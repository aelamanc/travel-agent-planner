"""MCP server exposing search_flights, wrapping SearchFlightsTool."""

from mcp.server.mcpserver import MCPServer

from src.mcp_servers.common import run_tool, tool_mode
from src.tools.flights import SearchFlightsTool

mcp = MCPServer("flights")
_tool = SearchFlightsTool(mode=tool_mode())


@mcp.tool(name=_tool.name, description=_tool.description)
def search_flights(
    origin: str, destination: str, date: str, max_price: float | None = None
) -> dict:
    return run_tool(
        _tool, origin=origin, destination=destination, date=date, max_price=max_price
    )


if __name__ == "__main__":
    mcp.run()
