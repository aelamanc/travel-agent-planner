"""Evaluation harness: runs all strategies across all scenarios and outputs CSV."""

import csv
import os
from datetime import datetime

from ..models import ItineraryResult
from .metrics import score_result
from .scenarios import SCENARIOS


def run_evaluation(
    strategies: list,
    scenarios: list[dict] | None = None,
    output_dir: str = "results",
) -> str:
    """Run all strategy x scenario combinations and write results to CSV.

    Args:
        strategies: List of strategy instances (each with a .run() method).
        scenarios: Scenario dicts to evaluate. Defaults to all SCENARIOS.
        output_dir: Directory to write the CSV file.

    Returns:
        Path to the output CSV file.
    """
    if scenarios is None:
        scenarios = SCENARIOS

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"eval_{timestamp}.csv")

    fieldnames = [
        "scenario_id",
        "category",
        "strategy",
        "goal_completion",
        "constraint_satisfaction",
        "latency_seconds",
        "tokens_used",
        "total_estimated_cost",
    ]

    results: list[dict] = []

    for strategy in strategies:
        print(f"\n{'='*60}")
        print(f"Strategy: {strategy.strategy_name}")
        print(f"{'='*60}")

        for scenario in scenarios:
            print(f"  Running: {scenario['id']}...", end=" ", flush=True)

            try:
                result: ItineraryResult = strategy.run(scenario["query"])
                scores = score_result(result, scenario)
                results.append(scores)
                print(
                    f"OK (goal={scores['goal_completion']:.0%}, "
                    f"constraints={scores['constraint_satisfaction']:.0%}, "
                    f"{scores['latency_seconds']:.1f}s)"
                )
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
                })

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults written to {csv_path}")
    return csv_path
