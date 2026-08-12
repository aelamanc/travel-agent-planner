"""Shared glue for MCP server wrappers around BaseTool instances."""

import os

from src.tools.base import BaseTool

MCP_TOOL_MODE_ENV = "MCP_TOOL_MODE"


def tool_mode() -> str:
    """Read the mock/live toggle for this server process from the environment.

    Read once at server import time (not per call) — each server process is
    long-lived, so its tool instances are constructed once with this mode.
    """
    mode = os.environ.get(MCP_TOOL_MODE_ENV, "mock")
    if mode not in ("mock", "live"):
        raise ValueError(f"{MCP_TOOL_MODE_ENV} must be 'mock' or 'live', got {mode!r}")
    return mode


def run_tool(tool: BaseTool, **kwargs) -> dict:
    """Execute a BaseTool and return its result dict unchanged.

    Mock/live dispatch, mock-fallback tagging (`mode`, `live_error`), and
    per-tool normalization all already live in `BaseTool.run()` — this is
    the only thing every MCP tool function in this package calls.
    """
    return tool.run(**kwargs)
