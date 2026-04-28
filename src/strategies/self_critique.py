"""Self-Critique strategy: gather all data, draft, critique, then refine."""

import json
import time

from openai import OpenAI

from ..models import ItineraryResult
from ..tools.base import BaseTool
from .base import BaseStrategy

TOOL_EXTRACTION_SYSTEM_PROMPT = """\
You are a travel query parser. Extract structured parameters from the user's travel \
request and return ONLY a valid JSON object (no markdown) with these fields:
{
  "destination": "city name",
  "origin": "departure city or airport (default JFK if not mentioned)",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "max_budget": null or number (total trip budget in USD),
  "max_flight_price": null or number,
  "max_hotel_per_night": null or number,
  "preferences": []  (list of categories from: museum, landmark, food, park, shopping, tour)
}
If any date is not explicitly given, infer a reasonable near-future date.
"""

DRAFT_SYSTEM_PROMPT = """\
You are a travel planning assistant. Using the tool results provided, create a \
complete travel itinerary draft.

Return ONLY a valid JSON object (no markdown) with these exact fields:
{
  "destination": "city name",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "selected_flight": {
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
  "weather_summary": "",
  "total_estimated_cost": 0.0,
  "natural_language_summary": ""
}
- Create one day entry per travel day.
- Distribute 2-3 attractions per day.
- Pick the best flight and hotel from the options provided.
- Calculate total_estimated_cost = flight price + hotel total + sum of daily costs.
"""

CRITIQUE_SYSTEM_PROMPT = """\
You are a strict travel itinerary reviewer. Given the original user request and a \
draft itinerary, identify every flaw and score the draft.

Return ONLY a valid JSON object (no markdown):
{
  "score": <integer 1-10>,
  "issues": ["specific issue 1", "specific issue 2", ...],
  "suggestions": ["specific fix 1", "specific fix 2", ...]
}

Check ALL of the following:
- Budget: does total_estimated_cost exceed any stated budget?
- Completeness: are flights, hotel, AND daily plans all present and non-empty?
- Coverage: is there a day plan entry for every day of the trip?
- Scheduling: are there 2-3 attractions per day (not too many, not zero)?
- Preferences: if the user mentioned interests (museums, food, etc.), are those reflected?
- Weather: does the daily plan reference the forecast conditions?
- Realism: are meals mentioned every day? Are attraction prices plausible?
"""

REFINE_SYSTEM_PROMPT = """\
You are a travel planning assistant performing a final refinement pass. You have:
1. An original user request
2. A draft itinerary
3. A critique with specific issues and suggestions

Fix EVERY issue listed in the critique. Return the improved itinerary as ONLY a \
valid JSON object in the exact same format as the draft (no markdown, no explanation).

If the total cost exceeds the user's budget, pick cheaper flights/hotels from the \
original tool results and reduce daily activity costs accordingly.
"""


class SelfCritiqueStrategy(BaseStrategy):
    def __init__(self, tools: list[BaseTool], model: str = "gpt-4o"):
        super().__init__(tools, model)
        self.client = OpenAI()

    @property
    def strategy_name(self) -> str:
        return "self_critique"

    def run(self, query: str) -> ItineraryResult:
        start_time = time.time()
        total_tokens = 0

        # ── Phase 1: Extract structured params from query ─────────────
        extract_response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": TOOL_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
        )
        total_tokens += extract_response.usage.total_tokens
        params = json.loads(extract_response.choices[0].message.content)

        destination = params.get("destination", "Paris")
        origin = params.get("origin", "JFK")
        start_date = params.get("start_date", "2025-06-15")
        end_date = params.get("end_date", "2025-06-20")
        preferences = params.get("preferences", [])
        max_flight_price = params.get("max_flight_price") or params.get("max_budget")
        max_hotel_ppn = params.get("max_hotel_per_night")

        # ── Phase 2: Gather all tool data ─────────────────────────────
        flight_args = {"origin": origin, "destination": destination, "date": start_date}
        if max_flight_price:
            flight_args["max_price"] = max_flight_price

        hotel_args = {
            "destination": destination,
            "check_in": start_date,
            "check_out": end_date,
        }
        if max_hotel_ppn:
            hotel_args["max_price_per_night"] = max_hotel_ppn

        attraction_args = {"destination": destination}
        if preferences:
            attraction_args["preferences"] = preferences

        flights_data = self._execute_tool("search_flights", flight_args)
        hotels_data = self._execute_tool("search_hotels", hotel_args)
        weather_data = self._execute_tool(
            "get_weather",
            {"destination": destination, "start_date": start_date, "end_date": end_date},
        )
        attractions_data = self._execute_tool("get_attractions", attraction_args)

        tool_results = {
            "search_flights": flights_data,
            "search_hotels": hotels_data,
            "get_weather": weather_data,
            "get_attractions": attractions_data,
        }

        # ── Phase 3: Draft itinerary ──────────────────────────────────
        tool_context = json.dumps(tool_results, indent=2)
        draft_response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User request: {query}\n\n"
                        f"Tool results:\n{tool_context}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        total_tokens += draft_response.usage.total_tokens
        draft = json.loads(draft_response.choices[0].message.content)

        # ── Phase 4: Critique ─────────────────────────────────────────
        critique_response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Original request: {query}\n\n"
                        f"Draft itinerary:\n{json.dumps(draft, indent=2)}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        total_tokens += critique_response.usage.total_tokens
        critique = json.loads(critique_response.choices[0].message.content)

        # ── Phase 5: Refine ───────────────────────────────────────────
        # Only refine if critique score < 8 or there are issues
        score = critique.get("score", 10)
        issues = critique.get("issues", [])

        if score >= 8 and not issues:
            # Draft is good enough — skip refinement to save tokens
            final = draft
        else:
            refine_response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": REFINE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Original request: {query}\n\n"
                            f"Draft itinerary:\n{json.dumps(draft, indent=2)}\n\n"
                            f"Critique:\n{json.dumps(critique, indent=2)}\n\n"
                            f"Tool results (for reference):\n{tool_context}"
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
            total_tokens += refine_response.usage.total_tokens
            final = json.loads(refine_response.choices[0].message.content)

        latency = time.time() - start_time
        return self._build_result(final, critique, total_tokens, latency)

    def _build_result(
        self, data: dict, critique: dict, tokens: int, latency: float
    ) -> ItineraryResult:
        flight = data.get("selected_flight", {})
        hotel = data.get("selected_hotel", {})
        daily_plan = data.get("daily_plan", [])

        if "total_price" not in hotel:
            nights = len(daily_plan) or 1
            hotel["total_price"] = hotel.get("price_per_night", 0) * nights

        # Append critique score to the summary so it's visible in eval output
        summary = data.get("natural_language_summary", "")
        score = critique.get("score")
        if score is not None:
            summary = f"[Critique score: {score}/10] {summary}"

        return ItineraryResult(
            destination=data.get("destination", "unknown"),
            travel_dates=(
                data.get("start_date", ""),
                data.get("end_date", ""),
            ),
            flights=[flight] if flight else [],
            hotel=hotel,
            daily_plan=daily_plan,
            weather_summary=data.get("weather_summary", ""),
            total_estimated_cost=data.get("total_estimated_cost", 0),
            natural_language_summary=summary,
            strategy_used=self.strategy_name,
            tokens_used=tokens,
            latency_seconds=round(latency, 2),
        )
