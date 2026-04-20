"""Zero-shot baseline: single LLM call with no tool use."""

import json
import time

from openai import OpenAI

from .models import ItineraryResult

SYSTEM_PROMPT = """\
You are a travel planning assistant. Given a user's travel request, produce a \
complete travel itinerary as a JSON object with the following fields:
- destination (string)
- start_date (string YYYY-MM-DD)
- end_date (string YYYY-MM-DD)
- selected_flight (object with: airline, flight_number, origin, destination, departure_time, arrival_time, price, duration_hours, stops)
- selected_hotel (object with: name, address, price_per_night, rating, amenities, total_price)
- daily_plan (array of objects, each with: date, weather, attractions (array of objects with name, category, rating, price, description, duration_hours), meals (array of strings), estimated_cost)
- weather_summary (string)
- total_estimated_cost (number)
- natural_language_summary (string)

Return ONLY valid JSON, no markdown fences or extra text.
"""


class ZeroShotBaseline:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.client = OpenAI()

    @property
    def strategy_name(self) -> str:
        return "zero_shot_baseline"

    def run(self, query: str) -> ItineraryResult:
        start_time = time.time()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
        )

        total_tokens = response.usage.total_tokens
        raw = json.loads(response.choices[0].message.content)
        latency = time.time() - start_time

        # Normalize the response into ItineraryResult
        flight = raw.get("selected_flight", {})
        hotel = raw.get("selected_hotel", {})
        daily_plan = raw.get("daily_plan", [])

        if "total_price" not in hotel:
            nights = len(daily_plan) or 1
            hotel["total_price"] = hotel.get("price_per_night", 0) * nights

        return ItineraryResult(
            destination=raw.get("destination", "unknown"),
            travel_dates=(
                raw.get("start_date", ""),
                raw.get("end_date", ""),
            ),
            flights=[flight] if flight else [],
            hotel=hotel,
            daily_plan=daily_plan,
            weather_summary=raw.get("weather_summary", ""),
            total_estimated_cost=raw.get("total_estimated_cost", 0),
            natural_language_summary=raw.get("natural_language_summary", ""),
            strategy_used=self.strategy_name,
            tokens_used=total_tokens,
            latency_seconds=round(latency, 2),
        )
