"""Base strategy interface that all reasoning strategies implement."""

from abc import ABC, abstractmethod

from ..models import ItineraryResult
from ..tools.base import BaseTool


class BaseStrategy(ABC):
    """Abstract base class for agent reasoning strategies."""

    def __init__(self, tools: list[BaseTool], model: str = "gpt-4o"):
        self.tools = {tool.name: tool for tool in tools}
        self.tool_list = tools
        self.model = model

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Human-readable name for this strategy."""
        ...

    @abstractmethod
    def run(self, query: str) -> ItineraryResult:
        """Execute the strategy on a user query and return an itinerary."""
        ...

    def _get_openai_tools(self) -> list[dict]:
        """Get all tools in OpenAI function-calling format."""
        return [tool.to_openai_tool() for tool in self.tool_list]

    def _execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """Look up and execute a tool by name."""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}
        return self.tools[tool_name].run(**arguments)
