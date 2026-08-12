"""MCP server exposing search_hotels, wrapping SearchHotelsTool."""

from mcp.server.mcpserver import MCPServer

from src.mcp_servers.common import run_tool, tool_mode
from src.tools.hotels import SearchHotelsTool

mcp = MCPServer("lodging")
_tool = SearchHotelsTool(mode=tool_mode())


@mcp.tool(name=_tool.name, description=_tool.description)
def search_hotels(
    destination: str,
    check_in: str,
    check_out: str,
    max_price_per_night: float | None = None,
) -> dict:
    return run_tool(
        _tool,
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        max_price_per_night=max_price_per_night,
    )


if __name__ == "__main__":
    mcp.run()
