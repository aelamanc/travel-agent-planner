"""Attractions tool — mock data + Google Places API live mode."""

import os
from typing import Any

import requests

from .base import BaseTool

# ── Mock data ────────────────────────────────────────────────────────

MOCK_ATTRACTIONS: dict[str, list[dict]] = {
    "paris": [
        {"name": "Eiffel Tower", "category": "landmark", "rating": 4.7, "price": 26.0, "description": "Iconic iron lattice tower with city views from three levels.", "duration_hours": 2.5},
        {"name": "Louvre Museum", "category": "museum", "rating": 4.8, "price": 17.0, "description": "World's largest art museum, home to the Mona Lisa.", "duration_hours": 3.5},
        {"name": "Notre-Dame Cathedral", "category": "landmark", "rating": 4.6, "price": 0.0, "description": "Medieval Catholic cathedral, a masterpiece of French Gothic architecture.", "duration_hours": 1.5},
        {"name": "Montmartre & Sacre-Coeur", "category": "neighborhood", "rating": 4.5, "price": 0.0, "description": "Hilltop artists' quarter with stunning basilica and panoramic views.", "duration_hours": 2.0},
        {"name": "Musee d'Orsay", "category": "museum", "rating": 4.7, "price": 16.0, "description": "Impressionist and post-impressionist masterpieces in a former railway station.", "duration_hours": 2.5},
        {"name": "Le Marais Food Tour", "category": "food", "rating": 4.6, "price": 45.0, "description": "Guided walking tour through Le Marais with tastings at local shops.", "duration_hours": 3.0},
        {"name": "Seine River Cruise", "category": "tour", "rating": 4.4, "price": 15.0, "description": "One-hour cruise past major Paris landmarks.", "duration_hours": 1.0},
        {"name": "Palace of Versailles", "category": "landmark", "rating": 4.6, "price": 21.0, "description": "Opulent royal chateau with vast gardens just outside Paris.", "duration_hours": 4.0},
    ],
    "tokyo": [
        {"name": "Senso-ji Temple", "category": "landmark", "rating": 4.6, "price": 0.0, "description": "Tokyo's oldest temple in the heart of Asakusa.", "duration_hours": 1.5},
        {"name": "Meiji Shrine", "category": "landmark", "rating": 4.7, "price": 0.0, "description": "Serene Shinto shrine set in a lush forested park.", "duration_hours": 1.5},
        {"name": "Tsukiji Outer Market", "category": "food", "rating": 4.5, "price": 0.0, "description": "Vibrant market with fresh sushi, street food, and kitchen goods.", "duration_hours": 2.0},
        {"name": "TeamLab Borderless", "category": "museum", "rating": 4.8, "price": 32.0, "description": "Immersive digital art museum with interactive installations.", "duration_hours": 2.5},
        {"name": "Shibuya Crossing & Hachiko", "category": "landmark", "rating": 4.3, "price": 0.0, "description": "World's busiest pedestrian crossing and the famous dog statue.", "duration_hours": 0.5},
        {"name": "Akihabara Electric Town", "category": "shopping", "rating": 4.2, "price": 0.0, "description": "Electronics, anime, and manga district.", "duration_hours": 2.0},
        {"name": "Ramen Street (Tokyo Station)", "category": "food", "rating": 4.4, "price": 12.0, "description": "Underground alley with eight top ramen shops.", "duration_hours": 1.0},
        {"name": "Shinjuku Gyoen", "category": "park", "rating": 4.7, "price": 5.0, "description": "Beautiful national garden blending Japanese, English, and French styles.", "duration_hours": 2.0},
    ],
    "rome": [
        {"name": "Colosseum", "category": "landmark", "rating": 4.7, "price": 18.0, "description": "Ancient amphitheater and icon of Imperial Rome.", "duration_hours": 2.0},
        {"name": "Vatican Museums & Sistine Chapel", "category": "museum", "rating": 4.8, "price": 17.0, "description": "Vast art collection culminating in Michelangelo's ceiling frescoes.", "duration_hours": 3.5},
        {"name": "Pantheon", "category": "landmark", "rating": 4.8, "price": 5.0, "description": "Remarkably preserved Roman temple with a stunning domed ceiling.", "duration_hours": 1.0},
        {"name": "Trastevere Food Walk", "category": "food", "rating": 4.6, "price": 40.0, "description": "Evening stroll through Rome's foodie neighborhood with tastings.", "duration_hours": 3.0},
        {"name": "Roman Forum", "category": "landmark", "rating": 4.5, "price": 18.0, "description": "Ruins of ancient government buildings at the heart of Rome.", "duration_hours": 2.0},
        {"name": "Trevi Fountain", "category": "landmark", "rating": 4.6, "price": 0.0, "description": "Baroque masterpiece; toss a coin to ensure your return to Rome.", "duration_hours": 0.5},
    ],
}

DEFAULT_ATTRACTIONS = [
    {"name": "City Walking Tour", "category": "tour", "rating": 4.3, "price": 25.0, "description": "Guided walking tour of major city highlights.", "duration_hours": 3.0},
    {"name": "Local Food Market", "category": "food", "rating": 4.1, "price": 0.0, "description": "Explore local cuisine and street food.", "duration_hours": 2.0},
    {"name": "National Museum", "category": "museum", "rating": 4.4, "price": 15.0, "description": "Major museum showcasing national art and history.", "duration_hours": 2.5},
]

# Foursquare category IDs mapped to our labels
FSQ_CATEGORY_MAP = {
    10000: "museum",
    10027: "museum",
    10004: "landmark",
    16000: "landmark",
    16032: "park",
    13000: "food",
    17000: "shopping",
    19000: "tour",
}

# Map preference categories to Foursquare category IDs
PREF_TO_FSQ_CATEGORY = {
    "museum": "10027",
    "landmark": "16000",
    "food": "13000",
    "park": "16032",
    "shopping": "17000",
    "tour": "19000",
    "neighborhood": "16000",
}


def _normalize(destination: str) -> str:
    mapping = {
        "paris": "paris", "cdg": "paris",
        "tokyo": "tokyo", "nrt": "tokyo", "hnd": "tokyo",
        "rome": "rome", "fco": "rome",
    }
    return mapping.get(destination.lower().strip(), "default")


class GetAttractionsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_attractions"

    @property
    def description(self) -> str:
        return (
            "Get attraction and activity recommendations for a destination, "
            "optionally filtered by preference categories."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "City name (e.g. 'Paris', 'Tokyo')",
                },
                "preferences": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of interest categories to filter by (e.g. ['museum', 'food', 'landmark']). Optional.",
                },
            },
            "required": ["destination"],
        }

    # ── Mock ─────────────────────────────────────────────────────────

    def _run_mock(self, **kwargs: Any) -> dict:
        destination = kwargs["destination"]
        preferences = kwargs.get("preferences", [])

        key = _normalize(destination)
        attractions = MOCK_ATTRACTIONS.get(key, DEFAULT_ATTRACTIONS)

        if preferences:
            prefs_lower = [p.lower() for p in preferences]
            filtered = [
                a for a in attractions
                if a["category"].lower() in prefs_lower
            ]
            if filtered:
                attractions = filtered

        return {"attractions": attractions, "count": len(attractions)}

    # ── Live (Foursquare Places API) ─────────────────────────────────
    # Uses the new places-api.foursquare.com domain (post-2025 migration)

    def _run_live(self, **kwargs: Any) -> dict:
        destination = kwargs["destination"]
        preferences = kwargs.get("preferences", [])
        api_key = os.environ["FOURSQUARE_API_KEY"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "X-Places-Api-Version": "2025-06-17",
        }

        # Build category filter from preferences
        if preferences:
            category_ids = []
            for pref in preferences:
                cat_id = PREF_TO_FSQ_CATEGORY.get(pref.lower())
                if cat_id and cat_id not in category_ids:
                    category_ids.append(cat_id)
            categories_param = ",".join(category_ids) if category_ids else None
        else:
            categories_param = None

        params = {
            "near": destination,
            "limit": 15,
            "sort": "POPULARITY",
        }
        if categories_param:
            params["fsq_category_ids"] = categories_param

        resp = requests.get(
            "https://places-api.foursquare.com/places/search",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()

        results = []
        seen_names = set()

        for place in resp.json().get("results", []):
            name = place.get("name", "Unknown")
            if name in seen_names:
                continue
            seen_names.add(name)

            category = "landmark"
            for cat in place.get("categories", []):
                mapped = FSQ_CATEGORY_MAP.get(cat.get("id", 0))
                if mapped:
                    category = mapped
                    break

            raw_rating = place.get("rating", 0) or 0
            rating = round(raw_rating / 2, 1)

            location = place.get("location", {})
            address = location.get("formatted_address") or location.get("address", "")

            results.append({
                "name": name,
                "category": category,
                "rating": rating,
                "price": 0.0,
                "description": address,
                "duration_hours": 2.0,
            })

        if not results:
            return {"attractions": DEFAULT_ATTRACTIONS, "count": len(DEFAULT_ATTRACTIONS)}

        return {"attractions": results, "count": len(results)}
