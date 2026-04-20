"""ReAct strategy: interleaved think-act-observe loop."""

import json
import time

from openai import OpenAI

from ..models import ItineraryResult
from ..tools.base import BaseTool
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
- Respect any budget constraints the user mentions.
- Pick the best flight and hotel based on the user's preferences and constraints.
- Create a day-by-day plan using the attractions and weather data.
- Include estimated costs for each day.
"""

FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish_itinerary",
        "description": (
            "Call this when you have all the information needed to produce "
            "the final travel itinerary. Pass the complete itinerary data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "selected_flight": {
                    "type": "object",
                    "description": "The chosen flight option",
                    "properties": {
                        "airline": {"type": "string"},
                        "flight_number": {"type": "string"},
                        "origin": {"type": "string"},
                        "destination": {"type": "string"},
                        "departure_time": {"type": "string"},
                        "arrival_time": {"type": "string"},
                        "price": {"type": "number"},
                        "duration_hours": {"type": "number"},
                        "stops": {"type": "integer"},
                    },
                },
                "return_flight": {
                    "type": "object",
                    "description": "The chosen return flight (optional)",
                    "properties": {
                        "airline": {"type": "string"},
                        "flight_number": {"type": "string"},
                        "origin": {"type": "string"},
                        "destination": {"type": "string"},
                        "departure_time": {"type": "string"},
                        "arrival_time": {"type": "string"},
                        "price": {"type": "number"},
                        "duration_hours": {"type": "number"},
                        "stops": {"type": "integer"},
                    },
                },
                "selected_hotel": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "address": {"type": "string"},
                        "price_per_night": {"type": "number"},
                        "rating": {"type": "number"},
                        "amenities": {"type": "array", "items": {"type": "string"}},
                        "total_price": {"type": "number"},
                    },
                },
                "daily_plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "weather": {"type": "string"},
                            "attractions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "category": {"type": "string"},
                                        "rating": {"type": "number"},
                                        "price": {"type": "number"},
                                        "description": {"type": "string"},
                                        "duration_hours": {"type": "number"},
                                    },
                                },
                            },
                            "meals": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "estimated_cost": {"type": "number"},
                        },
                    },
                },
                "weather_summary": {"type": "string"},
                "total_estimated_cost": {"type": "number"},
                "natural_language_summary": {"type": "string"},
            },
            "required": [
                "destination",
                "start_date",
                "end_date",
                "selected_flight",
                "selected_hotel",
                "daily_plan",
                "weather_summary",
                "total_estimated_cost",
                "natural_language_summary",
            ],
        },
    },
}

MAX_ITERATIONS = 15


class ReActStrategy(BaseStrategy):
    def __init__(self, tools: list[BaseTool], model: str = "gpt-4o"):
        super().__init__(tools, model)
        self.client = OpenAI()

    @property
    def strategy_name(self) -> str:
        return "react"

    def run(self, query: str) -> ItineraryResult:
        start_time = time.time()
        total_tokens = 0

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        openai_tools = self._get_openai_tools() + [FINISH_TOOL]

        for _ in range(MAX_ITERATIONS):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
            )

            msg = response.choices[0].message
            total_tokens += response.usage.total_tokens

            # Append assistant message to conversation
            messages.append(msg)

            # If no tool calls, the model is done talking (shouldn't happen
            # before finish_itinerary, but handle gracefully)
            if not msg.tool_calls:
                break

            # Process each tool call
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                if fn_name == "finish_itinerary":
                    # Build and return the final itinerary
                    latency = time.time() - start_time
                    return self._build_result(fn_args, total_tokens, latency)

                # Execute the real tool
                result = self._execute_tool(fn_name, fn_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

        # If we exhaust iterations, return whatever we have
        latency = time.time() - start_time
        return self._build_fallback(query, total_tokens, latency)

    def _build_result(
        self, data: dict, tokens: int, latency: float
    ) -> ItineraryResult:
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
            tokens_used=tokens,
            latency_seconds=round(latency, 2),
        )

    def _build_fallback(
        self, query: str, tokens: int, latency: float
    ) -> ItineraryResult:
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
            tokens_used=tokens,
            latency_seconds=round(latency, 2),
        )
