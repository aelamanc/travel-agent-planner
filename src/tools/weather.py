"""Weather forecast tool — mock data + OpenWeatherMap live mode."""

import os
from datetime import datetime
from typing import Any

import requests

from .base import BaseTool

# ── Mock data ────────────────────────────────────────────────────────

MOCK_WEATHER: dict[str, dict] = {
    "paris": {
        "city": "Paris",
        "country": "FR",
        "forecast": [
            {"date": "2025-06-15", "temp_high_c": 24, "temp_low_c": 15, "condition": "Partly Cloudy", "humidity": 55, "wind_kph": 12},
            {"date": "2025-06-16", "temp_high_c": 26, "temp_low_c": 16, "condition": "Sunny", "humidity": 45, "wind_kph": 8},
            {"date": "2025-06-17", "temp_high_c": 22, "temp_low_c": 14, "condition": "Light Rain", "humidity": 72, "wind_kph": 18},
            {"date": "2025-06-18", "temp_high_c": 25, "temp_low_c": 16, "condition": "Sunny", "humidity": 48, "wind_kph": 10},
            {"date": "2025-06-19", "temp_high_c": 27, "temp_low_c": 17, "condition": "Sunny", "humidity": 42, "wind_kph": 7},
            {"date": "2025-06-20", "temp_high_c": 23, "temp_low_c": 15, "condition": "Overcast", "humidity": 65, "wind_kph": 14},
            {"date": "2025-06-21", "temp_high_c": 21, "temp_low_c": 13, "condition": "Rain", "humidity": 80, "wind_kph": 22},
        ],
        "summary": "Mostly pleasant with highs around 24C. Expect light rain mid-week.",
    },
    "tokyo": {
        "city": "Tokyo",
        "country": "JP",
        "forecast": [
            {"date": "2025-06-15", "temp_high_c": 28, "temp_low_c": 21, "condition": "Humid & Cloudy", "humidity": 78, "wind_kph": 10},
            {"date": "2025-06-16", "temp_high_c": 30, "temp_low_c": 22, "condition": "Partly Cloudy", "humidity": 70, "wind_kph": 8},
            {"date": "2025-06-17", "temp_high_c": 27, "temp_low_c": 20, "condition": "Rain", "humidity": 85, "wind_kph": 15},
            {"date": "2025-06-18", "temp_high_c": 29, "temp_low_c": 22, "condition": "Sunny", "humidity": 65, "wind_kph": 6},
            {"date": "2025-06-19", "temp_high_c": 31, "temp_low_c": 23, "condition": "Sunny", "humidity": 60, "wind_kph": 5},
            {"date": "2025-06-20", "temp_high_c": 26, "temp_low_c": 20, "condition": "Thunderstorm", "humidity": 90, "wind_kph": 25},
            {"date": "2025-06-21", "temp_high_c": 28, "temp_low_c": 21, "condition": "Partly Cloudy", "humidity": 72, "wind_kph": 11},
        ],
        "summary": "Hot and humid, early rainy season. Highs near 29C with afternoon storms possible.",
    },
    "rome": {
        "city": "Rome",
        "country": "IT",
        "forecast": [
            {"date": "2025-06-15", "temp_high_c": 30, "temp_low_c": 19, "condition": "Sunny", "humidity": 40, "wind_kph": 8},
            {"date": "2025-06-16", "temp_high_c": 31, "temp_low_c": 20, "condition": "Sunny", "humidity": 38, "wind_kph": 6},
            {"date": "2025-06-17", "temp_high_c": 32, "temp_low_c": 21, "condition": "Sunny", "humidity": 35, "wind_kph": 5},
            {"date": "2025-06-18", "temp_high_c": 29, "temp_low_c": 19, "condition": "Partly Cloudy", "humidity": 50, "wind_kph": 12},
            {"date": "2025-06-19", "temp_high_c": 28, "temp_low_c": 18, "condition": "Partly Cloudy", "humidity": 52, "wind_kph": 10},
            {"date": "2025-06-20", "temp_high_c": 33, "temp_low_c": 22, "condition": "Sunny", "humidity": 30, "wind_kph": 4},
            {"date": "2025-06-21", "temp_high_c": 34, "temp_low_c": 23, "condition": "Hot & Sunny", "humidity": 28, "wind_kph": 3},
        ],
        "summary": "Hot and dry. Highs around 31C, mostly sunny skies throughout the week.",
    },
}

DEFAULT_WEATHER = {
    "city": "Unknown",
    "country": "XX",
    "forecast": [
        {"date": "2025-06-15", "temp_high_c": 25, "temp_low_c": 16, "condition": "Partly Cloudy", "humidity": 55, "wind_kph": 10},
        {"date": "2025-06-16", "temp_high_c": 26, "temp_low_c": 17, "condition": "Sunny", "humidity": 50, "wind_kph": 8},
        {"date": "2025-06-17", "temp_high_c": 24, "temp_low_c": 15, "condition": "Cloudy", "humidity": 60, "wind_kph": 12},
    ],
    "summary": "Mild conditions expected with highs around 25C.",
}


def _normalize(destination: str) -> str:
    mapping = {
        "paris": "paris", "cdg": "paris",
        "tokyo": "tokyo", "nrt": "tokyo", "hnd": "tokyo",
        "rome": "rome", "fco": "rome",
    }
    return mapping.get(destination.lower().strip(), "default")


class GetWeatherTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "Get weather forecast for a destination over a date range."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "City name (e.g. 'Paris', 'Tokyo')",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start of date range YYYY-MM-DD",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of date range YYYY-MM-DD",
                },
            },
            "required": ["destination", "start_date", "end_date"],
        }

    # ── Mock ─────────────────────────────────────────────────────────

    def _run_mock(self, **kwargs: Any) -> dict:
        destination = kwargs["destination"]
        key = _normalize(destination)
        weather = MOCK_WEATHER.get(key, {**DEFAULT_WEATHER, "city": destination})
        return weather

    # ── Live (OpenWeatherMap 5-day forecast) ─────────────────────────

    def _run_live(self, **kwargs: Any) -> dict:
        destination = kwargs["destination"]
        api_key = os.environ["OPENWEATHER_API_KEY"]

        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": destination,
                "appid": api_key,
                "units": "metric",
                "cnt": 40,  # 5 days of 3-hour intervals
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Group by date, take daily highs/lows
        daily: dict[str, dict] = {}
        for entry in data.get("list", []):
            dt = datetime.fromtimestamp(entry["dt"])
            date_str = dt.strftime("%Y-%m-%d")
            temp = entry["main"]["temp"]
            temp_min = entry["main"]["temp_min"]
            temp_max = entry["main"]["temp_max"]
            condition = entry["weather"][0]["description"].title()

            if date_str not in daily:
                daily[date_str] = {
                    "date": date_str,
                    "temp_high_c": temp_max,
                    "temp_low_c": temp_min,
                    "condition": condition,
                    "humidity": entry["main"]["humidity"],
                    "wind_kph": round(entry["wind"]["speed"] * 3.6, 1),
                }
            else:
                daily[date_str]["temp_high_c"] = max(daily[date_str]["temp_high_c"], temp_max)
                daily[date_str]["temp_low_c"] = min(daily[date_str]["temp_low_c"], temp_min)

        forecast = list(daily.values())
        city_name = data.get("city", {}).get("name", destination)
        country = data.get("city", {}).get("country", "XX")

        avg_high = sum(d["temp_high_c"] for d in forecast) / len(forecast) if forecast else 0
        conditions = [d["condition"] for d in forecast]
        summary = f"Highs around {avg_high:.0f}C. Conditions: {', '.join(set(conditions))}."

        return {
            "city": city_name,
            "country": country,
            "forecast": forecast,
            "summary": summary,
        }
