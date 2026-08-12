"""Run the full evaluation harness across all strategies and scenarios."""

import argparse
import asyncio
import os
import sys

from anthropic import AnthropicError
from dotenv import load_dotenv

load_dotenv()

from src.agents.cache import TTLCache
from src.agents.mcp_session_manager import MCPSessionManager
from src.anthropic_client import DEFAULT_MODEL
from src.baseline import ZeroShotBaseline
from src.evaluation.harness import run_evaluation
from src.evaluation.run_summary import write_run_summary
from src.evaluation.scenarios import SCENARIOS
from src.strategies.orchestrated import OrchestratedStrategy
from src.strategies.plan_execute import PlanExecuteStrategy
from src.strategies.react import ReActStrategy
from src.strategies.self_critique import SelfCritiqueStrategy
from src.token_tracker import RunSpendTracker
from src.tools import create_tool_registry

ALL_STRATEGY_NAMES = ["react", "plan", "critique", "baseline", "orchestrated"]


def _build_strategies(selected, args, tools, mcp_manager, cache):
    builders = {
        "react": lambda: ReActStrategy(tools=tools, model=args.model),
        "plan": lambda: PlanExecuteStrategy(tools=tools, model=args.model),
        "critique": lambda: SelfCritiqueStrategy(tools=tools, model=args.model),
        "baseline": lambda: ZeroShotBaseline(model=args.model),
        "orchestrated": lambda: OrchestratedStrategy(
            mcp_manager=mcp_manager, cache=cache, model=args.model
        ),
    }
    return [builders[name]() for name in selected]


async def main():
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument(
        "--mode", choices=["mock", "live"], default="mock",
        help="Tool data mode: 'mock' or 'live' (default: mock)",
    )
    parser.add_argument(
        "--strategy", choices=["all", *ALL_STRATEGY_NAMES],
        default="all",
        help="Which strategy to evaluate (default: all)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Anthropic model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Run only the first N scenarios. Useful for smoke tests.",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the confirmation prompt before a full-scenario Sonnet run.",
    )
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "Missing ANTHROPIC_API_KEY. Copy .env.example to .env and add an Anthropic API key.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Cost discipline: default to Haiku + --limit 4 for iteration. A full
    # 40-scenario run on Sonnet is real money — confirm before doing it.
    if "sonnet" in args.model.lower() and args.limit is None and not args.yes:
        answer = input(
            f"About to run the FULL scenario set on {args.model} with no --limit — "
            f"this is a real-cost run. Continue? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Aborted.")
            sys.exit(0)

    tools = create_tool_registry(mode=args.mode)
    scenarios = SCENARIOS[:args.limit] if args.limit else None
    selected = ALL_STRATEGY_NAMES if args.strategy == "all" else [args.strategy]
    spend_tracker = RunSpendTracker()

    try:
        if "orchestrated" in selected:
            async with MCPSessionManager(mode=args.mode) as mcp_manager:
                cache = TTLCache()
                strategies = _build_strategies(selected, args, tools, mcp_manager, cache)
                csv_path = await run_evaluation(
                    strategies, scenarios=scenarios, spend_tracker=spend_tracker
                )
                n_scenarios = len(scenarios) if scenarios is not None else len(SCENARIOS)
                write_run_summary(mcp_manager, cache, n_scenarios * len(strategies))
        else:
            strategies = _build_strategies(selected, args, tools, None, None)
            csv_path = await run_evaluation(
                strategies, scenarios=scenarios, spend_tracker=spend_tracker
            )
    except AnthropicError as e:
        print(f"\nAnthropic API request failed: {e}", file=sys.stderr)
        print(
            "Check your ANTHROPIC_API_KEY, network access, account billing, and model access.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nDone. Results at: {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
