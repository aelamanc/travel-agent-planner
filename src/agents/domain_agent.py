"""Generic domain agent bound to exactly one MCP server session.

Capability scoping is enforced at the protocol boundary here: a flights
DomainAgent only ever sees `self.tools`, which came from the flights
server's own `list_tools()` — it has no way to reach lodging or places
tools even if it wanted to, because they were never in its tool list.
"""

import time

from anthropic import AsyncAnthropic

from ..llm_loop import run_tool_loop
from ..token_tracker import StrategyRunTracker
from .cache import TTLCache
from .contracts import Domain, DomainFindings
from .mcp_session_manager import result_dict

DOMAIN_SYSTEM_PROMPTS: dict[Domain, str] = {
    "flights": (
        "You are the flights specialist on a travel-planning team. You can only see "
        "and call the flights server's tools — you have no visibility into hotels or "
        "experiences; other specialists handle those. Search for the outbound flight "
        "and, if return dates are given, the return flight too. Pick the best option(s) "
        "and summarize your pick and its price in plain text when you're done."
    ),
    "lodging": (
        "You are the lodging specialist on a travel-planning team. You can only see "
        "and call the lodging server's tools — you have no visibility into flights or "
        "experiences; other specialists handle those. Search for hotels matching the "
        "given constraints, pick the best option, and summarize your pick and its "
        "price in plain text when you're done."
    ),
    "experiences": (
        "You are the experiences specialist on a travel-planning team. You can only "
        "see and call the places server's tools (weather and attractions) — you have "
        "no visibility into flights or lodging; other specialists handle those. Check "
        "the weather, then find attractions matching the stated preferences, and "
        "summarize what you found in plain text when you're done."
    ),
}


class DomainAgent:
    """One agent, one MCP session, one domain. Tool-call budget is
    round-based and cumulative across re-invocations of the same instance:
    `max_tool_calls` passed to `run()` is a lifetime total, not a per-call
    reset — a flat cap would leave a re-invoked agent no room to act on a
    budget-agent's reallocation directive.
    """

    def __init__(
        self,
        domain: Domain,
        client: AsyncAnthropic,
        mcp_client,
        tools: list[dict],
        cache: TTLCache,
        server_name: str,
        model: str,
        max_tokens: int = 1024,
    ):
        self.domain = domain
        self.client = client
        self.mcp_client = mcp_client
        self.tools = tools
        self.cache = cache
        self.server_name = server_name
        self.model = model
        self.max_tokens = max_tokens

        self.tool_calls_made = 0
        self.cache_hits = 0
        self.mcp_round_trip_seconds = 0.0
        self.elapsed_seconds = 0.0
        self._captured: list[dict] = []

    async def _execute_tool(self, name: str, args: dict) -> dict:
        cached = self.cache.get(self.server_name, name, args)
        if cached is not None:
            self.cache_hits += 1
            data = cached
        else:
            t0 = time.monotonic()
            raw = await self.mcp_client.call_tool(name, args)
            self.mcp_round_trip_seconds += time.monotonic() - t0
            data = result_dict(raw)
            self.cache.set(self.server_name, name, args, data)
        self._captured.append({"tool": name, "args": args, "result": data})
        return data

    async def run(self, instructions: str, max_tool_calls: int = 4) -> DomainFindings:
        t_start = time.monotonic()
        tracker = StrategyRunTracker()
        remaining_calls = max(max_tool_calls - self.tool_calls_made, 0)

        result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=DOMAIN_SYSTEM_PROMPTS[self.domain],
            messages=[{"role": "user", "content": instructions}],
            tools=self.tools,
            execute_tool=self._execute_tool,
            tool_choice={"type": "auto"},
            max_tool_calls=remaining_calls,
            max_tokens=self.max_tokens,
            temperature=0,
        )
        tracker.record(result)
        self.tool_calls_made += result.num_tool_calls
        self.elapsed_seconds += time.monotonic() - t_start

        warnings = []
        summary = result.final_text or ""
        if not summary:
            warnings.append(
                f"{self.domain} agent produced no summary text (stop_reason={result.stop_reason})"
            )
        if result.stop_reason == "max_tool_calls":
            warnings.append(
                f"{self.domain} agent hit its tool-call cap ({max_tool_calls}) before finishing"
            )

        return DomainFindings(
            domain=self.domain,
            summary=summary,
            structured={"tool_calls": self._captured},
            tool_calls_made=self.tool_calls_made,
            cache_hits=self.cache_hits,
            usage=tracker.usage,
            warnings=warnings,
        )
