"""Typed message contracts flowing through the orchestrated strategy:

supervisor -> ConstraintSet
    -> asyncio.gather(domain agents) -> list[DomainFindings]
    -> budget check (Python cost, LLM-authored ReallocationDirective only
       when over budget) -> BudgetVerdict
    -> (optional single re-invocation round)
    -> synthesizer -> ItineraryResult (unchanged schema, not part of this module)
"""

from typing import Literal

from pydantic import BaseModel, Field

from ..token_tracker import TokenUsage

Domain = Literal["flights", "lodging", "experiences"]


class ConstraintSet(BaseModel):
    origin: str
    destinations: list[str]
    start_date: str
    end_date: str
    budget_total: float | None = None
    budget_currency: str = "USD"
    party_size: int = 1
    preferences: list[str] = Field(default_factory=list)
    raw_query: str


class DomainFindings(BaseModel):
    domain: Domain
    summary: str
    structured: dict = Field(default_factory=dict)
    tool_calls_made: int = 0
    cache_hits: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    warnings: list[str] = Field(default_factory=list)


class ReallocationDirective(BaseModel):
    """The only thing the budget agent's LLM call ever authors — never the
    cost figure or the accept/reject decision, both of which are Python."""

    target_domains: list[Domain]
    reason: str
    violated_constraint: str
    guidance: str


class BudgetVerdict(BaseModel):
    accepted: bool
    total_estimated_cost: float
    directive: ReallocationDirective | None = None


class OrchestrationRunStats(BaseModel):
    delegation_count: int = 0
    replan_count: int = 0
    cache_hit_rate: float = 0.0
    serial_equivalent_seconds: float = 0.0
    wall_clock_seconds: float = 0.0
    mcp_round_trip_seconds: float = 0.0
    agent_reasoning_seconds: float = 0.0
    per_agent_usage: dict[str, TokenUsage] = Field(default_factory=dict)
