"""One-row-per-eval-run companion CSV for MCP server startup + tool
discovery time.

These aren't a per-scenario cost — servers spawn once for the whole eval
run — so they don't belong as a repeated value on every `orchestrated` row
in the main results CSV (that would imply a per-scenario cost that doesn't
exist). This file is only written when `orchestrated` was part of the run.
"""

import csv
import os
from datetime import datetime

from ..agents.cache import TTLCache
from ..agents.mcp_session_manager import MCPSessionManager

FIELDNAMES = [
    "run_timestamp",
    "mode",
    "server_startup_seconds",
    "tool_discovery_seconds",
    "total_scenarios_run",
    "overall_cache_hit_rate",
]


def write_run_summary(
    mcp_manager: MCPSessionManager,
    cache: TTLCache,
    total_scenarios_run: int,
    output_dir: str = "results",
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"mcp_run_summary_{timestamp}.csv")

    row = {
        "run_timestamp": timestamp,
        "mode": mcp_manager.mode,
        "server_startup_seconds": round(mcp_manager.startup_time_seconds, 3),
        "tool_discovery_seconds": round(mcp_manager.tool_discovery_seconds, 3),
        "total_scenarios_run": total_scenarios_run,
        "overall_cache_hit_rate": round(cache.hit_rate, 4),
    }

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerow(row)

    print(f"MCP run summary written to {csv_path}")
    return csv_path
