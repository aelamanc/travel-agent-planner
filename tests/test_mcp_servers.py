"""Tests for the MCP servers wrapping the existing BaseTool subclasses.

Uses the in-memory MCP client (mcp.client.Client connected directly to an
MCPServer instance) — no subprocess is spawned and no ANTHROPIC_API_KEY (or
any API key) is required, since these servers only exercise the mock tool
data path.
"""

import json

import pytest
from mcp.client import Client
from mcp.server.mcpserver import MCPServer

from src.mcp_servers import flights_server, lodging_server, places_server
from src.tools.flights import SearchFlightsTool


def _result_dict(call_tool_result) -> dict:
    """Extract the tool's returned dict from a CallToolResult."""
    if call_tool_result.structured_content is not None:
        return call_tool_result.structured_content
    text = call_tool_result.content[0].text
    return json.loads(text)


class TestFlightsServer:
    @pytest.mark.anyio
    async def test_lists_search_flights_tool(self):
        async with Client(flights_server.mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools.tools]
            assert names == ["search_flights"]
            schema = tools.tools[0].input_schema
            assert set(schema["required"]) == {"origin", "destination", "date"}

    @pytest.mark.anyio
    async def test_dispatch_matches_base_tool(self):
        async with Client(flights_server.mcp) as client:
            result = await client.call_tool(
                "search_flights",
                {"origin": "JFK", "destination": "Paris", "date": "2025-06-15"},
            )
            assert result.is_error is not True
            data = _result_dict(result)

        expected = SearchFlightsTool(mode="mock").run(
            origin="JFK", destination="Paris", date="2025-06-15"
        )
        assert data["count"] == expected["count"]
        assert data["count"] > 0
        assert all("airline" in f for f in data["flights"])

    @pytest.mark.anyio
    async def test_respects_max_price(self):
        async with Client(flights_server.mcp) as client:
            result = await client.call_tool(
                "search_flights",
                {
                    "origin": "JFK",
                    "destination": "Paris",
                    "date": "2025-06-15",
                    "max_price": 100,
                },
            )
            data = _result_dict(result)
            assert all(f["price"] <= 100 for f in data["flights"])


class TestLodgingServer:
    @pytest.mark.anyio
    async def test_lists_search_hotels_tool(self):
        async with Client(lodging_server.mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools.tools]
            assert names == ["search_hotels"]

    @pytest.mark.anyio
    async def test_dispatch_returns_hotels(self):
        async with Client(lodging_server.mcp) as client:
            result = await client.call_tool(
                "search_hotels",
                {
                    "destination": "Paris",
                    "check_in": "2025-06-15",
                    "check_out": "2025-06-20",
                },
            )
            data = _result_dict(result)
            assert data["count"] > 0
            assert all("name" in h for h in data["hotels"])


class TestPlacesServer:
    @pytest.mark.anyio
    async def test_lists_both_tools(self):
        async with Client(places_server.mcp) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools.tools}
            assert names == {"get_weather", "get_attractions"}

    @pytest.mark.anyio
    async def test_get_weather_dispatch(self):
        async with Client(places_server.mcp) as client:
            result = await client.call_tool(
                "get_weather",
                {
                    "destination": "Paris",
                    "start_date": "2025-06-15",
                    "end_date": "2025-06-20",
                },
            )
            data = _result_dict(result)
            assert "forecast" in data
            assert "summary" in data

    @pytest.mark.anyio
    async def test_get_attractions_preference_filter(self):
        async with Client(places_server.mcp) as client:
            result = await client.call_tool(
                "get_attractions", {"destination": "Paris", "preferences": ["museum"]}
            )
            data = _result_dict(result)
            assert data["count"] > 0
            assert all(a["category"].lower() == "museum" for a in data["attractions"])

    @pytest.mark.anyio
    async def test_reads_destinations_resource(self):
        async with Client(places_server.mcp) as client:
            result = await client.read_resource("travel://destinations")
            payload = json.loads(result.contents[0].text)
            assert "paris" in payload["destinations"]
            assert "tokyo" in payload["destinations"]
            assert "rome" in payload["destinations"]

    @pytest.mark.anyio
    async def test_fetches_experience_search_strategy_prompt(self):
        async with Client(places_server.mcp) as client:
            result = await client.get_prompt(
                "experience_search_strategy",
                {"city": "Paris", "preferences": "museum"},
            )
            joined = " ".join(
                m.content.text if hasattr(m.content, "text") else str(m.content)
                for m in result.messages
            )
            assert "Paris" in joined
            assert "get_weather" in joined
            assert "get_attractions" in joined


class TestLiveFallbackTagging:
    """MCP dispatch must preserve BaseTool's mock_fallback/live_error tagging."""

    @pytest.mark.anyio
    async def test_live_failure_falls_back_to_mock_with_tagging(self, monkeypatch):
        monkeypatch.delenv("SERPAPI_KEY", raising=False)
        live_tool = SearchFlightsTool(mode="live")

        probe = MCPServer("flights-live-probe")

        @probe.tool(name=live_tool.name, description=live_tool.description)
        def search_flights(origin: str, destination: str, date: str) -> dict:
            return live_tool.run(origin=origin, destination=destination, date=date)

        async with Client(probe) as client:
            result = await client.call_tool(
                "search_flights",
                {"origin": "JFK", "destination": "Paris", "date": "2025-06-15"},
            )
            data = _result_dict(result)

        assert data["mode"] == "mock_fallback"
        assert "live_error" in data
        assert data["count"] > 0
