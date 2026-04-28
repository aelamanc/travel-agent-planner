"""Interactive demo: single ReAct query with live travel data."""

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAIError

load_dotenv()

from src.tools import create_tool_registry
from src.strategies.react import ReActStrategy


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY in .env", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("  Agentic Travel Planner — Live Demo (ReAct + Live APIs)")
    print("=" * 60)
    print()

    try:
        query = input("Enter your travel request: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    if not query:
        query = (
            "Plan a 5-day trip to Paris from JFK, June 15-20, 2026. "
            "Budget $2000 total. I love museums and food."
        )
        print(f"Using default query: {query}")

    print()
    print(f"Planning your trip... (this may take 10-20 seconds)")
    print("-" * 60)

    tools = create_tool_registry(mode="live")
    strategy = ReActStrategy(tools=tools, model="gpt-4o")

    try:
        result = strategy.run(query)
    except OpenAIError as e:
        print(f"\nOpenAI API error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n  Destination : {result.destination}")
    print(f"  Dates       : {result.travel_dates[0]} to {result.travel_dates[1]}")
    print(f"  Total cost  : ${result.total_estimated_cost:.0f}")
    print(f"  Tokens used : {result.tokens_used}  |  Latency: {result.latency_seconds}s")

    print(f"\nFlight")
    for f in result.flights:
        print(f"  {f.airline} {f.flight_number}  {f.origin} → {f.destination}")
        print(f"  Departs {f.departure_time}  |  {f.duration_hours}h  |  ${f.price:.0f}")

    print(f"\nHotel: {result.hotel.name}")
    print(f"  {result.hotel.address}")
    print(f"  ${result.hotel.price_per_night:.0f}/night  |  Rating {result.hotel.rating}  |  Total ${result.hotel.total_price:.0f}")

    print(f"\nDaily Plan")
    for day in result.daily_plan:
        print(f"\n  {day.date}  —  {day.weather}")
        for a in day.attractions:
            print(f"    • {a.name}  ({a.category})  ${a.price:.0f}  ~{a.duration_hours}h")
        for meal in day.meals:
            print(f"    {meal}")
        print(f"    Day estimate: ${day.estimated_cost:.0f}")

    print(f"\nWeather: {result.weather_summary}")

    print(f"\n{'=' * 60}")
    print(result.natural_language_summary)
    print("=" * 60)

    os.makedirs("results", exist_ok=True)
    out_path = "results/demo_last_run.json"
    with open(out_path, "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    print(f"\nFull result saved to {out_path}")


if __name__ == "__main__":
    main()
