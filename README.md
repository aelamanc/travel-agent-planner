# Agentic Travel Itinerary Planner

Compares three agentic reasoning strategies (ReAct, Plan-then-Execute, Self-Critique) against a zero-shot baseline for automated travel itinerary generation using the OpenAI API. All strategy logic is implemented from scratch using the OpenAI SDK — no LangChain or agent frameworks.

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
# Edit .env and add your OPENAI_API_KEY (required)
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
# --strategy: react | plan | critique | baseline
# --mode: mock | live
# --model: gpt-4o (default)

# Single query with real travel API data
python main.py --mode live

# Run tests (no API key needed — tests use mock tools only)
pytest tests/ -v

# Evaluation harness
python run_eval.py --limit 2              # smoke test (2 scenarios, mock data)
python run_eval.py                        # full evaluation (40 scenarios, all strategies)
python run_eval.py --strategy react       # single strategy
python run_eval.py --mode live --limit 2  # live travel APIs, limited run
```

Note: `--mode mock` only controls the travel data tools. All strategies still call the OpenAI API and require `OPENAI_API_KEY`.

In `--mode live`, each travel tool falls back to mock data if the external API key is missing, invalid, rate-limited, or otherwise fails. Fallback responses include `mode: "mock_fallback"` and a `live_error` field in the raw tool result.

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

Each tool supports two modes: `mock` (hardcoded data) and `live` (real API calls). The mode is set via `--mode` flag — strategies don't know which mode is active.

| Tool | Mock Data | Live API |
|---|---|---|
| `search_flights` | Hardcoded flights for Paris/Tokyo/Rome | SerpAPI Google Flights |
| `search_hotels` | Hardcoded hotels for Paris/Tokyo/Rome | Booking.com via RapidAPI |
| `get_weather` | Hardcoded 7-day forecasts | OpenWeatherMap 5-day forecast |
| `get_attractions` | Hardcoded attractions with categories | Geoapify Places API |

## Strategies

| Strategy | LLM Calls | How it works |
|---|---|---|
| **Zero-shot Baseline** | 1 | Single GPT-4o call, no tools |
| **Plan-then-Execute** | 3 | Generate full plan upfront, execute all steps, synthesize |
| **ReAct** | 6–10 | Think-act-observe loop, one tool at a time, up to 15 iterations |
| **Self-Critique** | 4–5 | Gather all data, draft itinerary, critique (score 1–10), refine |

## Evaluation

- **40 scenarios** across 4 categories: simple, budget-constrained, multi-city, preference-heavy
- **Metrics:** goal completion (field presence), constraint satisfaction (budget/cities/preferences), latency, token cost
- Results written to `results/` as CSV

### Results (mock mode, gpt-4o, seed=42)

| Strategy | Goal Completion | Constraint Satisfaction | Avg Latency | Avg Tokens |
|---|---|---|---|---|
| Zero-shot Baseline | 100% | 82.5% | 18.0s | 1,614 |
| Plan-then-Execute | 100% | 97.5% | 16.1s | 5,086 |
| Self-Critique | 96.2% | 97.5% | 37.6s | 12,120 |
| ReAct | 100% | 100% | 16.0s | 6,564 |

## Reproducibility

- **Model:** `gpt-4o` (OpenAI, accessed April 2026)
- **Seed:** `seed=42` is passed to every OpenAI API call
- **Mock mode** is fully deterministic — no external API calls, hardcoded tool data
- **Live mode** depends on external API responses and is not guaranteed to be reproducible
- Python 3.11, dependency versions pinned in `requirements.txt`

To exactly reproduce the eval results in `results/`:
```bash
python run_eval.py --strategy baseline --mode mock
python run_eval.py --strategy plan --mode mock
python run_eval.py --strategy critique --mode mock
python run_eval.py --strategy react --mode mock
```
