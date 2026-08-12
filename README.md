# Agentic Travel Itinerary Planner

Compares five agentic reasoning strategies for automated travel itinerary generation on
Claude: four single-agent strategies implemented from scratch on the Anthropic SDK (Zero-Shot
Baseline, ReAct, Plan-then-Execute, Self-Critique — no LangChain or agent frameworks), plus a
fifth **`orchestrated`** strategy — a real multi-agent system (supervisor, three domain agents,
a budget reviewer, a synthesizer) where each domain agent talks to exactly one server over the
Model Context Protocol (MCP). See [`MIGRATION.md`](MIGRATION.md) for how this project moved from
GPT-4o/OpenAI to Claude/Anthropic+MCP, and [`ARCHITECTURE.md`](ARCHITECTURE.md) for why MCP is
used the way it is and an honest accounting of what it costs.

## Setup

**Requirements:** Python 3.11+

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY (required)
```

### Live Mode (optional)

To use real APIs instead of mock data, add these keys to your `.env`:

```
SERPAPI_KEY=...              # flights (Google Flights via SerpAPI, 250 searches/month free)
RAPIDAPI_KEY=...             # hotels (Booking.com via RapidAPI, 500 requests/month free)
OPENWEATHER_API_KEY=...      # weather (free tier, 1000 calls/day)
GEOAPIFY_API_KEY=...         # attractions (Geoapify Places, 3000 credits/day free)
```

## Run

```bash
# Streamlit demo UI
streamlit run app.py

# Single query with mock travel data (default: ReAct strategy)
python main.py

# Pick a strategy and pass your own query
python main.py --strategy plan --query "Plan a 4-day Rome trip from JFK, June 15-19, 2026, under $1500."
# --strategy: react | plan | critique | baseline | orchestrated
# --mode: mock | live
# --model: claude-haiku-4-5-20251001 (default) — use claude-sonnet-5 for higher-fidelity runs

# Single query with real travel API data
python main.py --mode live

# Single query through the multi-agent MCP strategy
python main.py --strategy orchestrated

# Run tests (no API key needed — tests use mock tools + in-memory MCP transport only)
pytest tests/ -v

# Evaluation harness
python run_eval.py --limit 4                          # smoke test (4 scenarios, mock data, Haiku)
python run_eval.py                                     # full evaluation (40 scenarios, all 5 strategies)
python run_eval.py --strategy react                    # single strategy
python run_eval.py --mode live --limit 2               # live travel APIs, limited run
python run_eval.py --model claude-sonnet-5             # full run on Sonnet — prompts for confirmation
                                                        # unless --limit or --yes is also given (real cost)
```

Note: `--mode mock` only controls the travel data tools. All strategies still call the Anthropic
API and require `ANTHROPIC_API_KEY` — mock mode does not mean no LLM calls.

In `--mode live`, each travel tool falls back to mock data if the external API key is missing, invalid, rate-limited, or otherwise fails. Fallback responses include `mode: "mock_fallback"` and a `live_error` field in the raw tool result. This applies identically whether a control strategy calls the tool directly or an `orchestrated` domain agent calls it over MCP — the fallback logic lives inside the tool itself, not in the caller.

## Example Output

```
$ python main.py --strategy react --query "Plan a 5-day trip to Paris from JFK, June 15-20, 2026. Budget $2000."

Destination: Paris
Dates: 2026-06-15 → 2026-06-20
Flights: Air France AF001 JFK→CDG $450 | Air France AF002 CDG→JFK $420
Hotel: Le Marais Boutique Hotel — $120/night — Total $600
Total Cost: $1,820
Tokens used: 6,421 | Latency: 14.3s
```

## Tools

Each tool supports two modes: `mock` (hardcoded data) and `live` (real API calls). The four
control strategies call these tools as direct Python function calls; `orchestrated` reaches them
through three MCP servers (`src/mcp_servers/`), one tool-domain per server, each toggled
mock/live independently via the same `--mode` flag propagated as `MCP_TOOL_MODE`. Either way, the
mock/live dispatch and fallback logic (`BaseTool.run()`) is identical — the transport differs, the
tool behavior doesn't.

| Tool | Server (MCP) | Mock Data | Live API |
|---|---|---|---|
| `search_flights` | `flights` | Hardcoded flights for Paris/Tokyo/Rome | SerpAPI Google Flights |
| `search_hotels` | `lodging` | Hardcoded hotels for Paris/Tokyo/Rome | Booking.com via RapidAPI |
| `get_weather` | `places` | Hardcoded 7-day forecasts | OpenWeatherMap 5-day forecast |
| `get_attractions` | `places` | Hardcoded attractions with categories | Geoapify Places API |

The `places` server also exposes an MCP resource (`travel://destinations`, the list of cities
with mock coverage) and an MCP prompt (`experience_search_strategy`) — see `ARCHITECTURE.md`.

## Strategies

| Strategy | LLM Calls | How it works |
|---|---|---|
| **Zero-shot Baseline** | 1 | Single Claude call, no tools |
| **Plan-then-Execute** | 2 | Generate full plan upfront, execute all steps (no LLM call), synthesize |
| **ReAct** | 6–10 | Think-act-observe loop, one tool at a time, up to 15 iterations |
| **Self-Critique** | 3–4 | Gather all data, draft itinerary, critique (score 1–10), refine if needed |
| **Orchestrated** | 6–9 | Supervisor → 3 concurrent domain agents (each own MCP server) → budget check → synthesizer; +2 calls if a reallocation round fires |

## Evaluation

- **40 scenarios** across 4 categories: simple, budget-constrained, multi-city, preference-heavy
- **Metrics:** goal completion (field presence), constraint satisfaction (budget/cities/preferences), latency, token cost — identical scoring for all 5 strategies, since `orchestrated` produces the same `ItineraryResult` schema as the controls
- Results written to `results/` as CSV; `orchestrated` runs also write a `mcp_run_summary_*.csv` companion file (server startup + tool-discovery time, once per eval run, not per scenario)

### Results (mock mode, Claude, temperature unset — see Reproducibility)

| Strategy | Goal Completion | Constraint Satisfaction | Avg Latency | Avg Tokens |
|---|---|---|---|---|
| Zero-shot Baseline | 84.6%¹ | 79.5%¹ | 21.7s | 4,026 |
| Plan-then-Execute | 97.5% | 90.0% | 24.1s | 9,084 |
| Self-Critique | 100% | 100% | 57.2s | 23,119 |
| **ReAct** | **100%** | **95.0%** | **23.3s** | **13,697** |
| Orchestrated (MCP) | 100% | 92.5% | 42.7s | 23,536 |

¹ Baseline: 1 of 40 scenarios (`pref_05`) is excluded from these averages. It failed
`ItineraryResult` validation on every attempt during the eval run and was not successfully
re-scored before the run was stopped (see `ARCHITECTURE.md` for why, and the honest-reporting
note at the end of this section). All other rows are the full 40/40.

**By category (constraint satisfaction):**

| Strategy | Simple | Budget | Multi-City | Preference |
|---|---|---|---|---|
| Baseline | 100% | 100% | 90% | 22% |
| Plan-then-Execute | 100% | 70% | 100% | 90% |
| Self-Critique | 100% | 100% | 100% | 100% |
| **ReAct** | 100% | **80%** | 100% | 100% |
| Orchestrated | 100% | **70%** | 100% | 100% |

**ReAct wins outright** — it matches or beats every other strategy, including `orchestrated`, on
every metric except raw token count (Self-Critique uses more). `orchestrated` is 1.8x slower and
1.7x more expensive than ReAct for *worse* constraint satisfaction (92.5% vs 95.0%), and
specifically underperforms ReAct on the budget category (70% vs 80%) — the exact category its
budget-reviewer/reallocation mechanism exists to help with. Only 3 of 40 orchestrated scenarios
actually triggered a reallocation round; the mechanism rarely engages, and even when the initial
plan is over budget, the single-agent ReAct loop's ability to adapt turn-by-turn beats the
multi-agent system's one-shot-then-maybe-retry structure. **This is a real result, not a
methodology artifact — see `ARCHITECTURE.md`'s Verdict section for the full discussion,
including the two-axis confound that keeps this from being a clean MCP-vs-direct-calls
comparison.**

### Historical results (gpt-4o, OpenAI, seed=42) — not comparable to the table above

The numbers below were produced before the Anthropic/MCP migration, on a different model and a
different SDK. **Do not compare them directly to the Claude results above** — any difference
could come from the model, not the strategy. They're kept here only as a record of what this
project measured before the migration.

| Strategy | Goal Completion | Constraint Satisfaction | Avg Latency | Avg Tokens |
|---|---|---|---|---|
| Zero-shot Baseline | 100% | 82.5% | 18.0s | 1,614 |
| Plan-then-Execute | 100% | 97.5% | 16.1s | 5,086 |
| Self-Critique | 96.2% | 97.5% | 37.6s | 12,120 |
| ReAct | 100% | 100% | 16.0s | 6,564 |

## Reproducibility

- **Model:** `claude-haiku-4-5-20251001` for iteration (default); `claude-sonnet-5` for the
  results table above. Anthropic, accessed August 2026.
- **No seed parameter exists in the Anthropic API**, unlike OpenAI's `seed=42` used before the
  migration. **No `temperature` parameter is sent at all** — current-generation Claude models
  (Sonnet 5, Opus 5+) reject sampling parameters outright with a 400, and on models that do
  accept them, `temperature=0` never guaranteed byte-identical output anyway.
- **What's actually deterministic:** the tool layer (hardcoded mock data, fixed scenario order
  in `src/evaluation/scenarios.py`, no randomization), and dependency versions pinned in
  `requirements.txt`. **What's best-effort, not guaranteed:** model outputs. Two runs of the
  same scenario on the same model can produce different itineraries, different token counts, and
  occasionally different pass/fail outcomes on the stricter validation checks — this eval run
  hit that directly (see the footnote on the baseline row above).
- **Live mode** additionally depends on external API responses and is not reproducible at all.

To reproduce a comparable eval run (Haiku, cheap, fast):
```bash
python run_eval.py --strategy baseline --mode mock
python run_eval.py --strategy plan --mode mock
python run_eval.py --strategy critique --mode mock
python run_eval.py --strategy react --mode mock
python run_eval.py --strategy orchestrated --mode mock
```
To reproduce the results table above (Sonnet, real cost, ~$10-15 for all 5 strategies):
```bash
python run_eval.py --strategy all --mode mock --model claude-sonnet-5
```
