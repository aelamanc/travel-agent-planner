# Agentic Travel Itinerary Planner

Compares three agentic reasoning strategies (ReAct, Plan-then-Execute, Self-Critique) against a zero-shot baseline for automated travel itinerary generation using the OpenAI API. All strategy logic is implemented from scratch using the OpenAI SDK — no LangChain or agent frameworks.

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env and add your OpenAI API key
```

### Live Mode (optional)

To use real APIs instead of mock data, add these keys to your `.env`:

```
SERPAPI_KEY=...              # flights (Google Flights via SerpAPI, 250 searches/month free)
OPENWEATHER_API_KEY=...      # weather (free tier, 1000 calls/day)
GEOAPIFY_API_KEY=...         # attractions (Geoapify Places, 3000 credits/day free)
```

## Run

```bash
# Single query with mock travel data (default)
python main.py

# Pick a strategy and pass your own query
python main.py --strategy plan --query "Plan a 4-day Rome trip from JFK, June 15-19, under $1500."

# Single query with real travel API data
python main.py --mode live

# Run tests (no API key needed — tests use mock tools only)
pytest tests/ -v

# Evaluation harness
python run_eval.py --limit 2              # smoke test, mock travel data
python run_eval.py                        # full evaluation, mock travel data
python run_eval.py --mode live --limit 2  # live travel APIs, limited run
```

Note: `--mode mock` only controls the travel data tools. All strategies still call the OpenAI API and require `OPENAI_API_KEY`.

In `--mode live`, each travel tool falls back to mock data if the external API key is missing, invalid, rate-limited, or otherwise fails. Fallback responses include `mode: "mock_fallback"` and a `live_error` field in the raw tool result.

## Tools

Each tool supports two modes: `mock` (hardcoded data) and `live` (real API calls). The mode is set via `--mode` flag — strategies don't know which mode is active.

| Tool | Mock Data | Live API |
|---|---|---|
| `search_flights` | Hardcoded flights for Paris/Tokyo/Rome | SerpAPI Google Flights |
| `search_hotels` | Hardcoded hotels for Paris/Tokyo/Rome | Amadeus Hotel Search |
| `get_weather` | Hardcoded 7-day forecasts | OpenWeatherMap 5-day forecast |
| `get_attractions` | Hardcoded attractions with categories | Geoapify Places API |

## Strategies

| Strategy | How it works |
|---|---|
| **Zero-shot baseline** | Single GPT-4o call, no tools |
| **ReAct** | Think-act-observe loop, one tool at a time |
| **Plan-then-Execute** | Generate full plan upfront, execute all steps, synthesize |
| **Self-Critique** | Gather all data, draft itinerary, critique, refine |

## Evaluation

- **40 scenarios** across 4 categories: simple, budget-constrained, multi-city, preference-heavy
- **Metrics:** goal completion, constraint satisfaction, latency, token cost
- Results written to `results/` as CSV
