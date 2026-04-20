"""Hotel search tool — mock data + Amadeus API live mode."""

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

# Amadeus city codes for hotel search
CITY_CODES = {
    "paris": "PAR", "tokyo": "TYO", "rome": "ROM",
    "london": "LON", "new york": "NYC", "los angeles": "LAX",
}


def _normalize(destination: str) -> str:
    mapping = {
        "paris": "paris", "cdg": "paris", "par": "paris",
        "tokyo": "tokyo", "nrt": "tokyo", "hnd": "tokyo", "tyo": "tokyo",
        "rome": "rome", "fco": "rome", "rom": "rome",
    }
    return mapping.get(destination.lower().strip(), "default")


def _to_city_code(destination: str) -> str:
    key = destination.lower().strip()
    if key in CITY_CODES:
        return CITY_CODES[key]
    if len(destination.strip()) == 3 and destination.strip().isalpha():
        return destination.strip().upper()
    return destination.strip().upper()[:3]


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

    # ── Live (Amadeus API) ───────────────────────────────────────────

    def _get_amadeus_token(self) -> str:
        resp = requests.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": os.environ["AMADEUS_API_KEY"],
                "client_secret": os.environ["AMADEUS_API_SECRET"],
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _run_live(self, **kwargs: Any) -> dict:
        token = self._get_amadeus_token()

        destination = kwargs["destination"]
        check_in = kwargs["check_in"]
        check_out = kwargs["check_out"]
        max_price = kwargs.get("max_price_per_night")

        ci = dt_date.fromisoformat(check_in)
        co = dt_date.fromisoformat(check_out)
        nights = max((co - ci).days, 1)

        city_code = _to_city_code(destination)

        # Step 1: Get hotel IDs by city
        resp = requests.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city",
            headers={"Authorization": f"Bearer {token}"},
            params={"cityCode": city_code, "radius": 10, "radiusUnit": "KM"},
        )
        resp.raise_for_status()
        hotel_ids = [h["hotelId"] for h in resp.json().get("data", [])][:10]

        if not hotel_ids:
            return {"hotels": [], "count": 0}

        # Step 2: Get offers for those hotels
        resp = requests.get(
            "https://test.api.amadeus.com/v3/shopping/hotel-offers",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "hotelIds": ",".join(hotel_ids),
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "adults": 1,
                "currency": "USD",
            },
        )
        resp.raise_for_status()

        results = []
        for hotel_data in resp.json().get("data", []):
            hotel_info = hotel_data.get("hotel", {})
            offer = hotel_data.get("offers", [{}])[0]
            price_total = float(offer.get("price", {}).get("total", 0))
            ppn = round(price_total / nights, 2) if nights > 0 else price_total

            if max_price is not None and ppn > max_price:
                continue

            results.append({
                "name": hotel_info.get("name", "Unknown Hotel"),
                "address": hotel_info.get("address", {}).get("lines", [""])[0],
                "price_per_night": ppn,
                "rating": float(hotel_info.get("rating", 0)),
                "amenities": hotel_data.get("amenities", []),
                "check_in": check_in,
                "check_out": check_out,
                "nights": nights,
                "total_price": price_total,
            })

        return {"hotels": results[:5], "count": min(len(results), 5)}
