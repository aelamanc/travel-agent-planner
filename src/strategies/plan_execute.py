"""Plan-then-Execute strategy: generate full plan upfront, execute sequentially."""

import json
import time

from openai import OpenAI

from ..models import ItineraryResult
from ..tools.base import BaseTool
from .base import BaseStrategy

PLANNING_SYSTEM_PROMPT = """\
You are a travel planning assistant. Given a user's travel request, produce a \
step-by-step plan of exactly which tool calls to make to gather all information \
needed for a complete itinerary.

Output ONLY a valid JSON object with a "steps" array. Each step must have "tool" and "args" keys.
Do not include any explanation or markdown — only the raw JSON object.

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

Example output:
{
  "steps": [
    {"tool": "search_flights", "args": {"origin": "JFK", "destination": "Paris", "date": "2025-06-15", "max_price": 500}},
    {"tool": "search_flights", "args": {"origin": "Paris", "destination": "JFK", "date": "2025-06-20", "max_price": 500}},
    {"tool": "search_hotels", "args": {"destination": "Paris", "check_in": "2025-06-15", "check_out": "2025-06-20", "max_price_per_night": 150}},
    {"tool": "get_weather", "args": {"destination": "Paris", "start_date": "2025-06-15", "end_date": "2025-06-20"}},
    {"tool": "get_attractions", "args": {"destination": "Paris", "preferences": ["museum", "food"]}}
  ]
}
"""

SYNTHESIS_SYSTEM_PROMPT = """\
You are a travel planning assistant. You have executed a plan and collected results \
from several tools. Using ALL of the tool results below, create a complete travel \
itinerary.

Return ONLY a valid JSON object (no markdown, no explanation) with these exact fields:
{
  "destination": "city name",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "selected_flight": {
    "airline": "", "flight_number": "", "origin": "", "destination": "",
    "departure_time": "", "arrival_time": "", "price": 0.0,
    "duration_hours": 0.0, "stops": 0
  },
  "return_flight": {
    "airline": "", "flight_number": "", "origin": "", "destination": "",
    "departure_time": "", "arrival_time": "", "price": 0.0,
    "duration_hours": 0.0, "stops": 0
  },
  "selected_hotel": {
    "name": "", "address": "", "price_per_night": 0.0, "rating": 0.0,
    "amenities": [], "total_price": 0.0
  },
  "daily_plan": [
    {
      "date": "YYYY-MM-DD",
      "weather": "brief weather description",
      "attractions": [
        {"name": "", "category": "", "rating": 0.0, "price": 0.0, "description": "", "duration_hours": 0.0}
      ],
      "meals": ["Breakfast at ...", "Lunch at ...", "Dinner at ..."],
      "estimated_cost": 0.0
    }
  ],
  "weather_summary": "overall weather summary",
  "total_estimated_cost": 0.0,
  "natural_language_summary": "2-3 sentence overview of the trip"
}

Guidelines:
- Pick the best flight and hotel given any budget constraints.
- Build one day plan entry per day of the trip.
- Distribute attractions across days (2-3 per day max).
- estimated_cost per day = attraction costs + meals estimate.
- total_estimated_cost = flight + hotel total + sum of daily costs.
- Respect any stated budget — flag in natural_language_summary if over budget.
"""


class PlanExecuteStrategy(BaseStrategy):
    def __init__(self, tools: list[BaseTool], model: str = "gpt-4o"):
        super().__init__(tools, model)
        self.client = OpenAI()

    @property
    def strategy_name(self) -> str:
        return "plan_then_execute"

    def run(self, query: str) -> ItineraryResult:
        start_time = time.time()
        total_tokens = 0

        # ── Phase 1: Generate plan ────────────────────────────────────
        plan_response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
        )
        total_tokens += plan_response.usage.total_tokens
        raw_plan = json.loads(plan_response.choices[0].message.content)

        # The model may return {"steps": [...]} or a bare array wrapped in a key
        if isinstance(raw_plan, list):
            plan = raw_plan
        else:
            # Find the first list value in the response object
            plan = next(
                (v for v in raw_plan.values() if isinstance(v, list)), []
            )

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
        synthesis_response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Original request: {query}\n\n"
                        f"Tool results:\n{tool_context}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        total_tokens += synthesis_response.usage.total_tokens
        data = json.loads(synthesis_response.choices[0].message.content)

        latency = time.time() - start_time
        return self._build_result(data, total_tokens, latency)

    def _build_result(
        self, data: dict, tokens: int, latency: float
    ) -> ItineraryResult:
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
            tokens_used=tokens,
            latency_seconds=round(latency, 2),
        )
