"""Pydantic models for the travel itinerary planner."""

from pydantic import BaseModel


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


class HotelOption(BaseModel):
    name: str
    address: str
    price_per_night: float
    rating: float
    amenities: list[str]
    total_price: float


class Attraction(BaseModel):
    name: str
    category: str
    rating: float
    price: float
    description: str
    duration_hours: float


class DayPlan(BaseModel):
    date: str
    weather: str
    attractions: list[Attraction]
    meals: list[str]
    estimated_cost: float


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
