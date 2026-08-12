"""Shared Anthropic tool_use/tool_result loop.

This is the only place in the codebase that touches AsyncAnthropic, content
blocks, stop_reason, or usage fields directly. Every strategy (baseline,
react, plan, critique) and every orchestrated agent module (supervisor,
domain agent, budget agent, synthesizer) calls `run_tool_loop()`.

Anthropic has no JSON-mode equivalent to OpenAI's
`response_format={"type": "json_object"}`. Every call site that used to rely
on that now sets `single_shot=True` with a `tool_choice` that forces one
specific tool — the same mechanism react.py already used for
`finish_itinerary` — and reads the result off `LoopResult.forced_tool_input`
instead of parsing response text as JSON.
"""

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic

from .token_tracker import TokenUsage

# The itinerary output schema, shared by every strategy/agent that produces a
# final ItineraryResult-shaped payload: baseline, react's `finish_itinerary`,
# plan-then-execute's synthesis phase, self-critique's draft/refine phases,
# and the orchestrated strategy's synthesizer. Anthropic's `input_schema` is
# a near-direct rename of the JSON Schema react.py already used as
# `FINISH_TOOL["function"]["parameters"]`.
ITINERARY_TOOL_SCHEMA: dict = {
    "name": "finish_itinerary",
    "description": (
        "Call this when you have all the information needed to produce "
        "the final travel itinerary. Pass the complete itinerary data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {"type": "string"},
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "selected_flight": {
                "type": "object",
                "description": "The chosen flight option",
                "properties": {
                    "airline": {"type": "string"},
                    "flight_number": {"type": "string"},
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "departure_time": {"type": "string"},
                    "arrival_time": {"type": "string"},
                    "price": {"type": "number"},
                    "duration_hours": {"type": "number"},
                    "stops": {"type": "integer"},
                },
            },
            "return_flight": {
                "type": "object",
                "description": "The chosen return flight (optional)",
                "properties": {
                    "airline": {"type": "string"},
                    "flight_number": {"type": "string"},
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "departure_time": {"type": "string"},
                    "arrival_time": {"type": "string"},
                    "price": {"type": "number"},
                    "duration_hours": {"type": "number"},
                    "stops": {"type": "integer"},
                },
            },
            "selected_hotel": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "address": {"type": "string"},
                    "price_per_night": {"type": "number"},
                    "rating": {"type": "number"},
                    "amenities": {"type": "array", "items": {"type": "string"}},
                    "total_price": {"type": "number"},
                },
            },
            "daily_plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "weather": {"type": "string"},
                        "attractions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "category": {"type": "string"},
                                    "rating": {"type": "number"},
                                    "price": {"type": "number"},
                                    "description": {"type": "string"},
                                    "duration_hours": {"type": "number"},
                                },
                            },
                        },
                        "meals": {"type": "array", "items": {"type": "string"}},
                        "estimated_cost": {"type": "number"},
                    },
                },
            },
            "weather_summary": {"type": "string"},
            "total_estimated_cost": {"type": "number"},
            "natural_language_summary": {"type": "string"},
        },
        "required": [
            "destination",
            "start_date",
            "end_date",
            "selected_flight",
            "return_flight",
            "selected_hotel",
            "daily_plan",
            "weather_summary",
            "total_estimated_cost",
            "natural_language_summary",
        ],
    },
}


@dataclass
class LoopResult:
    forced_tool_input: dict | None = None
    final_text: str | None = None
    messages: list[dict] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    num_tool_calls: int = 0
    stop_reason: str = ""


async def run_tool_loop(
    *,
    client: AsyncAnthropic,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    execute_tool: Callable[[str, dict], dict | Awaitable[dict]] | None = None,
    tool_choice: dict | None = None,
    single_shot: bool = False,
    stop_when: Callable[[Any], bool] | None = None,
    max_tool_calls: int | None = None,
    max_iterations: int = 15,
    max_tokens: int,
) -> LoopResult:
    """Drive one Anthropic tool_use/tool_result conversation to completion.

    `single_shot=True` is the JSON-mode replacement: `tool_choice` must force
    a specific tool, and the loop returns after the first response with that
    tool's `.input`, never executing anything or looping further.

    Otherwise the loop extracts tool_use blocks, executes them via
    `execute_tool` (sync or async), and replies with a single batched
    tool_result user message per Anthropic's convention — until `stop_when`
    matches a tool_use block, the model stops calling tools (`end_turn`),
    `max_tool_calls` is reached, or `max_iterations` is exhausted.

    No `temperature` (or `top_p`/`top_k`) is set: newer Claude models
    (Sonnet 5, Opus 5+) reject sampling parameters outright (400), and on
    models that do accept them, `temperature=0` never guaranteed determinism
    anyway — reproducibility here is best-effort by default, not a lever.
    """
    usage = TokenUsage()
    num_tool_calls = 0
    convo = list(messages)
    resp = None

    for _ in range(max_iterations):
        create_kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=convo,
        )
        if tools:
            create_kwargs["tools"] = tools
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice

        resp = await client.messages.create(**create_kwargs)
        usage.input_tokens += resp.usage.input_tokens
        usage.output_tokens += resp.usage.output_tokens

        convo.append({"role": "assistant", "content": resp.content})

        tool_use_blocks = [b for b in resp.content if b.type == "tool_use"]

        if single_shot:
            if not tool_use_blocks:
                raise RuntimeError(
                    "single_shot=True expected a forced tool_use block but got none "
                    f"(stop_reason={resp.stop_reason!r})"
                )
            return LoopResult(
                forced_tool_input=tool_use_blocks[0].input,
                messages=convo,
                usage=usage,
                num_tool_calls=num_tool_calls,
                stop_reason="single_shot",
            )

        if not tool_use_blocks:
            text = "".join(b.text for b in resp.content if b.type == "text")
            return LoopResult(
                final_text=text,
                messages=convo,
                usage=usage,
                num_tool_calls=num_tool_calls,
                stop_reason="end_turn",
            )

        if stop_when is not None:
            matched = next((b for b in tool_use_blocks if stop_when(b)), None)
            if matched is not None:
                return LoopResult(
                    forced_tool_input=matched.input,
                    messages=convo,
                    usage=usage,
                    num_tool_calls=num_tool_calls,
                    stop_reason="stop_hook",
                )

        tool_results = []
        capped = False
        for block in tool_use_blocks:
            if max_tool_calls is not None and num_tool_calls >= max_tool_calls:
                capped = True
                break
            result = execute_tool(block.name, block.input)
            if inspect.isawaitable(result):
                result = await result
            num_tool_calls += 1
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )

        if capped:
            text = "".join(b.text for b in resp.content if b.type == "text")
            return LoopResult(
                final_text=text,
                messages=convo,
                usage=usage,
                num_tool_calls=num_tool_calls,
                stop_reason="max_tool_calls",
            )

        convo.append({"role": "user", "content": tool_results})

    text = "".join(b.text for b in resp.content if b.type == "text") if resp else ""
    return LoopResult(
        final_text=text,
        messages=convo,
        usage=usage,
        num_tool_calls=num_tool_calls,
        stop_reason="max_iterations",
    )
