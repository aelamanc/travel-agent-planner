"""ReAct strategy: interleaved think-act-observe loop."""

from ..llm_loop import ITINERARY_TOOL_SCHEMA, run_tool_loop
from ..models import ItineraryResult
from ..token_tracker import StrategyRunTracker
from .base import BaseStrategy

SYSTEM_PROMPT = """\
You are a travel planning assistant. Your job is to create a complete travel \
itinerary based on the user's request.

You have access to tools for searching flights, hotels, weather, and attractions. \
Use them one at a time: think about what information you need, call a tool, observe \
the result, and decide your next step. Continue until you have all the information \
needed to produce a complete itinerary.

When you have gathered enough information, call the `finish_itinerary` function \
with the complete itinerary data.

Important guidelines:
- Always search for flights, hotels, weather, AND attractions before finishing.
- Always search for BOTH the outbound flight (origin→destination) AND the return flight (destination→origin on the end date).
- Respect any budget constraints the user mentions — total cost includes outbound + return flight.
- Pick the best flight and hotel based on the user's preferences and constraints.
- Create a day-by-day plan using the attractions and weather data.
- Include estimated costs for each day.
"""

# `finish_itinerary` is a synthetic control-flow tool, not a real one — it is
# appended to the real tool list every call but never added to the tool
# registry (src/tools/__init__.py).
FINISH_TOOL = ITINERARY_TOOL_SCHEMA

MAX_ITERATIONS = 15


class ReActStrategy(BaseStrategy):
    @property
    def strategy_name(self) -> str:
        return "react"

    async def run(self, query: str) -> ItineraryResult:
        tracker = StrategyRunTracker()

        messages = [{"role": "user", "content": query}]
        tools = self._get_anthropic_tools() + [FINISH_TOOL]

        result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
            execute_tool=self._execute_tool,
            tool_choice={"type": "any"},  # always call a tool; prevents plain-text non-action responses
            stop_when=lambda block: block.name == "finish_itinerary",
            max_iterations=MAX_ITERATIONS,
            max_tokens=4096,
        )
        tracker.record(result)
        self.last_run_usage = tracker.usage

        if result.forced_tool_input is not None:
            return self._build_result(result.forced_tool_input, tracker)

        # Exhausted MAX_ITERATIONS without calling finish_itinerary
        return self._build_fallback(query, tracker)

    def _build_result(self, data: dict, tracker: StrategyRunTracker) -> ItineraryResult:
        """Convert the finish_itinerary arguments into an ItineraryResult."""
        flight = data.get("selected_flight", {})
        ret_flight = data.get("return_flight")
        flights = [flight]
        if ret_flight:
            flights.append(ret_flight)

        hotel = data.get("selected_hotel", {})
        daily_plan = data.get("daily_plan", [])

        # Ensure hotel has total_price
        if "total_price" not in hotel:
            nights = len(daily_plan) or 1
            hotel["total_price"] = hotel.get("price_per_night", 0) * nights

        return ItineraryResult(
            destination=data["destination"],
            travel_dates=(data["start_date"], data["end_date"]),
            flights=flights,
            hotel=hotel,
            daily_plan=daily_plan,
            weather_summary=data.get("weather_summary", ""),
            total_estimated_cost=data.get("total_estimated_cost", 0),
            natural_language_summary=data.get("natural_language_summary", ""),
            strategy_used=self.strategy_name,
            tokens_used=tracker.usage.total,
            latency_seconds=round(tracker.latency_seconds, 2),
        )

    def _build_fallback(self, query: str, tracker: StrategyRunTracker) -> ItineraryResult:
        """Fallback if the agent didn't call finish_itinerary."""
        return ItineraryResult(
            destination="unknown",
            travel_dates=("", ""),
            flights=[],
            hotel={
                "name": "N/A",
                "address": "",
                "price_per_night": 0,
                "rating": 0,
                "amenities": [],
                "total_price": 0,
            },
            daily_plan=[],
            weather_summary="",
            total_estimated_cost=0,
            natural_language_summary=f"Failed to complete itinerary for: {query}",
            strategy_used=self.strategy_name,
            tokens_used=tracker.usage.total,
            latency_seconds=round(tracker.latency_seconds, 2),
        )
