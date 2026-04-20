"""Run the full evaluation harness across all strategies and scenarios."""

import argparse

from dotenv import load_dotenv

load_dotenv()

from src.tools import create_tool_registry
from src.strategies.react import ReActStrategy
# from src.strategies.plan_execute import PlanExecuteStrategy
# from src.strategies.self_critique import SelfCritiqueStrategy
# from src.baseline import ZeroShotBaseline
from src.evaluation.harness import run_evaluation


def main():
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument(
        "--mode", choices=["mock", "live"], default="mock",
        help="Tool data mode: 'mock' or 'live' (default: mock)",
    )
    args = parser.parse_args()

    tools = create_tool_registry(mode=args.mode)

    strategies = [
        ReActStrategy(tools=tools, model="gpt-4o"),
        # Uncomment as you implement:
        # PlanExecuteStrategy(tools=tools, model="gpt-4o"),
        # SelfCritiqueStrategy(tools=tools, model="gpt-4o"),
        # ZeroShotBaseline(model="gpt-4o"),
    ]

    csv_path = run_evaluation(strategies)
    print(f"\nDone. Results at: {csv_path}")


if __name__ == "__main__":
    main()
