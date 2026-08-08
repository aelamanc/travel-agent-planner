"""Zero-shot baseline: single LLM call with no tool use."""

from .llm_loop import ITINERARY_TOOL_SCHEMA, run_tool_loop
from .models import ItineraryResult
from .strategies.base import BaseStrategy
from .token_tracker import StrategyRunTracker

SYSTEM_PROMPT = """\
You are a travel planning assistant. Given a user's travel request, produce a \
complete travel itinerary by calling `finish_itinerary` with the complete data. \
You have no tools for searching real flights, hotels, weather, or attractions — \
use your own knowledge to produce a plausible itinerary."""


class ZeroShotBaseline(BaseStrategy):
    """Not a `BaseStrategy` subclass before this migration — folded in here so
    the shared Anthropic tool-loop mixin (`self.client`, `run()` contract)
    serves it too."""

    @property
    def strategy_name(self) -> str:
        return "zero_shot_baseline"

    async def run(self, query: str) -> ItineraryResult:
        tracker = StrategyRunTracker()

        result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            tools=[ITINERARY_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "finish_itinerary"},
            single_shot=True,
            max_tokens=4096,
            temperature=0,
        )
        tracker.record(result)
        raw = result.forced_tool_input

        flight = raw.get("selected_flight", {})
        return_flight = raw.get("return_flight")
        hotel = raw.get("selected_hotel", {})
        daily_plan = raw.get("daily_plan", [])

        if "total_price" not in hotel:
            nights = len(daily_plan) or 1
            hotel["total_price"] = hotel.get("price_per_night", 0) * nights

        flights = [flight] if flight else []
        if return_flight:
            flights.append(return_flight)

        self.last_run_usage = tracker.usage

        return ItineraryResult(
            destination=raw.get("destination", "unknown"),
            travel_dates=(
                raw.get("start_date", ""),
                raw.get("end_date", ""),
            ),
            flights=flights,
            hotel=hotel,
            daily_plan=daily_plan,
            weather_summary=raw.get("weather_summary", ""),
            total_estimated_cost=raw.get("total_estimated_cost", 0),
            natural_language_summary=raw.get("natural_language_summary", ""),
            strategy_used=self.strategy_name,
            tokens_used=tracker.usage.total,
            latency_seconds=round(tracker.latency_seconds, 2),
        )
