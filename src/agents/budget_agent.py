"""Budget agent: validates the assembled plan against a Python-computed cost.

The LLM is never asked to compute or restate the cost, and never decides
accept/reject — both are plain Python. Its one conditional call (made only
when the Python check finds the plan over budget) authors *just* a
ReallocationDirective: which domain(s) should search again, and how.
"""

from ..llm_loop import run_tool_loop
from ..token_tracker import TokenUsage
from .contracts import BudgetVerdict, ConstraintSet, DomainFindings, ReallocationDirective

DIRECTIVE_TOOL_SCHEMA = {
    "name": "reallocate",
    "description": "Decide which domain(s) need to revise their pick to fit the budget, and how.",
    "input_schema": {
        "type": "object",
        "properties": {
            "target_domains": {
                "type": "array",
                "items": {"type": "string", "enum": ["flights", "lodging", "experiences"]},
                "description": "Which domain(s) should search again with tighter constraints",
            },
            "reason": {"type": "string"},
            "violated_constraint": {"type": "string"},
            "guidance": {
                "type": "string",
                "description": "Specific instruction for the re-invoked agent(s)",
            },
        },
        "required": ["target_domains", "reason", "violated_constraint", "guidance"],
    },
}

SYSTEM_PROMPT = (
    "You are the budget reviewer on a travel-planning team. A trip has already been "
    "confirmed over budget by exact arithmetic — you don't need to (and shouldn't try "
    "to) recompute the cost. Given the total cost, the budget limit, and each domain's "
    "findings, decide which domain(s) should search again with tighter constraints, "
    "and give them specific, actionable guidance."
)


def compute_total_cost(findings: list[DomainFindings]) -> float:
    """Sum the plan's cost from raw tool-call results in Python — never the LLM's job.

    Takes the cheapest option each domain agent actually saw for each
    search it made (one term per `search_flights`/`search_hotels` call
    captured in `DomainFindings.structured["tool_calls"]`).
    """
    total = 0.0
    for finding in findings:
        for call in finding.structured.get("tool_calls", []):
            result = call.get("result") or {}
            tool = call.get("tool")
            if tool == "search_flights":
                flights = result.get("flights") or []
                if flights:
                    total += min(f.get("price", 0.0) for f in flights)
            elif tool == "search_hotels":
                hotels = result.get("hotels") or []
                if hotels:
                    total += min(h.get("total_price", 0.0) for h in hotels)
    return total


async def evaluate_budget(
    constraints: ConstraintSet,
    findings: list[DomainFindings],
    client,
    model: str,
    max_tokens: int = 512,
) -> tuple[BudgetVerdict, TokenUsage]:
    total_cost = compute_total_cost(findings)
    accepted = constraints.budget_total is None or total_cost <= constraints.budget_total

    if accepted:
        return BudgetVerdict(accepted=True, total_estimated_cost=total_cost), TokenUsage()

    findings_text = "\n".join(
        f"- {f.domain}: {f.summary or '(no summary)'} (warnings: {f.warnings or 'none'})"
        for f in findings
    )
    user_content = (
        f"Total estimated cost: ${total_cost:.2f}\n"
        f"Budget limit: ${constraints.budget_total:.2f}\n\n"
        f"Findings:\n{findings_text}"
    )
    result = await run_tool_loop(
        client=client,
        model=model,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        tools=[DIRECTIVE_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "reallocate"},
        single_shot=True,
        max_tokens=max_tokens,
        temperature=0,
    )
    data = result.forced_tool_input
    directive = ReallocationDirective(
        target_domains=data["target_domains"],
        reason=data["reason"],
        violated_constraint=data["violated_constraint"],
        guidance=data["guidance"],
    )
    verdict = BudgetVerdict(accepted=False, total_estimated_cost=total_cost, directive=directive)
    return verdict, result.usage
