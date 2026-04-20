"""Flight search tool — mock data + Amadeus API live mode."""

import os
from typing import Any

import requests

from .base import BaseTool

# ── Mock data ────────────────────────────────────────────────────────

MOCK_FLIGHTS: dict[str, list[dict]] = {
    "PAR": [
        {
            "airline": "Air France",
            "flight_number": "AF123",
            "origin": "JFK",
            "destination": "CDG",
            "departure_time": "2025-06-15T18:30:00",
            "arrival_time": "2025-06-16T07:45:00",
            "price": 485.00,
            "duration_hours": 7.25,
            "stops": 0,
        },
        {
            "airline": "Delta",
            "flight_number": "DL441",
            "origin": "JFK",
            "destination": "CDG",
            "departure_time": "2025-06-15T21:00:00",
            "arrival_time": "2025-06-16T10:30:00",
            "price": 420.00,
            "duration_hours": 7.5,
            "stops": 0,
        },
        {
            "airline": "United",
            "flight_number": "UA887",
            "origin": "JFK",
            "destination": "CDG",
            "departure_time": "2025-06-15T16:00:00",
            "arrival_time": "2025-06-16T08:15:00",
            "price": 550.00,
            "duration_hours": 10.25,
            "stops": 1,
        },
    ],
    "TYO": [
        {
            "airline": "ANA",
            "flight_number": "NH109",
            "origin": "JFK",
            "destination": "NRT",
            "departure_time": "2025-06-15T11:00:00",
            "arrival_time": "2025-06-16T14:00:00",
            "price": 890.00,
            "duration_hours": 14.0,
            "stops": 0,
        },
        {
            "airline": "Japan Airlines",
            "flight_number": "JL5",
            "origin": "JFK",
            "destination": "HND",
            "departure_time": "2025-06-15T13:30:00",
            "arrival_time": "2025-06-16T16:45:00",
            "price": 820.00,
            "duration_hours": 14.25,
            "stops": 0,
        },
        {
            "airline": "Delta",
            "flight_number": "DL173",
            "origin": "JFK",
            "destination": "NRT",
            "departure_time": "2025-06-15T17:00:00",
            "arrival_time": "2025-06-17T06:30:00",
            "price": 650.00,
            "duration_hours": 18.5,
            "stops": 1,
        },
    ],
    "ROM": [
        {
            "airline": "ITA Airways",
            "flight_number": "AZ611",
            "origin": "JFK",
            "destination": "FCO",
            "departure_time": "2025-06-15T17:45:00",
            "arrival_time": "2025-06-16T08:00:00",
            "price": 410.00,
            "duration_hours": 8.25,
            "stops": 0,
        },
        {
            "airline": "Lufthansa",
            "flight_number": "LH405",
            "origin": "JFK",
            "destination": "FCO",
            "departure_time": "2025-06-15T19:00:00",
            "arrival_time": "2025-06-16T12:30:00",
            "price": 380.00,
            "duration_hours": 11.5,
            "stops": 1,
        },
    ],
}

DEFAULT_FLIGHTS = [
    {
        "airline": "American Airlines",
        "flight_number": "AA100",
        "origin": "JFK",
        "destination": "UNKNOWN",
        "departure_time": "2025-06-15T08:00:00",
        "arrival_time": "2025-06-15T14:00:00",
        "price": 350.00,
        "duration_hours": 6.0,
        "stops": 0,
    },
    {
        "airline": "United",
        "flight_number": "UA200",
        "origin": "JFK",
        "destination": "UNKNOWN",
        "departure_time": "2025-06-15T12:00:00",
        "arrival_time": "2025-06-15T20:00:00",
        "price": 275.00,
        "duration_hours": 8.0,
        "stops": 1,
    },
]

# ── IATA code mapping ────────────────────────────────────────────────

CITY_TO_IATA = {
    "paris": "CDG", "cdg": "CDG",
    "tokyo": "NRT", "nrt": "NRT", "hnd": "HND",
    "rome": "FCO", "fco": "FCO",
    "new york": "JFK", "jfk": "JFK",
    "los angeles": "LAX", "lax": "LAX",
    "chicago": "ORD", "ord": "ORD",
    "london": "LHR", "lhr": "LHR",
    "san francisco": "SFO", "sfo": "SFO",
    "miami": "MIA", "mia": "MIA",
    "boston": "BOS", "bos": "BOS",
}


def _normalize_destination(destination: str) -> str:
    mapping = {
        "paris": "PAR", "cdg": "PAR", "par": "PAR",
        "tokyo": "TYO", "nrt": "TYO", "hnd": "TYO", "tyo": "TYO",
        "rome": "ROM", "fco": "ROM", "rom": "ROM",
    }
    return mapping.get(destination.lower().strip(), "DEFAULT")


def _to_iata(city_or_code: str) -> str:
    """Best-effort conversion of city name to IATA code."""
    key = city_or_code.lower().strip()
    if key in CITY_TO_IATA:
        return CITY_TO_IATA[key]
    # If already looks like a code (3 uppercase letters), use as-is
    if len(city_or_code.strip()) == 3 and city_or_code.strip().isalpha():
        return city_or_code.strip().upper()
    return city_or_code.strip().upper()[:3]


class SearchFlightsTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_flights"

    @property
    def description(self) -> str:
        return (
            "Search for available flights between an origin and destination "
            "on a given date. Optionally filter by maximum price."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Departure city or airport code (e.g. 'JFK', 'New York')",
                },
                "destination": {
                    "type": "string",
                    "description": "Arrival city or airport code (e.g. 'Paris', 'CDG')",
                },
                "date": {
                    "type": "string",
                    "description": "Travel date in YYYY-MM-DD format",
                },
                "max_price": {
                    "type": "number",
                    "description": "Maximum ticket price in USD (optional)",
                },
            },
            "required": ["origin", "destination", "date"],
        }

    # ── Mock ─────────────────────────────────────────────────────────

    def _run_mock(self, **kwargs: Any) -> dict:
        destination = kwargs["destination"]
        max_price = kwargs.get("max_price")

        key = _normalize_destination(destination)
        if key == "DEFAULT":
            flights = [
                {**f, "destination": destination} for f in DEFAULT_FLIGHTS
            ]
        else:
            flights = MOCK_FLIGHTS[key]

        origin = kwargs.get("origin", "JFK")
        date = kwargs["date"]
        results = []
        for f in flights:
            flight = {**f, "origin": origin}
            flight["departure_time"] = date + flight["departure_time"][10:]
            if max_price is not None and flight["price"] > max_price:
                continue
            results.append(flight)

        return {"flights": results, "count": len(results)}

    # ── Live (Amadeus API) ───────────────────────────────────────────

    def _get_amadeus_token(self) -> str:
        """Authenticate with Amadeus and return an access token."""
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

        origin_code = _to_iata(kwargs["origin"])
        dest_code = _to_iata(kwargs["destination"])
        date = kwargs["date"]
        max_price = kwargs.get("max_price")

        params = {
            "originLocationCode": origin_code,
            "destinationLocationCode": dest_code,
            "departureDate": date,
            "adults": 1,
            "max": 5,
            "currencyCode": "USD",
        }
        if max_price is not None:
            params["maxPrice"] = int(max_price)

        resp = requests.get(
            "https://test.api.amadeus.com/v2/shopping/flight-offers",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        results = []
        for offer in data:
            seg = offer["itineraries"][0]["segments"]
            first_seg = seg[0]
            last_seg = seg[-1]

            # Parse duration like "PT7H25M"
            duration_str = offer["itineraries"][0]["duration"]
            hours = 0.0
            if "H" in duration_str:
                hours += int(duration_str.split("PT")[1].split("H")[0])
            if "M" in duration_str:
                mins_part = duration_str.split("H")[-1] if "H" in duration_str else duration_str.split("PT")[1]
                if "M" in mins_part:
                    hours += int(mins_part.replace("M", "")) / 60

            results.append({
                "airline": first_seg["carrierCode"],
                "flight_number": first_seg["carrierCode"] + first_seg["number"],
                "origin": first_seg["departure"]["iataCode"],
                "destination": last_seg["arrival"]["iataCode"],
                "departure_time": first_seg["departure"]["at"],
                "arrival_time": last_seg["arrival"]["at"],
                "price": float(offer["price"]["total"]),
                "duration_hours": round(hours, 2),
                "stops": len(seg) - 1,
            })

        return {"flights": results, "count": len(results)}
