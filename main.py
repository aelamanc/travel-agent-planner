"""Entrypoint: run a single example query through the ReAct strategy."""

import argparse
import json

from dotenv import load_dotenv

load_dotenv()

from src.tools import create_tool_registry
from src.strategies.react import ReActStrategy


def main():
    parser = argparse.ArgumentParser(description="Run a travel planning query")
    parser.add_argument(
        "--mode", choices=["mock", "live"], default="mock",
        help="Tool data mode: 'mock' for hardcoded data, 'live' for real APIs (default: mock)",
    )
    args = parser.parse_args()

    tools = create_tool_registry(mode=args.mode)
    strategy = ReActStrategy(tools=tools, model="gpt-4o")

    query = (
        "Plan a 5-day trip to Paris from New York (JFK), June 15-20, 2025. "
        "My budget is $2000 total. I love museums and food."
    )

    print(f"Query: {query}\n")
    print(f"Strategy: {strategy.strategy_name}")
    print(f"Mode: {args.mode}")
    print(f"Tools: {[t.name for t in tools]}")
    print("-" * 60)

    result = strategy.run(query)

    print(f"\nDestination: {result.destination}")
    print(f"Dates: {result.travel_dates[0]} to {result.travel_dates[1]}")
    print(f"Strategy: {result.strategy_used}")
    print(f"Tokens used: {result.tokens_used}")
    print(f"Latency: {result.latency_seconds}s")
    print(f"Total estimated cost: ${result.total_estimated_cost:.2f}")

    print(f"\nFlights ({len(result.flights)}):")
    for f in result.flights:
        print(f"  {f.airline} {f.flight_number}: ${f.price:.0f}")

    print(f"\nHotel: {result.hotel.name}")
    print(f"  ${result.hotel.price_per_night}/night, rating {result.hotel.rating}")
    print(f"  Total: ${result.hotel.total_price:.2f}")

    print(f"\nDaily Plan ({len(result.daily_plan)} days):")
    for day in result.daily_plan:
        print(f"  {day.date} — {day.weather}")
        for a in day.attractions:
            print(f"    - {a.name} ({a.category}, ${a.price:.0f})")
        print(f"    Est. cost: ${day.estimated_cost:.0f}")

    print(f"\nWeather: {result.weather_summary}")
    print(f"\n{'='*60}")
    print(result.natural_language_summary)

    # Also dump full JSON for inspection
    with open("results/last_run.json", "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    print("\nFull result saved to results/last_run.json")


if __name__ == "__main__":
    main()
