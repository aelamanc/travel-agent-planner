"""Plan-then-Execute strategy: generate full plan upfront, execute sequentially."""

import json
import time

from openai import OpenAI

from ..models import ItineraryResult
from ..tools.base import BaseTool
from .base import BaseStrategy

# TODO: Define PLANNING_SYSTEM_PROMPT — instruct the LLM to output a JSON plan
#       listing tool calls in order: [{"tool": "search_flights", "args": {...}}, ...]
PLANNING_SYSTEM_PROMPT = """\
You are a travel planning assistant. Given a user's travel request, produce a \
step-by-step plan of tool calls needed to gather all information for a complete \
itinerary. Output ONLY a JSON array of steps, each with "tool" and "args" keys.

Available tools and their parameters:
- search_flights: origin, destination, date, max_price (optional)
- search_hotels: destination, check_in, check_out, max_price_per_night (optional)
- get_weather: destination, start_date, end_date
- get_attractions: destination, preferences (optional list)

Example output:
[
  {"tool": "search_flights", "args": {"origin": "JFK", "destination": "Paris", "date": "2025-06-15"}},
  {"tool": "search_hotels", "args": {"destination": "Paris", "check_in": "2025-06-15", "check_out": "2025-06-20"}},
  ...
]
"""

# TODO: Define SYNTHESIS_SYSTEM_PROMPT — instruct the LLM to combine all tool
#       results into a final itinerary JSON matching the ItineraryResult schema.
SYNTHESIS_SYSTEM_PROMPT = """\
You are a travel planning assistant. You have been given the results of several \
tool calls. Combine them into a complete travel itinerary. Return a JSON object with:
- destination, start_date, end_date
- selected_flight (best option), return_flight (if applicable)
- selected_hotel (best option)
- daily_plan (array of day objects with date, weather, attractions, meals, estimated_cost)
- weather_summary
- total_estimated_cost
- natural_language_summary
"""


class PlanExecuteStrategy(BaseStrategy):
    def __init__(self, tools: list[BaseTool], model: str = "gpt-4o"):
        super().__init__(tools, model)
        self.client = OpenAI()

    @property
    def strategy_name(self) -> str:
        return "plan_then_execute"

    def run(self, query: str) -> ItineraryResult:
        start_time = time.time()
        total_tokens = 0

        # --- Phase 1: Generate plan ---
        # TODO: Call self.client.chat.completions.create with PLANNING_SYSTEM_PROMPT
        #       Parse the JSON array of tool calls from the response.
        #       Track tokens in total_tokens.
        plan = []  # TODO: replace with parsed plan

        # --- Phase 2: Execute plan ---
        # TODO: Loop over the plan steps, calling self._execute_tool for each.
        #       Collect results into a list of {"tool": ..., "args": ..., "result": ...}.
        tool_results = []  # TODO: replace with actual results

        # --- Phase 3: Synthesize itinerary ---
        # TODO: Call self.client.chat.completions.create with SYNTHESIS_SYSTEM_PROMPT,
        #       passing tool_results as context.
        #       Parse the JSON response into an ItineraryResult.
        #       Track tokens in total_tokens.

        latency = time.time() - start_time

        # TODO: Return a real ItineraryResult built from the synthesis response.
        raise NotImplementedError("PlanExecuteStrategy.run() not yet implemented")
