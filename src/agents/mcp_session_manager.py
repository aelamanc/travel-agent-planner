"""Owns the 3 persistent MCP client connections for the orchestrated
strategy — each domain agent gets exactly one, matching the server that
exposes only its domain's tools. Servers spawn once here and the
connections persist for the manager's lifetime; never spawn per call.

Tool schemas come from `list_tools()` at call time, once, here — never
hardcoded in agent code.
"""

import json
import sys
import time
from contextlib import AsyncExitStack

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

_SERVER_MODULES: dict[str, str] = {
    "flights": "src.mcp_servers.flights_server",
    "lodging": "src.mcp_servers.lodging_server",
    "places": "src.mcp_servers.places_server",
}


def mcp_tool_to_anthropic(tool) -> dict:
    """Convert an MCP Tool (from list_tools()) into Anthropic's tool schema shape.

    A near-direct field rename — MCP's `input_schema` (already snake_case in
    this SDK version) maps straight onto Anthropic's `input_schema`.
    """
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.input_schema,
    }


def result_dict(call_tool_result) -> dict:
    """Extract a tool's returned dict from a CallToolResult."""
    if call_tool_result.structured_content is not None:
        return call_tool_result.structured_content
    text = call_tool_result.content[0].text
    return json.loads(text)


class MCPSessionManager:
    """Async context manager owning the flights/lodging/places MCP clients."""

    def __init__(self, mode: str = "mock"):
        self.mode = mode
        self.clients: dict[str, Client] = {}
        self.tools_by_server: dict[str, list[dict]] = {}
        self.startup_time_seconds: float = 0.0
        self.tool_discovery_seconds: float = 0.0
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "MCPSessionManager":
        t0 = time.monotonic()
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        for server_name, module in _SERVER_MODULES.items():
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", module],
                env={"MCP_TOOL_MODE": self.mode},
            )
            client = Client(stdio_client(params))
            await self._stack.enter_async_context(client)
            self.clients[server_name] = client

        self.startup_time_seconds = time.monotonic() - t0

        t1 = time.monotonic()
        for server_name, client in self.clients.items():
            listed = await client.list_tools()
            self.tools_by_server[server_name] = [
                mcp_tool_to_anthropic(t) for t in listed.tools
            ]
        self.tool_discovery_seconds = time.monotonic() - t1

        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(*exc_info)
            self._stack = None
