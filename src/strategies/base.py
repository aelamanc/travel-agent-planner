"""Base strategy interface that all reasoning strategies implement."""

from abc import ABC, abstractmethod

from ..anthropic_client import DEFAULT_MODEL, get_async_client
from ..models import ItineraryResult
from ..tools.base import BaseTool


class BaseStrategy(ABC):
    """Abstract base class for agent reasoning strategies."""

    def __init__(self, tools: list[BaseTool] | None = None, model: str = DEFAULT_MODEL):
        tools = tools or []
        self.tools = {tool.name: tool for tool in tools}
        self.tool_list = tools
        self.model = model
        self.client = get_async_client()

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Human-readable name for this strategy."""
        ...

    @abstractmethod
    async def run(self, query: str) -> ItineraryResult:
        """Execute the strategy on a user query and return an itinerary."""
        ...

    def _get_anthropic_tools(self) -> list[dict]:
        """Get all tools in Anthropic tool-use format."""
        return [tool.to_anthropic_tool() for tool in self.tool_list]

    def _execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """Look up and execute a tool by name."""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}
        return self.tools[tool_name].run(**arguments)
