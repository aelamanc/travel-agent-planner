"""Plan-then-Execute strategy: generate full plan upfront, execute sequentially."""

import json

from ..llm_loop import ITINERARY_TOOL_SCHEMA, run_tool_loop
from ..models import ItineraryResult
from ..token_tracker import StrategyRunTracker
from .base import BaseStrategy

PLANNING_SYSTEM_PROMPT = """\
You are a travel planning assistant. Given a user's travel request, produce a \
step-by-step plan of exactly which tool calls to make to gather all information \
needed for a complete itinerary, then call `submit_plan` with that plan.

Available tools:
- search_flights: required: origin (str), destination (str), date (str YYYY-MM-DD); optional: max_price (number)
- search_hotels: required: destination (str), check_in (str YYYY-MM-DD), check_out (str YYYY-MM-DD); optional: max_price_per_night (number)
- get_weather: required: destination (str), start_date (str YYYY-MM-DD), end_date (str YYYY-MM-DD)
- get_attractions: required: destination (str); optional: preferences (array of strings)

Rules:
- Always include all five steps: outbound flight, return flight, hotels, weather, attractions.
- Extract dates, origin, budget, and preferences from the user query.
- If origin is not mentioned, default to "JFK".
- If budget is mentioned, pass it as max_price / max_price_per_night.
- For preferences, infer from the query (e.g. "museums" → ["museum"], "food lover" → ["food"]).
- The return flight swaps origin/destination and uses the end date.
"""

SYNTHESIS_SYSTEM_PROMPT = """\
You are a travel planning assistant. You have executed a plan and collected results \
from several tools. Using ALL of the tool results below, call `finish_itinerary` \
with a complete travel itinerary.

Guidelines:
- Pick the best flight and hotel given any budget constraints.
- Build one day plan entry per day of the trip.
- Distribute attractions across days (2-3 per day max).
- estimated_cost per day = attraction costs + meals estimate.
- total_estimated_cost = flight + hotel total + sum of daily costs.
- Respect any stated budget — flag in natural_language_summary if over budget.
"""

PLAN_TOOL_SCHEMA = {
    "name": "submit_plan",
    "description": "Submit the step-by-step tool-call plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "enum": ["search_flights", "search_hotels", "get_weather", "get_attractions"],
                        },
                        "args": {"type": "object"},
                    },
                    "required": ["tool", "args"],
                },
            },
        },
        "required": ["steps"],
    },
}


class PlanExecuteStrategy(BaseStrategy):
    @property
    def strategy_name(self) -> str:
        return "plan_then_execute"

    async def run(self, query: str) -> ItineraryResult:
        tracker = StrategyRunTracker()

        # ── Phase 1: Generate plan ────────────────────────────────────
        plan_result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=PLANNING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            tools=[PLAN_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "submit_plan"},
            single_shot=True,
            max_tokens=2048,
            temperature=0,
        )
        tracker.record(plan_result)
        plan = plan_result.forced_tool_input.get("steps", [])

        # ── Phase 2: Execute plan ─────────────────────────────────────
        tool_results = []
        for step in plan:
            tool_name = step.get("tool", "")
            tool_args = step.get("args", {})
            result = self._execute_tool(tool_name, tool_args)
            tool_results.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            })

        # ── Phase 3: Synthesize itinerary ─────────────────────────────
        tool_context = json.dumps(tool_results, indent=2)
        synthesis_result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=SYNTHESIS_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Original request: {query}\n\n"
                        f"Tool results:\n{tool_context}"
                    ),
                },
            ],
            tools=[ITINERARY_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "finish_itinerary"},
            single_shot=True,
            max_tokens=4096,
            temperature=0,
        )
        tracker.record(synthesis_result)
        data = synthesis_result.forced_tool_input

        self.last_run_usage = tracker.usage
        return self._build_result(data, tracker)

    def _build_result(self, data: dict, tracker: StrategyRunTracker) -> ItineraryResult:
        flight = data.get("selected_flight", {})
        return_flight = data.get("return_flight")
        hotel = data.get("selected_hotel", {})
        daily_plan = data.get("daily_plan", [])

        if "total_price" not in hotel:
            nights = len(daily_plan) or 1
            hotel["total_price"] = hotel.get("price_per_night", 0) * nights

        flights = [flight] if flight else []
        if return_flight:
            flights.append(return_flight)

        return ItineraryResult(
            destination=data.get("destination", "unknown"),
            travel_dates=(
                data.get("start_date", ""),
                data.get("end_date", ""),
            ),
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
