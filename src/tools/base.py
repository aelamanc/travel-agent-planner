"""Base tool interface that all tools implement."""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all travel planner tools."""

    def __init__(self, mode: str = "mock"):
        if mode not in ("mock", "live"):
            raise ValueError(f"Tool mode must be 'mock' or 'live', got '{mode}'")
        self.mode = mode

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calling."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description shown to the LLM."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """JSON Schema for the tool's parameters."""
        ...

    def run(self, **kwargs: Any) -> dict:
        """Execute the tool — dispatches to mock or live implementation."""
        if self.mode == "live":
            return self._run_live(**kwargs)
        return self._run_mock(**kwargs)

    @abstractmethod
    def _run_mock(self, **kwargs: Any) -> dict:
        """Execute with hardcoded mock data."""
        ...

    @abstractmethod
    def _run_live(self, **kwargs: Any) -> dict:
        """Execute with real API calls."""
        ...

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function-calling tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
