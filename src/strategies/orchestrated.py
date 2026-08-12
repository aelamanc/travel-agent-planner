"""Fifth strategy: multi-agent orchestration over MCP.

supervisor -> asyncio.gather(3 domain agents, return_exceptions=True)
    -> compute_total_cost (Python) -> budget check (Python)
        -> if over budget: evaluate_budget's one LLM call (ReallocationDirective only)
           -> re-invoke the named domain agent(s) once (cap 4->6, hard 2-round ceiling)
    -> synthesizer -> ItineraryResult

Capability scoping is the point: each domain agent connects to exactly one
MCP server and only ever sees that server's tools — enforced by the
protocol boundary (MCPSessionManager hands each agent one server's tool
list), not by a prompt asking it to behave.
"""

import asyncio
import time

from ..agents.budget_agent import evaluate_budget
from ..agents.cache import TTLCache
from ..agents.contracts import ConstraintSet, Domain, DomainFindings, OrchestrationRunStats
from ..agents.domain_agent import DomainAgent
from ..agents.mcp_session_manager import MCPSessionManager
from ..agents.supervisor import parse_constraints
from ..agents.synthesizer import synthesize
from ..anthropic_client import DEFAULT_MODEL
from ..models import ItineraryResult
from ..token_tracker import StrategyRunTracker, TokenUsage
from .base import BaseStrategy

INITIAL_MAX_TOOL_CALLS = 4
REALLOCATION_MAX_TOOL_CALLS = 6
DOMAIN_TO_SERVER: dict[Domain, str] = {
    "flights": "flights",
    "lodging": "lodging",
    "experiences": "places",
}


def _add_usage(bucket: dict[str, TokenUsage], key: str, usage: TokenUsage) -> None:
    bucket[key] = bucket.get(key, TokenUsage()) + usage


class OrchestratedStrategy(BaseStrategy):
    def __init__(
        self,
        mcp_manager: MCPSessionManager,
        cache: TTLCache,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1024,
    ):
        super().__init__(tools=[], model=model)
        self.mcp_manager = mcp_manager
        self.cache = cache
        self.max_tokens = max_tokens

    @property
    def strategy_name(self) -> str:
        return "orchestrated"

    def _build_domain_agent(self, domain: Domain) -> DomainAgent:
        server_name = DOMAIN_TO_SERVER[domain]
        return DomainAgent(
            domain=domain,
            client=self.client,
            mcp_client=self.mcp_manager.clients[server_name],
            tools=self.mcp_manager.tools_by_server[server_name],
            cache=self.cache,
            server_name=server_name,
            model=self.model,
            max_tokens=self.max_tokens,
        )

    @staticmethod
    def _domain_instructions(
        domain: Domain, constraints: ConstraintSet, guidance: str | None = None
    ) -> str:
        dest = ", ".join(constraints.destinations)
        text = (
            f"Origin: {constraints.origin}. Destination(s): {dest}. "
            f"Dates: {constraints.start_date} to {constraints.end_date}. "
            f"Party size: {constraints.party_size}. "
            f"Preferences: {', '.join(constraints.preferences) or 'none stated'}. "
            f"Budget: "
            f"{constraints.budget_total if constraints.budget_total is not None else 'not stated'} "
            f"{constraints.budget_currency}."
        )
        if guidance:
            text += f"\n\nThe budget reviewer rejected the previous round: {guidance}"
        return text

    @staticmethod
    def _resolve_gather(
        raw_results: list, domains: tuple[Domain, ...]
    ) -> list[DomainFindings]:
        """asyncio.gather(..., return_exceptions=True) never aborts the query —
        a failed domain becomes a warnings-tagged stub instead of a raised
        exception reaching the caller."""
        resolved = []
        for domain, r in zip(domains, raw_results):
            if isinstance(r, BaseException):
                resolved.append(
                    DomainFindings(
                        domain=domain,
                        summary="",
                        structured={},
                        tool_calls_made=0,
                        cache_hits=0,
                        usage=TokenUsage(),
                        warnings=[f"domain agent failed: {type(r).__name__}: {r}"],
                    )
                )
            else:
                resolved.append(r)
        return resolved

    async def run(self, query: str) -> ItineraryResult:
        tracker = StrategyRunTracker()
        per_agent_usage: dict[str, TokenUsage] = {}
        gather_wall_clock = 0.0

        constraints, supervisor_usage = await parse_constraints(
            query, self.client, self.model, max_tokens=self.max_tokens
        )
        _add_usage(per_agent_usage, "supervisor", supervisor_usage)
        tracker.usage += supervisor_usage

        domains: tuple[Domain, ...] = ("flights", "lodging", "experiences")
        agents = {d: self._build_domain_agent(d) for d in domains}

        async def run_domain(domain: Domain, guidance: str | None = None) -> DomainFindings:
            instructions = self._domain_instructions(domain, constraints, guidance)
            return await agents[domain].run(instructions, max_tool_calls=INITIAL_MAX_TOOL_CALLS)

        t0 = time.monotonic()
        raw_results = await asyncio.gather(
            *(run_domain(d) for d in domains), return_exceptions=True
        )
        gather_wall_clock += time.monotonic() - t0

        findings = self._resolve_gather(raw_results, domains)
        delegation_count = len(domains)
        for f in findings:
            _add_usage(per_agent_usage, f.domain, f.usage)
            tracker.usage += f.usage

        verdict, budget_usage = await evaluate_budget(
            constraints, findings, self.client, self.model, max_tokens=self.max_tokens
        )
        _add_usage(per_agent_usage, "budget", budget_usage)
        tracker.usage += budget_usage
        replan_count = 0

        if not verdict.accepted and verdict.directive is not None:
            replan_count = 1
            directive = verdict.directive
            target_domains = tuple(
                d for d in directive.target_domains if d in agents
            )

            t1 = time.monotonic()
            raw_retry = await asyncio.gather(
                *(
                    agents[d].run(
                        self._domain_instructions(d, constraints, directive.guidance),
                        max_tool_calls=REALLOCATION_MAX_TOOL_CALLS,
                    )
                    for d in target_domains
                ),
                return_exceptions=True,
            )
            gather_wall_clock += time.monotonic() - t1

            retried = dict(zip(target_domains, self._resolve_gather(raw_retry, target_domains)))
            delegation_count += len(target_domains)

            new_findings = []
            for f in findings:
                if f.domain in retried:
                    r = retried[f.domain]
                    new_findings.append(r)
                    _add_usage(per_agent_usage, f.domain, r.usage)
                    tracker.usage += r.usage
                else:
                    new_findings.append(f)
            findings = new_findings

            # Round 2 ships regardless of the outcome (hard 2-round cap) —
            # still recompute so the shipped total_estimated_cost is current.
            verdict, budget_usage_2 = await evaluate_budget(
                constraints, findings, self.client, self.model, max_tokens=self.max_tokens
            )
            _add_usage(per_agent_usage, "budget", budget_usage_2)
            tracker.usage += budget_usage_2

        # Fixed, generous budget for the itinerary-generating call regardless
        # of self.max_tokens (which sizes the smaller supervisor/domain/budget
        # calls) — matches the 4096 every other strategy uses for the same
        # ITINERARY_TOOL_SCHEMA call, since a multi-day daily_plan can be long.
        raw_itinerary, synth_usage = await synthesize(
            constraints, findings, self.client, self.model, max_tokens=4096,
        )
        _add_usage(per_agent_usage, "synthesizer", synth_usage)
        tracker.usage += synth_usage

        flight = raw_itinerary.get("selected_flight") or {}
        return_flight = raw_itinerary.get("return_flight")
        flights = [flight] if flight else []
        if return_flight:
            flights.append(return_flight)

        hotel = raw_itinerary.get("selected_hotel") or {}
        daily_plan = raw_itinerary.get("daily_plan", [])
        if "total_price" not in hotel:
            nights = len(daily_plan) or 1
            hotel["total_price"] = hotel.get("price_per_night", 0) * nights

        mcp_round_trip = sum(a.mcp_round_trip_seconds for a in agents.values())
        serial_equivalent = sum(a.elapsed_seconds for a in agents.values())
        # tool_calls_made already counts cache hits (run_tool_loop calls
        # _execute_tool for every tool_use block regardless of cache outcome
        # inside it) — it's the right denominator, not tool_calls_made + hits.
        cache_hits = sum(a.cache_hits for a in agents.values())
        cache_calls = sum(a.tool_calls_made for a in agents.values())

        self.last_run_usage = tracker.usage
        self.last_run_stats = OrchestrationRunStats(
            delegation_count=delegation_count,
            replan_count=replan_count,
            cache_hit_rate=(cache_hits / cache_calls) if cache_calls else 0.0,
            serial_equivalent_seconds=round(serial_equivalent, 3),
            wall_clock_seconds=round(gather_wall_clock, 3),
            mcp_round_trip_seconds=round(mcp_round_trip, 3),
            agent_reasoning_seconds=round(max(gather_wall_clock - mcp_round_trip, 0.0), 3),
            per_agent_usage=per_agent_usage,
        )

        return ItineraryResult(
            destination=raw_itinerary.get("destination", "unknown"),
            travel_dates=(
                raw_itinerary.get("start_date", ""),
                raw_itinerary.get("end_date", ""),
            ),
            flights=flights,
            hotel=hotel,
            daily_plan=daily_plan,
            weather_summary=raw_itinerary.get("weather_summary", ""),
            total_estimated_cost=raw_itinerary.get("total_estimated_cost", 0),
            natural_language_summary=raw_itinerary.get("natural_language_summary", ""),
            strategy_used=self.strategy_name,
            tokens_used=tracker.usage.total,
            latency_seconds=round(tracker.latency_seconds, 2),
        )
