# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Agentic travel itinerary planner comparing three reasoning strategies (ReAct, Plan-then-Execute, Self-Critique) plus a zero-shot baseline, all using GPT-4o via OpenAI API. No agent frameworks (LangChain, etc.) — all strategy logic is implemented from scratch using the OpenAI SDK's function calling.

## Commands

```bash
source .venv/bin/activate        # always activate venv first
pytest tests/ -v                 # run all tests (no API key needed)
pytest tests/test_tools.py -v    # tool tests only
pytest tests/test_tools.py::TestSearchFlights::test_respects_max_price -v  # single test
python main.py                   # single ReAct query (needs OPENAI_API_KEY in .env)
python run_eval.py               # full eval harness, outputs CSV to results/
```

## Architecture

**All three strategies and the baseline share the same tools, LLM, and output schema (`ItineraryResult`). Only the reasoning loop differs.**

- **Tools** (`src/tools/`): Four tools behind a `BaseTool` ABC. Each tool exposes `name`, `description`, `parameters_schema` (JSON Schema), `run(**kwargs) -> dict`, and `to_openai_tool()` for function-calling format. Tools use hardcoded mock data keyed by destination (Paris/Tokyo/Rome with fallback defaults). The tool registry in `src/tools/__init__.py` instantiates all four and is the single source passed to strategies.

- **Strategies** (`src/strategies/`): Each extends `BaseStrategy` ABC which holds the tool registry, provides `_get_openai_tools()` and `_execute_tool(name, args)`. Strategies implement `run(query: str) -> ItineraryResult`. ReAct is fully implemented; Plan-then-Execute and Self-Critique are skeletons with prompts written and TODO markers at each phase.

- **ReAct flow** (`react.py`): System prompt + user query → loop up to 15 iterations of OpenAI function calling → tool results appended as `role: tool` messages → terminates when LLM calls `finish_itinerary` (a synthetic tool defined in the strategy, not in the tool registry) → response parsed into `ItineraryResult`.

- **Evaluation** (`src/evaluation/`): 40 scenarios across 4 categories (simple, budget, multi-city, preference). `harness.py` runs strategies × scenarios, scores via `metrics.py` (goal completion + constraint satisfaction), writes CSV. `run_eval.py` is the entrypoint.

- **Output schema** (`src/models.py`): `ItineraryResult` is the universal Pydantic model returned by every strategy. It includes the itinerary data plus metadata (`strategy_used`, `tokens_used`, `latency_seconds`).

## Key Conventions

- Mock data normalization: each tool has a `_normalize(destination)` function mapping city names/airport codes to mock data keys. Add new destinations by extending these dicts.
- New tools: implement `BaseTool`, add to `TOOL_REGISTRY` in `src/tools/__init__.py`. Strategies pick them up automatically via `_get_openai_tools()`.
- New strategies: extend `BaseStrategy`, implement `run()`, register in `run_eval.py`.
- The `finish_itinerary` tool in ReAct is defined inline in `react.py` (not in the tool registry) — it's a control-flow mechanism, not a real tool.
