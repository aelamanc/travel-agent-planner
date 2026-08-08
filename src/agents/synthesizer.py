"""Synthesizer: emits the final itinerary via the same ITINERARY_TOOL_SCHEMA
every other strategy uses, so eval scoring is unchanged."""

import json

from ..llm_loop import ITINERARY_TOOL_SCHEMA, run_tool_loop
from ..token_tracker import TokenUsage
from .contracts import ConstraintSet, DomainFindings

SYSTEM_PROMPT = (
    "You are the synthesizer on a travel-planning team. Combine the supervisor's "
    "constraints and each domain specialist's findings into one complete travel "
    "itinerary by calling finish_itinerary. If a domain's findings are empty or carry "
    "warnings, say so explicitly in natural_language_summary — never invent data for "
    "a domain that came back empty."
)


async def synthesize(
    constraints: ConstraintSet,
    findings: list[DomainFindings],
    client,
    model: str,
    max_tokens: int = 4096,
) -> tuple[dict, TokenUsage]:
    findings_text = json.dumps([f.model_dump() for f in findings], indent=2, default=str)
    user_content = (
        f"Constraints:\n{constraints.model_dump_json(indent=2)}\n\n"
        f"Domain findings:\n{findings_text}"
    )
    result = await run_tool_loop(
        client=client,
        model=model,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        tools=[ITINERARY_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "finish_itinerary"},
        single_shot=True,
        max_tokens=max_tokens,
        temperature=0,
    )
    return result.forced_tool_input, result.usage
