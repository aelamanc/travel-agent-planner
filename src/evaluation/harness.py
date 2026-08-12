"""Evaluation harness: runs all strategies across all scenarios and outputs CSV."""

import csv
import json
import os
from datetime import datetime

from ..models import ItineraryResult
from ..token_tracker import RunSpendTracker, TokenUsage
from .metrics import score_result
from .scenarios import SCENARIOS

FIELDNAMES = [
    "scenario_id",
    "category",
    "strategy",
    "goal_completion",
    "constraint_satisfaction",
    "latency_seconds",
    "tokens_used",
    "total_estimated_cost",
    # Added for the Anthropic/MCP migration. Blank/0 for the four control
    # strategies — only `orchestrated` sets `strategy.last_run_stats`.
    "total_input_tokens",
    "total_output_tokens",
    "per_agent_tokens",
    "delegation_count",
    "replan_count",
    "cache_hit_rate",
    "serial_equivalent_seconds",
    "mcp_round_trip_seconds",
    "agent_reasoning_seconds",
]


def _empty_orchestration_fields() -> dict:
    """Blank/0 for the orchestrated-only columns — used for control-strategy
    rows and the except-block fallback, so every row has every key
    `csv.DictWriter` expects regardless of which strategy produced it."""
    return {
        "per_agent_tokens": "",
        "delegation_count": 0,
        "replan_count": 0,
        "cache_hit_rate": 0.0,
        "serial_equivalent_seconds": 0.0,
        "mcp_round_trip_seconds": 0.0,
        "agent_reasoning_seconds": 0.0,
    }


def _instrumentation_fields(strategy, usage: TokenUsage | None) -> dict:
    row = {
        "total_input_tokens": usage.input_tokens if usage else 0,
        "total_output_tokens": usage.output_tokens if usage else 0,
        **_empty_orchestration_fields(),
    }
    stats = getattr(strategy, "last_run_stats", None)
    if stats is not None:
        row["per_agent_tokens"] = json.dumps(
            {
                name: {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}
                for name, u in stats.per_agent_usage.items()
            }
        )
        row["delegation_count"] = stats.delegation_count
        row["replan_count"] = stats.replan_count
        row["cache_hit_rate"] = stats.cache_hit_rate
        row["serial_equivalent_seconds"] = stats.serial_equivalent_seconds
        row["mcp_round_trip_seconds"] = stats.mcp_round_trip_seconds
        row["agent_reasoning_seconds"] = stats.agent_reasoning_seconds
    return row


async def run_evaluation(
    strategies: list,
    scenarios: list[dict] | None = None,
    output_dir: str = "results",
    spend_tracker: RunSpendTracker | None = None,
) -> str:
    """Run all strategy x scenario combinations and write results to CSV.

    Args:
        strategies: List of strategy instances (each with an async .run() method).
        scenarios: Scenario dicts to evaluate. Defaults to all SCENARIOS.
        output_dir: Directory to write the CSV file.
        spend_tracker: If given, its cumulative input/output token total is
            printed to stdout after each successfully-scored scenario.

    Returns:
        Path to the output CSV file.
    """
    if scenarios is None:
        scenarios = SCENARIOS

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    strategy_tag = "_".join(s.strategy_name for s in strategies)
    csv_path = os.path.join(output_dir, f"eval_{strategy_tag}_{timestamp}.csv")

    results: list[dict] = []

    for strategy in strategies:
        print(f"\n{'='*60}")
        print(f"Strategy: {strategy.strategy_name}")
        print(f"{'='*60}")

        for scenario in scenarios:
            print(f"  Running: {scenario['id']}...", end=" ", flush=True)

            try:
                result: ItineraryResult = await strategy.run(scenario["query"])
                scores = score_result(result, scenario)
                usage = getattr(strategy, "last_run_usage", None)
                scores.update(_instrumentation_fields(strategy, usage))
                results.append(scores)
                print(
                    f"OK (goal={scores['goal_completion']:.0%}, "
                    f"constraints={scores['constraint_satisfaction']:.0%}, "
                    f"{scores['latency_seconds']:.1f}s)"
                )
                if spend_tracker is not None and usage is not None:
                    spend_tracker.add(usage)
            except Exception as e:
                print(f"FAILED: {e}")
                results.append({
                    "scenario_id": scenario["id"],
                    "category": scenario["category"],
                    "strategy": strategy.strategy_name,
                    "goal_completion": 0.0,
                    "constraint_satisfaction": 0.0,
                    "latency_seconds": 0.0,
                    "tokens_used": 0,
                    "total_estimated_cost": 0.0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    **_empty_orchestration_fields(),
                })

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults written to {csv_path}")
    return csv_path
