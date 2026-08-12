"""Self-Critique strategy: gather all data, draft, critique, then refine."""

import json

from ..llm_loop import ITINERARY_TOOL_SCHEMA, run_tool_loop
from ..models import ItineraryResult
from ..token_tracker import StrategyRunTracker
from .base import BaseStrategy

TOOL_EXTRACTION_SYSTEM_PROMPT = """\
You are a travel query parser. Extract structured parameters from the user's travel \
request by calling `submit_params`.
- end_date is also the return flight date.
- Always return "destinations" as an array, even for a single city (e.g. ["Paris"]).
- For multi-city trips list every city in order (e.g. ["Tokyo", "Rome"]).
- If any date is not explicitly given, infer a reasonable near-future date.
- If origin is not mentioned, default to "JFK".
- Preferences should be categories from: museum, landmark, food, park, shopping, tour.
"""

DRAFT_SYSTEM_PROMPT = """\
You are a travel planning assistant. Using the tool results provided, create a \
complete travel itinerary draft by calling `finish_itinerary`.

For multi-city trips: set "destination" to a comma-separated string (e.g. "Paris, Tokyo"), \
use the outbound flight to the first city as "selected_flight", pick the best hotel for \
the primary city as "selected_hotel", and distribute daily_plan entries across all cities.

- Create one day entry per travel day.
- Distribute 2-3 attractions per day.
- Pick the best flight and hotel from the options provided.
- Calculate total_estimated_cost = flight price + hotel total + sum of daily costs.
"""

CRITIQUE_SYSTEM_PROMPT = """\
You are a strict travel itinerary reviewer. Given the original user request and a \
draft itinerary, identify every flaw and score the draft by calling `submit_critique`.

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

Fix EVERY issue listed in the critique, then call `finish_itinerary` with the improved \
itinerary in the exact same format as the draft.

If the total cost exceeds the user's budget, pick cheaper flights/hotels from the \
original tool results and reduce daily activity costs accordingly.
"""

PARAMS_TOOL_SCHEMA = {
    "name": "submit_params",
    "description": "Submit the extracted structured travel parameters.",
    "input_schema": {
        "type": "object",
        "properties": {
            "destinations": {"type": "array", "items": {"type": "string"}},
            "origin": {"type": "string"},
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "max_budget": {"type": ["number", "null"], "description": "Total trip budget in USD"},
            "max_flight_price": {"type": ["number", "null"]},
            "max_hotel_per_night": {"type": ["number", "null"]},
            "preferences": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["destinations", "origin", "start_date", "end_date"],
    },
}

CRITIQUE_TOOL_SCHEMA = {
    "name": "submit_critique",
    "description": "Submit the critique of the draft itinerary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "description": "1-10"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "suggestions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "issues", "suggestions"],
    },
}


class SelfCritiqueStrategy(BaseStrategy):
    @property
    def strategy_name(self) -> str:
        return "self_critique"

    async def run(self, query: str) -> ItineraryResult:
        tracker = StrategyRunTracker()

        # ── Phase 1: Extract structured params from query ─────────────
        extract_result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=TOOL_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            tools=[PARAMS_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "submit_params"},
            single_shot=True,
            max_tokens=1024,
        )
        tracker.record(extract_result)
        params = extract_result.forced_tool_input

        raw_destinations = params.get("destinations") or [params.get("destination", "Paris")]
        destinations = [d for d in raw_destinations if d]
        if not destinations:
            destinations = ["Paris"]

        origin = params.get("origin", "JFK")
        start_date = params.get("start_date", "2025-06-15")
        end_date = params.get("end_date", "2025-06-20")
        preferences = params.get("preferences", [])
        max_flight_price = params.get("max_flight_price") or params.get("max_budget")
        max_hotel_ppn = params.get("max_hotel_per_night")

        # ── Phase 2: Gather tool data for every destination ───────────
        tool_results = {}
        for dest in destinations:
            flight_args = {"origin": origin, "destination": dest, "date": start_date}
            if max_flight_price:
                flight_args["max_price"] = max_flight_price

            hotel_args = {"destination": dest, "check_in": start_date, "check_out": end_date}
            if max_hotel_ppn:
                hotel_args["max_price_per_night"] = max_hotel_ppn

            attraction_args = {"destination": dest}
            if preferences:
                attraction_args["preferences"] = preferences

            return_args = {"origin": dest, "destination": origin, "date": end_date}
            if max_flight_price:
                return_args["max_price"] = max_flight_price

            tool_results[dest] = {
                "outbound_flights": self._execute_tool("search_flights", flight_args),
                "return_flights": self._execute_tool("search_flights", return_args),
                "hotels": self._execute_tool("search_hotels", hotel_args),
                "weather": self._execute_tool(
                    "get_weather",
                    {"destination": dest, "start_date": start_date, "end_date": end_date},
                ),
                "attractions": self._execute_tool("get_attractions", attraction_args),
            }

        # ── Phase 3: Draft itinerary ──────────────────────────────────
        tool_context = json.dumps(tool_results, indent=2)
        draft_result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=DRAFT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"User request: {query}\n\n"
                        f"Tool results:\n{tool_context}"
                    ),
                },
            ],
            tools=[ITINERARY_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "finish_itinerary"},
            single_shot=True,
            max_tokens=4096,
        )
        tracker.record(draft_result)
        draft = draft_result.forced_tool_input

        # ── Phase 4: Critique ─────────────────────────────────────────
        critique_result = await run_tool_loop(
            client=self.client,
            model=self.model,
            system=CRITIQUE_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Original request: {query}\n\n"
                        f"Draft itinerary:\n{json.dumps(draft, indent=2)}"
                    ),
                },
            ],
            tools=[CRITIQUE_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "submit_critique"},
            single_shot=True,
            max_tokens=1024,
        )
        tracker.record(critique_result)
        critique = critique_result.forced_tool_input

        # ── Phase 5: Refine ───────────────────────────────────────────
        # Only refine if critique score < 8 or there are issues
        score = critique.get("score", 10)
        issues = critique.get("issues", [])

        if score >= 8 and not issues:
            # Draft is good enough — skip refinement to save tokens
            final = draft
        else:
            refine_result = await run_tool_loop(
                client=self.client,
                model=self.model,
                system=REFINE_SYSTEM_PROMPT,
                messages=[
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
                tools=[ITINERARY_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "finish_itinerary"},
                single_shot=True,
                max_tokens=4096,
            )
            tracker.record(refine_result)
            final = refine_result.forced_tool_input

        self.last_run_usage = tracker.usage
        return self._build_result(final, critique, tracker)

    def _build_result(
        self, data: dict, critique: dict, tracker: StrategyRunTracker
    ) -> ItineraryResult:
        # Normalize destination (LLM sometimes returns a list for multi-city)
        destination = data.get("destination", "unknown")
        if isinstance(destination, list):
            destination = ", ".join(str(d) for d in destination)

        hotel = data.get("selected_hotel", {})
        daily_plan = data.get("daily_plan", [])

        # Normalize daily_plan (LLM sometimes returns a dict keyed by city)
        if isinstance(daily_plan, dict):
            flat: list = []
            for v in daily_plan.values():
                if isinstance(v, list):
                    flat.extend(v)
            daily_plan = flat

        # Normalize hotel (LLM sometimes returns per-city dict or empty object)
        if not isinstance(hotel, dict) or "name" not in hotel:
            hotel = {
                "name": "N/A", "address": "", "price_per_night": 0.0,
                "rating": 0.0, "amenities": [], "total_price": 0.0,
            }

        # Normalize weather_summary (LLM sometimes returns a per-city dict)
        weather_summary = data.get("weather_summary", "")
        if isinstance(weather_summary, dict):
            weather_summary = " | ".join(str(v) for v in weather_summary.values())

        if "total_price" not in hotel:
            nights = len(daily_plan) or 1
            hotel["total_price"] = hotel.get("price_per_night", 0) * nights

        # Append critique score to the summary so it's visible in eval output
        summary = data.get("natural_language_summary", "")
        score = critique.get("score")
        if score is not None:
            summary = f"[Critique score: {score}/10] {summary}"

        flight = data.get("selected_flight", {})
        return_flight = data.get("return_flight")
        flights = [flight] if flight else []
        if return_flight:
            flights.append(return_flight)

        return ItineraryResult(
            destination=destination,
            travel_dates=(
                data.get("start_date", ""),
                data.get("end_date", ""),
            ),
            flights=flights,
            hotel=hotel,
            daily_plan=daily_plan,
            weather_summary=weather_summary,
            total_estimated_cost=data.get("total_estimated_cost", 0),
            natural_language_summary=summary,
            strategy_used=self.strategy_name,
            tokens_used=tracker.usage.total,
            latency_seconds=round(tracker.latency_seconds, 2),
        )
