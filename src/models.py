"""Pydantic models for the travel itinerary planner."""

import re
from pydantic import BaseModel, field_validator


class FlightOption(BaseModel):
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    price: float
    duration_hours: float
    stops: int

    @field_validator("stops", mode="before")
    @classmethod
    def coerce_stops(cls, v):
        if isinstance(v, str):
            low = v.lower()
            if "non" in low or "direct" in low:
                return 0
            m = re.search(r"\d+", v)
            return int(m.group()) if m else 0
        return v if v is not None else 0


class HotelOption(BaseModel):
    name: str
    address: str
    price_per_night: float
    rating: float
    amenities: list[str]
    total_price: float


class Attraction(BaseModel):
    name: str
    category: str = ""
    rating: float = 0.0
    price: float = 0.0
    description: str = ""
    duration_hours: float = 0.0

    @field_validator("rating", "price", "duration_hours", mode="before")
    @classmethod
    def coerce_float(cls, v):
        return 0.0 if v is None else v


class DayPlan(BaseModel):
    date: str
    weather: str
    attractions: list[Attraction]
    meals: list[str]
    estimated_cost: float

    @field_validator("attractions", mode="before")
    @classmethod
    def coerce_attractions(cls, v):
        return [] if v is None else v

    @field_validator("meals", mode="before")
    @classmethod
    def coerce_meals(cls, v):
        if v is None:
            return []
        result = []
        for m in v:
            if isinstance(m, dict):
                result.append(m.get("description") or m.get("name") or str(m))
            else:
                result.append(m)
        return result


class ItineraryResult(BaseModel):
    destination: str
    travel_dates: tuple[str, str]
    flights: list[FlightOption]
    hotel: HotelOption
    daily_plan: list[DayPlan]
    weather_summary: str
    total_estimated_cost: float
    natural_language_summary: str
    strategy_used: str
    tokens_used: int
    latency_seconds: float
