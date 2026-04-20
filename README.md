# Agentic Travel Itinerary Planner

Compares three agentic reasoning strategies (ReAct, Plan-then-Execute, Self-Critique) against a zero-shot baseline for automated travel itinerary generation using GPT-4o. All strategy logic is implemented from scratch using the OpenAI SDK — no LangChain or agent frameworks.

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
AMADEUS_API_KEY=...          # flights + hotels (free test environment)
AMADEUS_API_SECRET=...
OPENWEATHER_API_KEY=...      # weather (free tier, 1000 calls/day)
GOOGLE_PLACES_API_KEY=...    # attractions (free $200/month credit)
```

## Run

```bash
# Single query with mock data (default)
python main.py

# Single query with real API data
python main.py --mode live

# Run tests (no API key needed — tests use mock tools only)
pytest tests/ -v

# Full evaluation harness
python run_eval.py               # mock mode
python run_eval.py --mode live   # live mode
```

## Tools

Each tool supports two modes: `mock` (hardcoded data) and `live` (real API calls). The mode is set via `--mode` flag — strategies don't know which mode is active.

| Tool | Mock Data | Live API |
|---|---|---|
| `search_flights` | Hardcoded flights for Paris/Tokyo/Rome | Amadeus Flight Offers |
| `search_hotels` | Hardcoded hotels for Paris/Tokyo/Rome | Amadeus Hotel Search |
| `get_weather` | Hardcoded 7-day forecasts | OpenWeatherMap 5-day forecast |
| `get_attractions` | Hardcoded attractions with categories | Google Places Text Search |

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
