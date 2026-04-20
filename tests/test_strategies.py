"""Unit tests for strategy infrastructure (not LLM calls)."""

import pytest

from src.tools import TOOL_REGISTRY
from src.strategies.base import BaseStrategy
from src.models import ItineraryResult


class TestBaseStrategy:
    def test_tool_registry_has_all_tools(self):
        assert len(TOOL_REGISTRY) == 4
        names = {t.name for t in TOOL_REGISTRY}
        assert names == {"search_flights", "search_hotels", "get_weather", "get_attractions"}

    def test_openai_tools_format(self):
        # Use a concrete strategy to test the base method
        class DummyStrategy(BaseStrategy):
            @property
            def strategy_name(self):
                return "dummy"

            def run(self, query):
                pass

        s = DummyStrategy(TOOL_REGISTRY)
        tools = s._get_openai_tools()
        assert len(tools) == 4
        for t in tools:
            assert t["type"] == "function"
            assert "name" in t["function"]
            assert "parameters" in t["function"]

    def test_execute_tool(self):
        class DummyStrategy(BaseStrategy):
            @property
            def strategy_name(self):
                return "dummy"

            def run(self, query):
                pass

        s = DummyStrategy(TOOL_REGISTRY)
        result = s._execute_tool(
            "search_flights",
            {"origin": "JFK", "destination": "Paris", "date": "2025-06-15"},
        )
        assert "flights" in result

    def test_execute_unknown_tool(self):
        class DummyStrategy(BaseStrategy):
            @property
            def strategy_name(self):
                return "dummy"

            def run(self, query):
                pass

        s = DummyStrategy(TOOL_REGISTRY)
        result = s._execute_tool("nonexistent", {})
        assert "error" in result
