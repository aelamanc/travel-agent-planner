"""MCP server exposing get_weather + get_attractions, wrapping the matching
BaseTool subclasses. Also hosts one MCP resource and one MCP prompt so the
project covers more than tool calling.
"""

import json

from mcp.server.mcpserver import MCPServer

from src.mcp_servers.common import run_tool, tool_mode
from src.tools.attractions import MOCK_ATTRACTIONS, GetAttractionsTool
from src.tools.weather import MOCK_WEATHER, GetWeatherTool

mcp = MCPServer("places")
_weather_tool = GetWeatherTool(mode=tool_mode())
_attractions_tool = GetAttractionsTool(mode=tool_mode())


@mcp.tool(name=_weather_tool.name, description=_weather_tool.description)
def get_weather(destination: str, start_date: str, end_date: str) -> dict:
    return run_tool(
        _weather_tool, destination=destination, start_date=start_date, end_date=end_date
    )


@mcp.tool(name=_attractions_tool.name, description=_attractions_tool.description)
def get_attractions(destination: str, preferences: list[str] | None = None) -> dict:
    return run_tool(_attractions_tool, destination=destination, preferences=preferences)


@mcp.resource("travel://destinations")
def destinations() -> str:
    """Cities with hardcoded mock coverage, so a caller can check before spending a tool call."""
    cities = sorted(set(MOCK_WEATHER.keys()) | set(MOCK_ATTRACTIONS.keys()))
    return json.dumps({"destinations": cities, "source": "mock_fixture"})


@mcp.prompt()
def experience_search_strategy(city: str, preferences: str = "") -> str:
    """Search-strategy guidance for an experiences domain agent working one city."""
    prefs = preferences or "no stated preferences"
    return (
        f"Plan your experiences research for {city}. First call get_weather to "
        f"decide an indoor/outdoor mix for the trip dates. Then call get_attractions "
        f"filtered by these preferences: {prefs}. Stay within your tool-call budget — "
        f"don't call either tool more than once per city unless the first result is "
        f"empty or clearly insufficient."
    )


if __name__ == "__main__":
    mcp.run()
