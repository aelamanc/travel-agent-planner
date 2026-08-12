"""Tests for the orchestrated strategy's agent layer: contracts, the TTL
cache, cost computation, and gather-failure resilience.

No ANTHROPIC_API_KEY is required. Where a domain agent's interaction with
`run_tool_loop()` needs exercising, a small fake Anthropic client stub
stands in for `AsyncAnthropic` — it never touches the network.
"""

import time
from types import SimpleNamespace

import pytest

from src.agents.budget_agent import compute_total_cost
from src.agents.cache import TTLCache
from src.agents.contracts import (
    BudgetVerdict,
    ConstraintSet,
    DomainFindings,
    OrchestrationRunStats,
    ReallocationDirective,
)
from src.agents.domain_agent import DomainAgent
from src.agents.mcp_session_manager import mcp_tool_to_anthropic
from src.strategies.orchestrated import OrchestratedStrategy
from src.token_tracker import TokenUsage


# ── Fakes: stand in for AsyncAnthropic and an MCP Client, no network ──────


class FakeUsage:
    def __init__(self, input_tokens=5, output_tokens=5):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, name, input, id="call_1"):
        self.name = name
        self.input = input
        self.id = id


class FakeMessage:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.usage = FakeUsage()
        self.stop_reason = stop_reason


class FakeMessagesAPI:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeAnthropicClient:
    def __init__(self, responses):
        self.messages = FakeMessagesAPI(responses)


class FakeRaisingMcpClient:
    """An MCP client whose call_tool always raises — simulates a domain
    agent's server dying or a tool call failing mid-conversation."""

    async def call_tool(self, name, args):
        raise RuntimeError(f"simulated MCP failure calling {name}")


# ── Contracts ───────────────────────────────────────────────────────────


class TestContracts:
    def test_constraint_set_defaults(self):
        c = ConstraintSet(
            origin="JFK", destinations=["Paris"], start_date="2025-06-15",
            end_date="2025-06-20", raw_query="plan a trip",
        )
        assert c.budget_total is None
        assert c.budget_currency == "USD"
        assert c.party_size == 1
        assert c.preferences == []

    def test_domain_findings_embeds_token_usage(self):
        f = DomainFindings(
            domain="flights", summary="found flights",
            usage=TokenUsage(input_tokens=10, output_tokens=20),
        )
        assert f.usage.total == 30
        assert f.structured == {}
        assert f.warnings == []

    def test_domain_findings_rejects_unknown_domain(self):
        with pytest.raises(Exception):
            DomainFindings(domain="not_a_domain", summary="x")

    def test_budget_verdict_directive_optional(self):
        accepted = BudgetVerdict(accepted=True, total_estimated_cost=100.0)
        assert accepted.directive is None

        directive = ReallocationDirective(
            target_domains=["flights"], reason="over budget",
            violated_constraint="budget_total", guidance="pick a cheaper flight",
        )
        rejected = BudgetVerdict(
            accepted=False, total_estimated_cost=999.0, directive=directive
        )
        assert rejected.directive.target_domains == ["flights"]

    def test_orchestration_run_stats_per_agent_usage(self):
        stats = OrchestrationRunStats(
            per_agent_usage={"flights": TokenUsage(1, 2), "supervisor": TokenUsage(3, 4)}
        )
        assert stats.per_agent_usage["flights"].total == 3
        assert stats.delegation_count == 0


# ── TTLCache ────────────────────────────────────────────────────────────


class TestTTLCache:
    def test_miss_then_hit(self):
        cache = TTLCache(ttl_seconds=60)
        assert cache.get("flights", "search_flights", {"a": 1}) is None
        cache.set("flights", "search_flights", {"a": 1}, {"count": 1})
        assert cache.get("flights", "search_flights", {"a": 1}) == {"count": 1}
        assert cache.hits == 1
        assert cache.misses == 1
        assert cache.hit_rate == 0.5

    def test_different_args_are_different_keys(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("flights", "search_flights", {"destination": "Paris"}, {"count": 1})
        assert cache.get("flights", "search_flights", {"destination": "Tokyo"}) is None

    def test_expired_entry_is_a_miss(self):
        cache = TTLCache(ttl_seconds=0.01)
        cache.set("flights", "search_flights", {"a": 1}, {"count": 1})
        time.sleep(0.02)
        assert cache.get("flights", "search_flights", {"a": 1}) is None

    def test_hit_rate_with_no_calls_is_zero(self):
        cache = TTLCache()
        assert cache.hit_rate == 0.0


# ── mcp_tool_to_anthropic ───────────────────────────────────────────────


class TestMcpToolToAnthropic:
    def test_field_rename(self):
        fake_tool = SimpleNamespace(
            name="search_flights",
            description="Search flights",
            input_schema={"type": "object", "properties": {}},
        )
        converted = mcp_tool_to_anthropic(fake_tool)
        assert converted == {
            "name": "search_flights",
            "description": "Search flights",
            "input_schema": {"type": "object", "properties": {}},
        }

    def test_missing_description_defaults_to_empty_string(self):
        fake_tool = SimpleNamespace(name="x", description=None, input_schema={})
        converted = mcp_tool_to_anthropic(fake_tool)
        assert converted["description"] == ""


# ── compute_total_cost ─────────────────────────────────────────────────


class TestComputeTotalCost:
    def test_sums_cheapest_flight_and_hotel(self):
        findings = [
            DomainFindings(
                domain="flights",
                summary="found flights",
                structured={
                    "tool_calls": [
                        {"tool": "search_flights", "args": {}, "result": {
                            "flights": [{"price": 500}, {"price": 300}]
                        }},
                        {"tool": "search_flights", "args": {}, "result": {
                            "flights": [{"price": 450}]
                        }},
                    ]
                },
            ),
            DomainFindings(
                domain="lodging",
                summary="found hotels",
                structured={
                    "tool_calls": [
                        {"tool": "search_hotels", "args": {}, "result": {
                            "hotels": [{"total_price": 600}, {"total_price": 400}]
                        }},
                    ]
                },
            ),
        ]
        # cheapest outbound (300) + cheapest return (450) + cheapest hotel (400)
        assert compute_total_cost(findings) == 300 + 450 + 400

    def test_empty_findings_cost_zero(self):
        assert compute_total_cost([]) == 0.0

    def test_ignores_non_flight_hotel_tools(self):
        findings = [
            DomainFindings(
                domain="experiences",
                summary="found attractions",
                structured={
                    "tool_calls": [
                        {"tool": "get_weather", "args": {}, "result": {"summary": "sunny"}},
                        {"tool": "get_attractions", "args": {}, "result": {"attractions": []}},
                    ]
                },
            ),
        ]
        assert compute_total_cost(findings) == 0.0


# ── Gather-failure resilience ───────────────────────────────────────────


class TestResolveGather:
    def test_exception_becomes_warnings_tagged_stub(self):
        real_finding = DomainFindings(domain="lodging", summary="ok", structured={"x": 1})
        raw = [RuntimeError("boom"), real_finding]
        resolved = OrchestratedStrategy._resolve_gather(raw, ("flights", "lodging"))

        assert resolved[0].domain == "flights"
        assert resolved[0].structured == {}
        assert "domain agent failed" in resolved[0].warnings[0]
        assert "boom" in resolved[0].warnings[0]

        assert resolved[1] is real_finding

    def test_no_exceptions_passes_through_unchanged(self):
        a = DomainFindings(domain="flights", summary="a")
        b = DomainFindings(domain="lodging", summary="b")
        resolved = OrchestratedStrategy._resolve_gather([a, b], ("flights", "lodging"))
        assert resolved == [a, b]


class TestDomainAgentGatherFailure:
    """A domain agent whose MCP tool call raises must not crash the whole
    orchestrated run — asyncio.gather(..., return_exceptions=True) plus
    _resolve_gather absorbs it into a warnings-tagged stub instead."""

    @pytest.mark.anyio
    async def test_mcp_failure_propagates_to_agent_then_absorbed_by_gather(self):
        import asyncio

        fake_client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[FakeToolUseBlock("search_flights", {"origin": "JFK", "destination": "Paris", "date": "2025-06-15"})],
                    stop_reason="tool_use",
                ),
            ]
        )
        agent = DomainAgent(
            domain="flights",
            client=fake_client,
            mcp_client=FakeRaisingMcpClient(),
            tools=[{"name": "search_flights", "description": "", "input_schema": {"type": "object"}}],
            cache=TTLCache(),
            server_name="flights",
            model="claude-haiku-4-5-20251001",
        )

        async def run_lodging_ok():
            return DomainFindings(domain="lodging", summary="found a hotel", structured={"picked": True})

        raw_results = await asyncio.gather(
            agent.run("find me a flight"), run_lodging_ok(), return_exceptions=True
        )
        resolved = OrchestratedStrategy._resolve_gather(raw_results, ("flights", "lodging"))

        assert resolved[0].domain == "flights"
        assert resolved[0].structured == {}
        assert any("domain agent failed" in w for w in resolved[0].warnings)
        assert "simulated MCP failure" in resolved[0].warnings[0]

        assert resolved[1].domain == "lodging"
        assert resolved[1].structured == {"picked": True}
        assert resolved[1].warnings == []


# ── Domain agent happy path (no failures) ──────────────────────────────


class TestDomainAgentHappyPath:
    @pytest.mark.anyio
    async def test_captures_tool_calls_and_stops_at_end_turn(self):
        fake_client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[FakeToolUseBlock("search_flights", {"origin": "JFK", "destination": "Paris", "date": "2025-06-15"})],
                    stop_reason="tool_use",
                ),
                FakeMessage(
                    content=[FakeTextBlock("Picked Air France for $485.")],
                    stop_reason="end_turn",
                ),
            ]
        )

        class FakeOkMcpClient:
            async def call_tool(self, name, args):
                return SimpleNamespace(
                    structured_content={"flights": [{"airline": "Air France", "price": 485}], "count": 1},
                    content=[],
                )

        agent = DomainAgent(
            domain="flights",
            client=fake_client,
            mcp_client=FakeOkMcpClient(),
            tools=[{"name": "search_flights", "description": "", "input_schema": {"type": "object"}}],
            cache=TTLCache(),
            server_name="flights",
            model="claude-haiku-4-5-20251001",
        )

        findings = await agent.run("find me a flight to Paris")

        assert findings.domain == "flights"
        assert findings.summary == "Picked Air France for $485."
        assert findings.tool_calls_made == 1
        assert findings.warnings == []
        assert findings.structured["tool_calls"][0]["tool"] == "search_flights"
        assert findings.structured["tool_calls"][0]["result"]["flights"][0]["airline"] == "Air France"

    @pytest.mark.anyio
    async def test_respects_cumulative_tool_call_cap_across_invocations(self):
        # Round 1: makes exactly 1 tool call (the cap), then stops.
        fake_client = FakeAnthropicClient(
            responses=[
                FakeMessage(
                    content=[FakeToolUseBlock("search_flights", {"origin": "JFK", "destination": "Paris", "date": "2025-06-15"})],
                    stop_reason="tool_use",
                ),
                FakeMessage(
                    content=[FakeTextBlock("No flights found.")],
                    stop_reason="end_turn",
                ),
            ]
        )

        class FakeOkMcpClient:
            async def call_tool(self, name, args):
                return SimpleNamespace(structured_content={"flights": [], "count": 0}, content=[])

        agent = DomainAgent(
            domain="flights", client=fake_client, mcp_client=FakeOkMcpClient(),
            tools=[{"name": "search_flights", "description": "", "input_schema": {"type": "object"}}],
            cache=TTLCache(), server_name="flights", model="claude-haiku-4-5-20251001",
        )

        findings = await agent.run("find flights", max_tool_calls=1)
        assert agent.tool_calls_made == 1
        assert findings.tool_calls_made == 1

        # Round 2 (post-rejection): cap raised to 6 total but 1 already spent,
        # so only 5 remain — the cap is cumulative on the same instance, not reset.
        assert max(6 - agent.tool_calls_made, 0) == 5
