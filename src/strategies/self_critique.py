"""Self-Critique strategy: gather all data, draft, critique, then refine."""

import json
import time

from openai import OpenAI

from ..models import ItineraryResult
from ..tools.base import BaseTool
from .base import BaseStrategy

DRAFT_SYSTEM_PROMPT = """\
You are a travel planning assistant. You have gathered data from several tools. \
Using this data, create a complete travel itinerary as a JSON object with:
- destination, start_date, end_date
- selected_flight, return_flight (if applicable)
- selected_hotel
- daily_plan (array with date, weather, attractions, meals, estimated_cost)
- weather_summary, total_estimated_cost, natural_language_summary
"""

# TODO: Define CRITIQUE_SYSTEM_PROMPT — instruct the LLM to score the draft
#       itinerary and flag gaps (missing days, budget overruns, unused preferences).
#       Output a JSON object with "score" (1-10), "issues" (list of strings),
#       and "suggestions" (list of strings).
CRITIQUE_SYSTEM_PROMPT = """\
You are a travel itinerary critic. Review the following itinerary draft and the \
original user request. Score the itinerary from 1-10 and identify any issues.

Output a JSON object:
{
  "score": <1-10>,
  "issues": ["issue 1", "issue 2", ...],
  "suggestions": ["suggestion 1", ...]
}

Check for:
- Missing flights, hotel, or daily plans
- Budget constraint violations
- Preference mismatches
- Unrealistic scheduling (too many activities per day)
- Missing weather considerations
"""

# TODO: Define REFINE_SYSTEM_PROMPT — instruct the LLM to fix the draft
#       based on the critique feedback. Output the same itinerary JSON format.
REFINE_SYSTEM_PROMPT = """\
You are a travel planning assistant. Refine the following itinerary based on \
the critique feedback. Fix all identified issues and incorporate suggestions \
where appropriate. Return the improved itinerary in the same JSON format.
"""


class SelfCritiqueStrategy(BaseStrategy):
    def __init__(self, tools: list[BaseTool], model: str = "gpt-4o"):
        super().__init__(tools, model)
        self.client = OpenAI()

    @property
    def strategy_name(self) -> str:
        return "self_critique"

    def run(self, query: str) -> ItineraryResult:
        start_time = time.time()
        total_tokens = 0

        # --- Phase 1: Gather all tool data ---
        # TODO: Parse the query to extract destination, dates, budget, preferences.
        #       Call ALL four tools (can be sequential for now; parallel is a bonus).
        #       Collect results into a dict keyed by tool name.
        tool_results = {}  # TODO: replace with actual tool call results

        # --- Phase 2: Draft itinerary ---
        # TODO: Call self.client.chat.completions.create with DRAFT_SYSTEM_PROMPT,
        #       passing tool_results and the original query as context.
        #       Parse the JSON response. Track tokens.
        draft = {}  # TODO: replace with parsed draft

        # --- Phase 3: Critique ---
        # TODO: Call self.client.chat.completions.create with CRITIQUE_SYSTEM_PROMPT,
        #       passing the draft and the original query.
        #       Parse the critique JSON. Track tokens.
        critique = {}  # TODO: replace with parsed critique

        # --- Phase 4: Refine ---
        # TODO: Call self.client.chat.completions.create with REFINE_SYSTEM_PROMPT,
        #       passing the draft, critique, and original query.
        #       Parse the refined itinerary JSON. Track tokens.
        #       Build and return an ItineraryResult.

        latency = time.time() - start_time

        # TODO: Return a real ItineraryResult built from the refined itinerary.
        raise NotImplementedError("SelfCritiqueStrategy.run() not yet implemented")
