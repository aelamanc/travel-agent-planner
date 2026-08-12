"""Supervisor: parses the request into structured constraints and delegates.
Holds no travel tools itself — no MCP session, no real tool calls."""

from ..llm_loop import run_tool_loop
from ..token_tracker import TokenUsage
from .contracts import ConstraintSet

CONSTRAINT_TOOL_SCHEMA = {
    "name": "extract_constraints",
    "description": "Extract structured travel constraints from the user's request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": "Departure city/airport, default JFK if not stated",
            },
            "destinations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "One or more destination cities, in order",
            },
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "budget_total": {
                "type": ["number", "null"],
                "description": "Total trip budget in USD, if stated",
            },
            "budget_currency": {"type": "string"},
            "party_size": {"type": "integer"},
            "preferences": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Interest categories, e.g. museum, food, landmark",
            },
        },
        "required": ["origin", "destinations", "start_date", "end_date"],
    },
}

SYSTEM_PROMPT = (
    "You are the supervisor on a travel-planning team. Parse the user's request into "
    "structured constraints for the domain specialists (flights, lodging, experiences) "
    "to work from. You do not search for travel data yourself — you only extract and "
    "structure what the user asked for, then call extract_constraints."
)


async def parse_constraints(
    query: str, client, model: str, max_tokens: int = 512
) -> tuple[ConstraintSet, TokenUsage]:
    result = await run_tool_loop(
        client=client,
        model=model,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
        tools=[CONSTRAINT_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "extract_constraints"},
        single_shot=True,
        max_tokens=max_tokens,
    )
    data = result.forced_tool_input
    constraints = ConstraintSet(
        origin=data.get("origin") or "JFK",
        destinations=[d for d in data.get("destinations", []) if d] or ["Paris"],
        start_date=data.get("start_date", ""),
        end_date=data.get("end_date", ""),
        budget_total=data.get("budget_total"),
        budget_currency=data.get("budget_currency") or "USD",
        party_size=data.get("party_size") or 1,
        preferences=data.get("preferences", []),
        raw_query=query,
    )
    return constraints, result.usage
