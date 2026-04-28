"""Run the full evaluation harness across all strategies and scenarios."""

import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAIError

load_dotenv()

from src.tools import create_tool_registry
from src.strategies.react import ReActStrategy
from src.strategies.plan_execute import PlanExecuteStrategy
from src.strategies.self_critique import SelfCritiqueStrategy
from src.baseline import ZeroShotBaseline
from src.evaluation.harness import run_evaluation
from src.evaluation.scenarios import SCENARIOS


def main():
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument(
        "--mode", choices=["mock", "live"], default="mock",
        help="Tool data mode: 'mock' or 'live' (default: mock)",
    )
    parser.add_argument(
        "--strategy", choices=["all", "react", "plan", "critique", "baseline"],
        default="all",
        help="Which strategy to evaluate (default: all)",
    )
    parser.add_argument(
        "--model", default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Run only the first N scenarios. Useful for smoke tests.",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Missing OPENAI_API_KEY. Copy .env.example to .env and add an OpenAI API key.",
            file=sys.stderr,
        )
        sys.exit(1)

    tools = create_tool_registry(mode=args.mode)

    all_strategies = {
        "react": ReActStrategy(tools=tools, model=args.model),
        "plan": PlanExecuteStrategy(tools=tools, model=args.model),
        "critique": SelfCritiqueStrategy(tools=tools, model=args.model),
        "baseline": ZeroShotBaseline(model=args.model),
    }

    if args.strategy == "all":
        strategies = list(all_strategies.values())
    else:
        strategies = [all_strategies[args.strategy]]

    scenarios = SCENARIOS[:args.limit] if args.limit else None

    try:
        csv_path = run_evaluation(strategies, scenarios=scenarios)
    except OpenAIError as e:
        print(f"\nOpenAI API request failed: {e}", file=sys.stderr)
        print(
            "Check your OPENAI_API_KEY, network access, account billing, and model access.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"\nDone. Results at: {csv_path}")


if __name__ == "__main__":
    main()
