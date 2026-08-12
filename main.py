"""Entrypoint: run a single travel planning query through a chosen strategy."""

import argparse
import asyncio
import json
import os
import sys

from anthropic import AnthropicError
from dotenv import load_dotenv

load_dotenv()

from src.agents.cache import TTLCache
from src.agents.mcp_session_manager import MCPSessionManager
from src.anthropic_client import DEFAULT_MODEL
from src.baseline import ZeroShotBaseline
from src.strategies.orchestrated import OrchestratedStrategy
from src.strategies.plan_execute import PlanExecuteStrategy
from src.strategies.react import ReActStrategy
from src.strategies.self_critique import SelfCritiqueStrategy
from src.tools import create_tool_registry


async def main():
    parser = argparse.ArgumentParser(description="Run a travel planning query")
    parser.add_argument(
        "--mode", choices=["mock", "live"], default="mock",
        help="Tool data mode: 'mock' or 'live' (default: mock)",
    )
    parser.add_argument(
        "--strategy", choices=["react", "plan", "critique", "baseline", "orchestrated"],
        default="react",
        help="Reasoning strategy to use (default: react)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Anthropic model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--query",
        default=(
            "Plan a 5-day trip to Paris from New York (JFK), June 15-20, 2026. "
            "My budget is $2000 total. I love museums and food."
        ),
        help="Travel request to plan. If omitted, a Paris sample query is used.",
    )
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "Missing ANTHROPIC_API_KEY. Copy .env.example to .env and add an Anthropic API key.",
            file=sys.stderr,
        )
        sys.exit(1)

    query = args.query
    print(f"Query: {query}\n")
    print(f"Strategy: {args.strategy}")
    print(f"Mode: {args.mode}")
    print("-" * 60)

    try:
        if args.strategy == "orchestrated":
            async with MCPSessionManager(mode=args.mode) as mcp_manager:
                cache = TTLCache()
                strategy = OrchestratedStrategy(
                    mcp_manager=mcp_manager, cache=cache, model=args.model
                )
                result = await strategy.run(query)
        else:
            tools = create_tool_registry(mode=args.mode)
            strategies = {
                "react": ReActStrategy(tools=tools, model=args.model),
                "plan": PlanExecuteStrategy(tools=tools, model=args.model),
                "critique": SelfCritiqueStrategy(tools=tools, model=args.model),
                "baseline": ZeroShotBaseline(model=args.model),
            }
            strategy = strategies[args.strategy]
            result = await strategy.run(query)
    except AnthropicError as e:
        print(f"\nAnthropic API request failed: {e}", file=sys.stderr)
        print(
            "Check your ANTHROPIC_API_KEY, network access, account billing, and model access.",
            file=sys.stderr,
        )
        sys.exit(1)

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

    os.makedirs("results", exist_ok=True)
    with open("results/last_run.json", "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    print("\nFull result saved to results/last_run.json")


if __name__ == "__main__":
    asyncio.run(main())
