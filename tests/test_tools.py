"""Unit tests for the mock tools."""

import pytest

from src.tools.flights import SearchFlightsTool
from src.tools.hotels import SearchHotelsTool
from src.tools.weather import GetWeatherTool
from src.tools.attractions import GetAttractionsTool


class TestSearchFlights:
    def setup_method(self):
        self.tool = SearchFlightsTool()

    def test_returns_flights_for_known_destination(self):
        result = self.tool.run(origin="JFK", destination="Paris", date="2025-06-15")
        assert result["count"] > 0
        assert all("airline" in f for f in result["flights"])

    def test_respects_max_price(self):
        result = self.tool.run(
            origin="JFK", destination="Paris", date="2025-06-15", max_price=430
        )
        assert all(f["price"] <= 430 for f in result["flights"])

    def test_returns_flights_for_unknown_destination(self):
        result = self.tool.run(origin="JFK", destination="Narnia", date="2025-06-15")
        assert result["count"] > 0

    def test_openai_tool_format(self):
        tool_def = self.tool.to_openai_tool()
        assert tool_def["type"] == "function"
        assert tool_def["function"]["name"] == "search_flights"


class TestSearchHotels:
    def setup_method(self):
        self.tool = SearchHotelsTool()

    def test_returns_hotels_for_known_destination(self):
        result = self.tool.run(
            destination="Paris", check_in="2025-06-15", check_out="2025-06-20"
        )
        assert result["count"] > 0
        assert all("total_price" in h for h in result["hotels"])

    def test_calculates_total_price_correctly(self):
        result = self.tool.run(
            destination="Paris", check_in="2025-06-15", check_out="2025-06-20"
        )
        for hotel in result["hotels"]:
            assert hotel["total_price"] == hotel["price_per_night"] * 5

    def test_respects_max_price_per_night(self):
        result = self.tool.run(
            destination="Paris",
            check_in="2025-06-15",
            check_out="2025-06-20",
            max_price_per_night=100,
        )
        assert all(h["price_per_night"] <= 100 for h in result["hotels"])


class TestGetWeather:
    def setup_method(self):
        self.tool = GetWeatherTool()

    def test_returns_forecast_for_known_destination(self):
        result = self.tool.run(
            destination="Paris", start_date="2025-06-15", end_date="2025-06-20"
        )
        assert "forecast" in result
        assert "summary" in result
        assert len(result["forecast"]) > 0

    def test_returns_forecast_for_unknown_destination(self):
        result = self.tool.run(
            destination="Atlantis", start_date="2025-06-15", end_date="2025-06-20"
        )
        assert "forecast" in result


class TestGetAttractions:
    def setup_method(self):
        self.tool = GetAttractionsTool()

    def test_returns_attractions_for_known_destination(self):
        result = self.tool.run(destination="Paris")
        assert result["count"] > 0
        assert all("name" in a for a in result["attractions"])

    def test_filters_by_preferences(self):
        result = self.tool.run(destination="Paris", preferences=["museum"])
        assert all(
            a["category"] == "museum" for a in result["attractions"]
        )

    def test_fallback_when_preference_yields_nothing(self):
        result = self.tool.run(destination="Paris", preferences=["scuba_diving"])
        # Should fall back to all attractions
        assert result["count"] > 0
