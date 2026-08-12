# Migration: Multi-Agent MCP Refactor + OpenAI → Anthropic

## Why

The planner runs four reasoning strategies (baseline, ReAct, Plan-then-Execute, Self-Critique),
all calling four tools (`search_flights`, `search_hotels`, `get_weather`, `get_attractions`) as
direct Python function calls, on GPT-4o via the OpenAI SDK. This migration does two things:

1. Moves the model layer to Anthropic (Claude Haiku 4.5 for iteration, Sonnet 5 for final eval).
2. Adds a fifth **`orchestrated`** strategy — a real multi-agent system where capability
   scoping (which tools an agent can see) is enforced by the MCP protocol boundary itself, not
   by prompt instructions.

The four existing strategies become controls: same semantics, same direct tool calls, only the
model backend changes underneath them. Old GPT-4o eval numbers are not comparable post-migration
and will be kept as a labeled historical row once new baselines are established on Claude.

## Deviations from this plan, found during implementation

Two things below turned out different from what this document originally specified, discovered
by actually running the code rather than by design review. Both are corrected in the
implementation; this plan is left as-written above (as the record of what was approved) with
the correction noted here rather than silently edited in.

1. **No `temperature` parameter is sent at all — not `temperature=0`.** This plan's original
   wording ("`temperature=0` explicit") was wrong: `claude-sonnet-5` (and the rest of the
   Sonnet-5/Opus-5-tier model family) rejects `temperature`/`top_p`/`top_k` outright with a 400,
   full stop, not just when non-default. This was invisible through all of chunks 1–3 because
   Haiku 4.5 (the default iteration model) still accepts the parameter — it only surfaced when
   the first full Sonnet eval run failed all 200 calls at request validation before generating a
   single token. `run_tool_loop()` and every call site now omit the parameter entirely. This
   doesn't change the reproducibility framing below — `temperature=0` was already documented as
   best-effort, not a guarantee, and dropping the parameter doesn't make that claim any less true.
2. **The installed `mcp` SDK (2.0.0) is a materially different generation than this plan assumed**
   (`mcp.server.fastmcp.FastMCP` / classic `ClientSession`+`stdio_client`). The actual API is
   `mcp.server.mcpserver.MCPServer` and a higher-level `mcp.client.Client` that connects directly
   to either an in-process server instance or a stdio transport with the same interface — which
   ended up *simpler* than the `ClientSession`-based design sketched here, not more complex.
   `src/mcp_servers/*.py` and `src/agents/mcp_session_manager.py` reflect the real API; nothing in
   the module layout or responsibilities below changed as a result.

## Load-bearing decisions

1. **MCP is used by exactly one of five strategies** — `orchestrated`. The four controls keep
   calling `BaseTool.run()` directly; changing their tool-calling transport would be a semantic
   change that was explicitly ruled out. Only the model backend swaps under them.
2. **All 5 strategies use `AsyncAnthropic`** and `async def run()`, so one shared tool-loop
   function (`run_tool_loop()`) serves every strategy and every agent.
3. **`ZeroShotBaseline` folds into `BaseStrategy`** (`tools: list[BaseTool] = []` default) so the
   shared loop mixin serves it too.
4. **Every `response_format={"type":"json_object"}` call site becomes a forced single-tool call**
   (`tool_choice={"type":"tool","name":...}`, read `.input` off the `tool_use` block) — this
   generalizes the pattern the codebase already uses for `react.py`'s `finish_itinerary`, and is
   the direct answer to "Anthropic has no JSON mode."
5. **Domain-agent tool-call cap is round-based, not flat-cumulative**: 4 calls on the initial
   invocation, up to 6 total only if re-invoked after a budget-agent rejection. A flat
   cumulative-4 cap would make reallocation a no-op — an agent that already spent its budget in
   round one couldn't act on new guidance.
6. **The budget agent never computes cost.** `total_estimated_cost` is summed in Python from
   `DomainFindings.structured`; `accepted` is a Python threshold check against
   `ConstraintSet.budget_total`. The budget agent's one conditional LLM call (only made when
   over budget) authors *just* a `ReallocationDirective` — which domain(s), why, what guidance.
7. **`asyncio.gather(..., return_exceptions=True)`** — a failed domain agent never aborts the
   query. Its result is replaced with a stub `DomainFindings(structured={}, warnings=[...])`,
   and the synthesizer is explicitly instructed to state that gap in `natural_language_summary`
   rather than silently fabricating data for it.
8. **`orchestrated` differs from the controls on two axes at once** — multi-agent decomposition
   *and* MCP transport. This is a real confound: a latency/token/quality difference cannot be
   attributed to either cause alone without a further ablation this project does not build.
   `ARCHITECTURE.md` states this plainly, backed by separate `mcp_round_trip_seconds` vs.
   `agent_reasoning_seconds` instrumentation. Only `orchestrated` has a TTL cache — in mock mode
   this makes `cache_hit_rate` a property of its own repeated-argument pattern, not a fair
   efficiency comparison against the controls (which have no equivalent cache).

## Module layout

**(a) OpenAI → Anthropic swap + shared plumbing**

| File | Responsibility |
|---|---|
| `src/anthropic_client.py` (new) | `get_async_client() -> AsyncAnthropic`, reads `ANTHROPIC_API_KEY`. Single import site for all strategies/agents. |
| `src/llm_loop.py` (new) | Shared `run_tool_loop()` + `ITINERARY_TOOL_SCHEMA` (generalized `FINISH_TOOL`, `input_schema`-shaped). |
| `src/token_tracker.py` (new) | `TokenUsage` dataclass (`input_tokens`/`output_tokens` — Anthropic has no combined field), `StrategyRunTracker` (per-run latency + token accumulation), `RunSpendTracker` (cumulative-across-eval-run counter, prints to stdout). Replaces the ad hoc `start_time=time.time()`/`total_tokens+=` duplicated in every strategy today. |
| `src/tools/base.py` | `to_openai_tool()` → `to_anthropic_tool()`: `{"name", "description", "input_schema": self.parameters_schema}` (flat, no `{"type":"function","function":{...}}` wrapper). `run()`/`_run_mock`/`_run_live`/mock-fallback tagging unchanged — exactly what the MCP servers wrap. |
| `src/strategies/base.py` | `tools: list[BaseTool] = []` (was required), `model` default → `claude-haiku-4-5-20251001`, `run()` → `abstractmethod async def`, `_get_openai_tools()` → `_get_anthropic_tools()`. |
| `src/baseline.py` | `ZeroShotBaseline(BaseStrategy)`. One `run_tool_loop()` call, `single_shot=True` against `ITINERARY_TOOL_SCHEMA`, no real tools. Drop `seed=42`, `response_format`; `temperature=0` explicit. |
| `src/strategies/react.py` | `FINISH_TOOL`'s `"parameters"` → `"input_schema"` (imported from `llm_loop.py` as `ITINERARY_TOOL_SCHEMA`). One `run_tool_loop()` call: `tool_choice={"type":"any"}`, `stop_when=lambda b: b.name=="finish_itinerary"`, `max_iterations=15`. Drop `seed=42`. |
| `src/strategies/plan_execute.py` | Two `run_tool_loop()` calls (`single_shot=True`): plan and synthesis. Middle "execute the plan" phase stays as plain Python calling `self._execute_tool()` — unchanged. Drop both `seed=42` sites. |
| `src/strategies/self_critique.py` | Four `run_tool_loop()` calls (`single_shot=True`): extract, draft, critique, refine. Direct-tool-call gathering phase unchanged. Drop all four `seed=42` sites. Multi-city normalization in `_build_result()` preserved as-is. |
| `main.py` | `--model` default → `claude-haiku-4-5-20251001`; `OPENAI_API_KEY` check → `ANTHROPIC_API_KEY`; `async def` + `asyncio.run(...)`; add `"orchestrated"` to `--strategy` choices. |
| `run_eval.py` | Same key swap; async; add `"orchestrated"`; soft confirm prompt when `"sonnet"` in `--model` and no `--limit` given. |
| `requirements.txt` | Remove `openai`; add `anthropic`, `mcp`. |
| `.env.example` | `OPENAI_API_KEY` → `ANTHROPIC_API_KEY`. |

**(b) MCP servers** (`src/mcp_servers/`)

- `common.py` — `make_tool_fn(tool: BaseTool)` wraps `BaseTool.run(**kwargs)` for `@mcp.tool()` registration; env var `MCP_TOOL_MODE` (`mock`/`live`, default `mock`) sets each `BaseTool(mode=...)` once at server startup.
- `flights_server.py` — `FastMCP("flights")`, registers `search_flights`.
- `lodging_server.py` — registers `search_hotels`.
- `places_server.py` — registers `get_weather` + `get_attractions`; also hosts:
  - **Resource** `travel://destinations` — re-exports the static city list backing the mock fixtures (`paris`/`tokyo`/`rome`), so a domain agent can check mock coverage before spending a tool call.
  - **Prompt** `experience_search_strategy(city, preferences)` — canned guidance ("check weather first to decide indoor/outdoor mix, then pull attractions filtered by preferences, stay within your call budget") the experiences domain agent fetches via `session.get_prompt(...)` instead of hardcoding the instruction in Python.

Each server is a thin adapter over the existing `BaseTool` subclasses — no tool logic is
duplicated, and mock-fallback/`live_error`/`mode` tagging keeps working unchanged because it
lives inside `BaseTool.run()` itself.

**(c) Agent layer** (`src/agents/`)

- `contracts.py` — Pydantic types: `ConstraintSet`, `DomainFindings`, `ReallocationDirective`, `BudgetVerdict`, `OrchestrationRunStats`.
- `mcp_session_manager.py` — `MCPSessionManager`, an async context manager owning the 3 persistent `ClientSession`s, `list_tools()`-based schema discovery (cached, never per-call), startup timing, `mcp_tool_to_anthropic()`.
- `cache.py` — `TTLCache` keyed on `(server, tool, normalized_args)`.
- `supervisor.py` — `parse_constraints(query, ...) -> ConstraintSet`, one `single_shot=True` loop call, no MCP session, no real tools.
- `domain_agent.py` — generic `DomainAgent`, parametrized by server name / system prompt; instantiated 3× (flights, lodging, experiences), each bound to exactly one `ClientSession`. Tool-call budget: `max_tool_calls=4` initially, `+2` (up to 6 total, cumulative on the same instance) only if re-invoked after a budget-agent rejection.
- `budget_agent.py` — `evaluate_budget(constraints, findings, ...) -> BudgetVerdict` and `compute_total_cost(findings: list[DomainFindings]) -> float` (pure Python, sums flight price(s) + hotel `total_price` from each finding's `structured` dict). `evaluate_budget()` only makes an LLM call when the Python-computed cost exceeds budget; that call authors *just* a `ReallocationDirective`.
- `synthesizer.py` — `synthesize(constraints, findings, ...) -> ItineraryResult`, one `single_shot=True` call against `ITINERARY_TOOL_SCHEMA` — the exact same schema every other strategy produces. Prompt instructs it to state any domain left with empty `structured`/non-empty `warnings` in `natural_language_summary`, rather than fabricate.
- `src/strategies/orchestrated.py` — `OrchestratedStrategy(BaseStrategy)`, `strategy_name = "orchestrated"`. `run()`: supervisor → `asyncio.gather(flights, lodging, experiences, return_exceptions=True)` (exceptions become warnings-tagged stub findings) → `compute_total_cost(findings)` → Python budget threshold check → if over budget, `evaluate_budget()`'s directive → re-invoke `directive.target_domains` agents (cap raised 4→6 for round 2 only, guidance appended) → recompute cost, round 2 ships regardless (hard 2-round cap) → synthesizer → `ItineraryResult`.

**(d) Eval/test files**

- `src/evaluation/harness.py` — `fieldnames` extended, except-block fallback dict kept in lockstep; `run_evaluation` → `async def`, `await strategy.run(...)`.
- `src/evaluation/run_summary.py` (new) — one-row-per-eval-run companion CSV for MCP startup + tool-discovery time (`results/mcp_run_summary_<timestamp>.csv`).
- `src/evaluation/scenarios.py`, `src/evaluation/metrics.py` — **unchanged**, confirmed strategy-agnostic.
- `tests/test_strategies.py` — rename `_get_openai_tools` references; still never calls `run()`, still needs no key.
- `tests/test_mcp_servers.py` (new) — in-memory MCP transport tests: tool registration, `inputSchema`→`input_schema` conversion, dispatch incl. `mock_fallback`/`live_error` tagging. Never touches `AsyncAnthropic`. Exact in-memory transport call verified against the installed `mcp` package version during implementation.
- `tests/test_agents.py` (new) — contract validation, `TTLCache` hit/miss/TTL logic, `mcp_tool_to_anthropic()` unit tests, gather-failure handling. No API key.
- `README.md` — reproducibility section rewritten (tool layer deterministic; temperature=0 best-effort, not guaranteed; no seed language); new `orchestrated` row; old gpt-4o numbers kept as a separately-labeled historical row.

## Shared Anthropic tool_use/tool_result loop

One function, `run_tool_loop()` in `src/llm_loop.py`, is the only place that touches
`AsyncAnthropic`, content blocks, `stop_reason`, and token usage fields.

```python
@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

@dataclass
class LoopResult:
    forced_tool_input: dict | None   # single_shot / stop_when-matched result
    final_text: str | None           # plain end_turn text, if no tool matched
    messages: list[dict]             # transcript, for phase-chaining callers
    usage: TokenUsage
    num_tool_calls: int
    stop_reason: str                 # single_shot | stop_hook | end_turn | max_iterations | max_tool_calls

async def run_tool_loop(
    *, client, model, system, messages, tools,
    execute_tool=None,               # sync or async callable(name, args) -> dict
    tool_choice=None,                # {"type":"auto"|"any"} or {"type":"tool","name":...}
    single_shot=False,               # forced-JSON-output replacement mode
    stop_when=None,                  # callable(tool_use_block) -> bool
    max_tool_calls=None,             # domain-agent cap
    max_iterations=15,
    max_tokens,                      # required, per-call
    temperature=0,
) -> LoopResult: ...
```

`system` is always the top-level param, never a `role="system"` message. Every call accumulates
`usage.input_tokens`/`usage.output_tokens`. `single_shot=True` forces a specific tool via
`tool_choice`, reads `.input` off the first `tool_use` block, returns immediately — the direct
replacement for every `response_format=json_object` call site. Otherwise, tool_use blocks are
executed and batched into **one** `{"role":"user","content":[...]}` tool_result message
(Anthropic's convention, unlike OpenAI's one-message-per-call). `stop_when` lets react detect
`finish_itinerary` inside a general tool-choice loop; `max_tool_calls` gives domain agents their
call cap.

| Caller | tools | tool_choice | single_shot | stop_when | max_tool_calls |
|---|---|---|---|---|---|
| baseline | `[ITINERARY_TOOL_SCHEMA]` | forced | ✓ | — | — |
| react | real tools + `FINISH_TOOL` | `{"type":"any"}` | — | `name=="finish_itinerary"` | — |
| plan (×2 calls) | plan schema / `ITINERARY_TOOL_SCHEMA` | forced | ✓ | — | — |
| critique (×4 calls) | phase-specific schema | forced | ✓ | — | — |
| supervisor | `[ConstraintSet schema]` | forced | ✓ | — | — |
| domain agent (×3) | MCP server's tools | `{"type":"auto"}` | — | — | 4 (6 if re-invoked, round 2 only) |
| budget agent (conditional) | `[ReallocationDirective schema]` | forced | ✓ | — | — |
| synthesizer | `[ITINERARY_TOOL_SCHEMA]` | forced | ✓ | — | — |

The budget agent's row is invoked only when the Python-computed `total_estimated_cost` exceeds
`budget_total` — its forced tool call authors a `ReallocationDirective` and nothing else;
`accepted` and the cost figure are always Python values, never model output.

## Message contract types (`src/agents/contracts.py`, Pydantic)

```python
class ConstraintSet(BaseModel):
    origin: str; destinations: list[str]; start_date: str; end_date: str
    budget_total: float | None = None; budget_currency: str = "USD"
    party_size: int = 1; preferences: list[str] = []; raw_query: str

class DomainFindings(BaseModel):
    domain: Literal["flights","lodging","experiences"]
    summary: str; structured: dict
    tool_calls_made: int; cache_hits: int
    usage: TokenUsage; warnings: list[str] = []
    # on an asyncio.gather failure for this domain: structured={}, tool_calls_made=0,
    # cache_hits=0, usage=TokenUsage(), warnings=["domain agent failed: <exc>"] —
    # never a raised exception reaching OrchestratedStrategy.run()

class ReallocationDirective(BaseModel):
    target_domains: list[Literal["flights","lodging","experiences"]]
    reason: str; violated_constraint: str; guidance: str
    # the ONLY field an LLM call produces during budget evaluation

class BudgetVerdict(BaseModel):
    accepted: bool                  # Python: total_estimated_cost <= budget_total (True if none stated)
    total_estimated_cost: float     # Python: compute_total_cost(findings) — never LLM-authored
    directive: ReallocationDirective | None = None   # LLM-authored, only when accepted=False

class OrchestrationRunStats(BaseModel):
    delegation_count: int; replan_count: int; cache_hit_rate: float
    serial_equivalent_seconds: float; wall_clock_seconds: float
    mcp_round_trip_seconds: float; agent_reasoning_seconds: float
    per_agent_usage: dict[str, TokenUsage]
```

Flow: `supervisor(query) -> ConstraintSet` → `asyncio.gather(..., return_exceptions=True)` of 3
domain agents → failed domains replaced with a warnings-tagged stub `DomainFindings` →
`compute_total_cost(findings)` (pure Python) → `accepted = total_estimated_cost <= budget_total`
(Python) → if not accepted, `evaluate_budget()` makes its one LLM call, authoring only a
`ReallocationDirective` → re-invoke `directive.target_domains` agents (cap raised 4→6 for round 2
only, guidance appended) → recompute cost, round 2 ships regardless (hard 2-round cap) →
`synthesizer(constraints, findings) -> ItineraryResult`, instructed to call out any domain left
with empty `structured`/non-empty `warnings` as a stated gap. `ItineraryResult` itself is not
extended — every strategy produces the identical schema; `OrchestrationRunStats` is assembled
separately by `OrchestratedStrategy.run()` for the new CSV columns.

## MCP session + cache lifecycle

`MCPSessionManager` (`src/agents/mcp_session_manager.py`) is an async context manager built on
`contextlib.AsyncExitStack`, spawning the 3 stdio subprocesses and their `ClientSession`s once,
calling `list_tools()` once per server (cached in `tools_by_server`, converted via
`mcp_tool_to_anthropic()`), and recording `startup_time_seconds`. `TTLCache`
(`src/agents/cache.py`) is a plain dict keyed on `(server, tool, json.dumps(sorted kwargs))`.

Both are constructed **once per eval run** (or once per single CLI query), not once per
scenario: `run_eval.py` and `main.py` wrap the orchestrated-strategy work in
`async with MCPSessionManager(mode=args.mode) as mcp_mgr:`, alongside a single `TTLCache()`,
threading both into `OrchestratedStrategy`. `AsyncExitStack` unwinds in reverse order on exit,
closing each `ClientSession` before its transport, cleanly terminating the subprocess even if a
domain agent raises.

**Timing instrumentation.** The domain agent's `execute_tool` callable (passed into
`run_tool_loop()`) wraps each `session.call_tool()` with its own timer, accumulated separately
from the LLM-call time `run_tool_loop()` already tracks. `OrchestrationRunStats` carries both
`mcp_round_trip_seconds` and `agent_reasoning_seconds` so IPC overhead and model latency are
never conflated in the CSV or in `ARCHITECTURE.md`'s cost accounting.

**Cache fairness caveat.** `TTLCache` is wired into the orchestrated strategy only. In mock
mode, tool calls are near-instant in-process dict lookups, so caching saves negligible wall time
regardless of hit rate; `cache_hit_rate` should be read as a property of the orchestrated run's
own repeated-argument pattern, not as evidence of an advantage over the controls (which have no
equivalent cache to compare against). It only becomes a fair efficiency signal in live mode,
where a hit avoids a real network round-trip.

## Eval / instrumentation

New CSV columns (blank/0/NA for the 4 control strategies, via explicit keys in every row dict
including the harness's except-block fallback — both edited together, as today):
`total_input_tokens`, `total_output_tokens` (alongside existing `tokens_used`, now computed
uniformly since Anthropic splits usage with no combined field), `per_agent_tokens` (one
JSON-blob column keyed by agent name — avoids a fixed 6-column layout that's meaningless for
control rows), `delegation_count`, `replan_count`, `cache_hit_rate`, `serial_equivalent_seconds`,
`mcp_round_trip_seconds`, `agent_reasoning_seconds`. Server startup + tool-discovery time is not
a per-scenario cost, so it goes in the new one-row-per-run `run_summary.py` companion CSV
instead of being repeated on every orchestrated row.

`run_eval.py`: add `"orchestrated"` to `--strategy` choices; `OPENAI_API_KEY` check replaced
with an unconditional `ANTHROPIC_API_KEY` check (all 5 strategies need it now); soft
confirmation prompt when `"sonnet"` is in `--model` and `--limit` is unset. `RunSpendTracker`
constructed once in `run_eval.py`, threaded into every strategy as an optional `spend_tracker`,
printing a running input/output token total to stdout after each scenario.

## Delivery order (stop after each for commit)

1. **MCP servers** — `src/mcp_servers/*`, `MCP_TOOL_MODE` toggle, resource + prompt, plus
   `tests/test_mcp_servers.py`. Also: `requirements.txt` update, this file.
2. **Agent layer** — `src/agents/*`, `src/llm_loop.py`, `src/anthropic_client.py`,
   `src/token_tracker.py`, `src/strategies/orchestrated.py`, plus the OpenAI→Anthropic swap
   across `src/baseline.py`, `src/strategies/{base,react,plan_execute,self_critique}.py`,
   `main.py`. All `seed=42` sites removed, `temperature=0` set explicitly. Plus
   `tests/test_agents.py` and updates to `tests/test_strategies.py`.
3. **Eval instrumentation** — `src/evaluation/harness.py` new columns, `run_summary.py`,
   `run_eval.py` CLI/gating changes. `app.py` gets an `asyncio.run(...)` bridge (Streamlit's
   script model is sync, but `run()` is now async) plus `"orchestrated"` registration in the
   `strategies` dict, `strategy_label()`, and the selectbox `options`.
4. **Re-run eval + docs** — smoke test with `--limit 4` on Haiku first; full 40-scenario Sonnet
   run only after explicit go-ahead; README before/after table with the old gpt-4o row clearly
   labeled historical; `ARCHITECTURE.md` written, including an honest verdict if orchestration
   loses to ReAct on latency/tokens without a quality gain, and the two-axis confound statement.

## Verification

- `pytest tests/ -v` must pass with **no** `ANTHROPIC_API_KEY` set at every chunk boundary.
- After chunk 1: manually run each MCP server standalone and confirm `MCP_TOOL_MODE=mock`/`live`
  toggle + fallback tagging behave like the existing `BaseTool` tests expect.
- After chunk 2: `python main.py --strategy {react,plan,critique,baseline} --mode mock` on Haiku
  confirms output still validates against `ItineraryResult`; `python main.py --strategy
  orchestrated --mode mock` end-to-end once MCP sessions wire in; a targeted test forcing one
  domain agent's `call_tool` to raise confirms `asyncio.gather(..., return_exceptions=True)`
  produces a warnings-tagged stub instead of aborting the run, and the synthesizer's summary
  mentions the gap.
- After chunk 3: `python run_eval.py --strategy orchestrated --mode mock --limit 4` (Haiku,
  default) confirms new CSV columns populate correctly and legacy rows stay blank/0 in them.
- Full 40-scenario Sonnet eval run: only after asking the user, per cost discipline.
