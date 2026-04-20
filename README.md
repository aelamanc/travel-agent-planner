# Agentic Travel Itinerary Planner

Compares three agentic reasoning strategies (ReAct, Plan-then-Execute, Self-Critique) against a zero-shot baseline for automated travel itinerary generation using GPT-4o.

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

## Run

```bash
# Single query through ReAct strategy
python main.py

# Run tests (no API key needed — tests use mock tools only)
pytest tests/ -v

# Run full evaluation across all strategies and scenarios
python run_eval.py
```

## Project Structure

```
├── main.py                      # Single-query entrypoint (ReAct)
├── run_eval.py                  # Full evaluation harness entrypoint
├── src/
│   ├── models.py                # Pydantic output schema (ItineraryResult)
│   ├── baseline.py              # Zero-shot baseline (no tools)
│   ├── tools/
│   │   ├── base.py              # BaseTool interface
│   │   ├── flights.py           # search_flights (mock)
│   │   ├── hotels.py            # search_hotels (mock)
│   │   ├── weather.py           # get_weather (mock)
│   │   └── attractions.py       # get_attractions (mock)
│   ├── strategies/
│   │   ├── base.py              # BaseStrategy interface
│   │   ├── react.py             # ReAct (implemented)
│   │   ├── plan_execute.py      # Plan-then-Execute (skeleton)
│   │   └── self_critique.py     # Self-Critique (skeleton)
│   └── evaluation/
│       ├── scenarios.py         # 40 evaluation scenarios
│       ├── metrics.py           # Scoring functions
│       └── harness.py           # Eval loop + CSV output
├── tests/
│   ├── test_tools.py            # Tool unit tests
│   └── test_strategies.py       # Strategy infrastructure tests
└── results/                     # CSV and JSON output
```

## Strategies

| Strategy | How it works |
|---|---|
| **Zero-shot baseline** | Single GPT-4o call, no tools |
| **ReAct** | Think-act-observe loop, one tool at a time |
| **Plan-then-Execute** | Generate full plan upfront, execute all steps, synthesize |
| **Self-Critique** | Gather all data, draft itinerary, critique, refine |

## Evaluation Metrics

1. **Goal completion** — were flights, hotel, daily plan, and weather all returned?
2. **Constraint satisfaction** — did the itinerary respect budget, dates, and preferences?
3. **Latency** — wall-clock seconds
4. **Token cost** — total tokens across all LLM calls
