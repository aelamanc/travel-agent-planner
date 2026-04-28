"""Evaluation metrics for scoring itinerary results."""

from ..models import ItineraryResult


def _result_search_text(result: ItineraryResult) -> str:
    """Flatten user-facing result fields for simple constraint checks."""
    parts = [
        result.destination,
        result.weather_summary,
        result.natural_language_summary,
    ]
    for day in result.daily_plan:
        parts.extend([day.date, day.weather, " ".join(day.meals)])
        for attraction in day.attractions:
            parts.extend([
                attraction.name,
                attraction.category,
                attraction.description,
            ])
    return " ".join(parts).lower()


def goal_completion_score(result: ItineraryResult, expected_fields: list[str]) -> float:
    """Score 0-1: what fraction of expected fields are present and non-empty."""
    if not expected_fields:
        return 1.0

    checks = {
        "flights": len(result.flights) > 0,
        "hotel": result.hotel.name not in ("", "N/A"),
        "daily_plan": len(result.daily_plan) > 0,
        "weather_summary": len(result.weather_summary) > 0,
    }

    passed = sum(1 for f in expected_fields if checks.get(f, False))
    return passed / len(expected_fields)


def constraint_satisfaction_score(result: ItineraryResult, constraints: dict) -> float:
    """Score 0-1: what fraction of constraints are satisfied."""
    if not constraints:
        return 1.0

    checks = []

    if "max_total_budget" in constraints:
        checks.append(result.total_estimated_cost <= constraints["max_total_budget"])

    if "max_flight_price" in constraints:
        for flight in result.flights:
            checks.append(flight.price <= constraints["max_flight_price"])

    if "max_hotel_per_night" in constraints:
        checks.append(
            result.hotel.price_per_night <= constraints["max_hotel_per_night"]
        )

    if "cities" in constraints:
        text = _result_search_text(result)
        checks.append(
            all(city.lower() in text for city in constraints["cities"])
        )

    # Preference checks — just verify daily_plan has attractions matching categories
    if "preferences" in constraints:
        pref_cats = {p.lower() for p in constraints["preferences"]}
        found_cats = set()
        for day in result.daily_plan:
            for attraction in day.attractions:
                found_cats.add(attraction.category.lower())
        overlap = pref_cats & found_cats
        checks.append(len(overlap) > 0)

    if not checks:
        return 1.0
    return sum(1 for c in checks if c) / len(checks)


def score_result(result: ItineraryResult, scenario: dict) -> dict:
    """Compute all metrics for a single result + scenario pair."""
    return {
        "scenario_id": scenario["id"],
        "category": scenario["category"],
        "strategy": result.strategy_used,
        "goal_completion": goal_completion_score(
            result, scenario["expected_fields"]
        ),
        "constraint_satisfaction": constraint_satisfaction_score(
            result, scenario["constraints"]
        ),
        "latency_seconds": result.latency_seconds,
        "tokens_used": result.tokens_used,
        "total_estimated_cost": result.total_estimated_cost,
    }
