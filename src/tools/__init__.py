from .flights import SearchFlightsTool
from .hotels import SearchHotelsTool
from .weather import GetWeatherTool
from .attractions import GetAttractionsTool


def create_tool_registry(mode: str = "mock") -> list:
    """Create all tools in the given mode ('mock' or 'live')."""
    return [
        SearchFlightsTool(mode=mode),
        SearchHotelsTool(mode=mode),
        GetWeatherTool(mode=mode),
        GetAttractionsTool(mode=mode),
    ]


# Default registry for backward compatibility
TOOL_REGISTRY: list = create_tool_registry("mock")
