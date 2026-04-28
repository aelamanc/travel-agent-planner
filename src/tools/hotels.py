"""Hotel search tool — mock data + Booking.com (RapidAPI) live mode."""

import os
from datetime import date as dt_date
from typing import Any

import requests

from .base import BaseTool

# ── Mock data ────────────────────────────────────────────────────────

MOCK_HOTELS: dict[str, list[dict]] = {
    "paris": [
        {
            "name": "Hotel Le Marais",
            "address": "12 Rue de Rivoli, 75004 Paris",
            "price_per_night": 180.00,
            "rating": 4.5,
            "amenities": ["wifi", "breakfast", "air_conditioning", "concierge"],
        },
        {
            "name": "Ibis Styles Montmartre",
            "address": "5 Rue Caulaincourt, 75018 Paris",
            "price_per_night": 95.00,
            "rating": 3.8,
            "amenities": ["wifi", "breakfast"],
        },
        {
            "name": "The Ritz Paris",
            "address": "15 Place Vendome, 75001 Paris",
            "price_per_night": 950.00,
            "rating": 4.9,
            "amenities": ["wifi", "spa", "pool", "restaurant", "concierge", "gym"],
        },
    ],
    "tokyo": [
        {
            "name": "Shinjuku Granbell Hotel",
            "address": "2-14-4 Kabukicho, Shinjuku, Tokyo",
            "price_per_night": 120.00,
            "rating": 4.3,
            "amenities": ["wifi", "laundry", "air_conditioning"],
        },
        {
            "name": "Park Hyatt Tokyo",
            "address": "3-7-1-2 Nishi-Shinjuku, Tokyo",
            "price_per_night": 450.00,
            "rating": 4.8,
            "amenities": ["wifi", "spa", "pool", "restaurant", "gym", "concierge"],
        },
        {
            "name": "Sakura Hotel Jimbocho",
            "address": "2-21-4 Kanda-Jimbocho, Chiyoda, Tokyo",
            "price_per_night": 55.00,
            "rating": 3.6,
            "amenities": ["wifi", "shared_kitchen"],
        },
    ],
    "rome": [
        {
            "name": "Hotel Colosseum",
            "address": "Via Sforza 10, 00184 Rome",
            "price_per_night": 140.00,
            "rating": 4.2,
            "amenities": ["wifi", "breakfast", "terrace"],
        },
        {
            "name": "Roma Luxus Hotel",
            "address": "Via Vittorio Veneto 72, 00187 Rome",
            "price_per_night": 320.00,
            "rating": 4.7,
            "amenities": ["wifi", "spa", "restaurant", "bar", "concierge"],
        },
    ],
}

DEFAULT_HOTELS = [
    {
        "name": "City Center Inn",
        "address": "123 Main Street",
        "price_per_night": 110.00,
        "rating": 4.0,
        "amenities": ["wifi", "breakfast"],
    },
    {
        "name": "Budget Lodge",
        "address": "456 Side Avenue",
        "price_per_night": 65.00,
        "rating": 3.5,
        "amenities": ["wifi"],
    },
]

# Booking.com destination IDs for major cities (from searchDestination endpoint)
DEST_IDS = {
    "paris": "-1456928",
    "tokyo": "-246227",
    "rome": "-126693",
    "london": "-2601889",
    "new york": "20088325",
    "los angeles": "20144463",
    "chicago": "20033173",
    "miami": "20014335",
    "barcelona": "-372490",
    "amsterdam": "-2140479",
}


def _normalize(destination: str) -> str:
    mapping = {
        "paris": "paris", "cdg": "paris", "par": "paris",
        "tokyo": "tokyo", "nrt": "tokyo", "hnd": "tokyo", "tyo": "tokyo",
        "rome": "rome", "fco": "rome", "rom": "rome",
    }
    return mapping.get(destination.lower().strip(), "default")


def _get_dest_id(destination: str, api_key: str) -> str | None:
    """Look up Booking.com destination ID, using cache first then live search."""
    key = destination.lower().strip()
    if key in DEST_IDS:
        return DEST_IDS[key]
    # Fall back to live destination search for unknown cities
    resp = requests.get(
        "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchDestination",
        params={"query": destination},
        headers={
            "x-rapidapi-host": "booking-com15.p.rapidapi.com",
            "x-rapidapi-key": api_key,
        },
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    # Prefer city-type result
    for item in data:
        if item.get("dest_type") == "city":
            return str(item["dest_id"])
    return str(data[0]["dest_id"]) if data else None


class SearchHotelsTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_hotels"

    @property
    def description(self) -> str:
        return (
            "Search for available hotels at a destination for given check-in "
            "and check-out dates. Optionally filter by max price per night."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "City or area to search (e.g. 'Paris', 'Tokyo')",
                },
                "check_in": {
                    "type": "string",
                    "description": "Check-in date YYYY-MM-DD",
                },
                "check_out": {
                    "type": "string",
                    "description": "Check-out date YYYY-MM-DD",
                },
                "max_price_per_night": {
                    "type": "number",
                    "description": "Maximum nightly rate in USD (optional)",
                },
            },
            "required": ["destination", "check_in", "check_out"],
        }

    # ── Mock ─────────────────────────────────────────────────────────

    def _run_mock(self, **kwargs: Any) -> dict:
        destination = kwargs["destination"]
        check_in = kwargs["check_in"]
        check_out = kwargs["check_out"]
        max_price = kwargs.get("max_price_per_night")

        ci = dt_date.fromisoformat(check_in)
        co = dt_date.fromisoformat(check_out)
        nights = max((co - ci).days, 1)

        key = _normalize(destination)
        hotels = MOCK_HOTELS.get(key, DEFAULT_HOTELS)

        results = []
        for h in hotels:
            if max_price is not None and h["price_per_night"] > max_price:
                continue
            results.append({
                **h,
                "check_in": check_in,
                "check_out": check_out,
                "nights": nights,
                "total_price": round(h["price_per_night"] * nights, 2),
            })

        return {"hotels": results, "count": len(results)}

    # ── Live (Booking.com via RapidAPI) ─────────────────────────────

    def _run_live(self, **kwargs: Any) -> dict:
        destination = kwargs["destination"]
        check_in = kwargs["check_in"]
        check_out = kwargs["check_out"]
        max_price = kwargs.get("max_price_per_night")
        api_key = os.environ["RAPIDAPI_KEY"]

        ci = dt_date.fromisoformat(check_in)
        co = dt_date.fromisoformat(check_out)
        nights = max((co - ci).days, 1)

        headers = {
            "x-rapidapi-host": "booking-com15.p.rapidapi.com",
            "x-rapidapi-key": api_key,
        }

        dest_id = _get_dest_id(destination, api_key)
        if not dest_id:
            return self._run_mock(**kwargs)

        resp = requests.get(
            "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchHotels",
            headers=headers,
            params={
                "dest_id": dest_id,
                "search_type": "city",
                "arrival_date": check_in,
                "departure_date": check_out,
                "adults": 1,
                "room_qty": 1,
                "currency_code": "USD",
                "languagecode": "en-us",
                "page_number": 1,
            },
        )
        resp.raise_for_status()

        results = []
        for hotel in resp.json().get("data", {}).get("hotels", []):
            prop = hotel.get("property", {})
            name = prop.get("name", "Unknown Hotel")
            review_score = float(prop.get("reviewScore") or 0) / 2  # convert 10→5 scale
            total_price = float(
                prop.get("priceBreakdown", {}).get("grossPrice", {}).get("value", 0)
            )
            ppn = round(total_price / nights, 2) if nights > 0 else total_price

            if max_price is not None and ppn > max_price:
                continue

            results.append({
                "name": name,
                "address": f"{prop.get('wishlistName', '')}, {destination}".strip(", "),
                "price_per_night": ppn,
                "rating": round(review_score, 1),
                "amenities": [],
                "check_in": check_in,
                "check_out": check_out,
                "nights": nights,
                "total_price": round(total_price, 2),
            })

        if not results:
            return self._run_mock(**kwargs)

        return {"hotels": results[:5], "count": min(len(results), 5)}
