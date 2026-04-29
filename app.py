"""Streamlit demo UI for the Agentic Travel Planner."""

import os
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agentic Travel Planner",
    page_icon="✈️",
    layout="wide",
)

# ── Custom CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f1117; }
    .block-container { padding-top: 4rem; padding-bottom: 2rem; }

    .hero-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .hero-sub {
        color: #8b95a1;
        font-size: 1.05rem;
        margin-top: 0.3rem;
        margin-bottom: 2rem;
    }

    .card {
        background: #1a1d27;
        border: 1px solid #2d3148;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
    }
    .card-title {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #667eea;
        margin-bottom: 0.5rem;
    }
    .card-value {
        font-size: 1.1rem;
        color: #e8eaf0;
        font-weight: 600;
    }
    .card-sub {
        font-size: 0.85rem;
        color: #8b95a1;
        margin-top: 0.2rem;
    }

    .metric-row {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.2rem;
        flex-wrap: wrap;
    }
    .metric-box {
        background: #1a1d27;
        border: 1px solid #2d3148;
        border-radius: 10px;
        padding: 0.8rem 1.2rem;
        flex: 1;
        min-width: 120px;
        text-align: center;
    }
    .metric-label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #8b95a1;
    }
    .metric-val {
        font-size: 1.3rem;
        font-weight: 700;
        color: #e8eaf0;
    }

    .day-card {
        background: #1a1d27;
        border-left: 3px solid #667eea;
        border-radius: 0 10px 10px 0;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .day-header {
        font-weight: 700;
        color: #e8eaf0;
        margin-bottom: 0.4rem;
    }
    .weather-badge {
        display: inline-block;
        background: #252840;
        color: #a78bfa;
        border-radius: 20px;
        padding: 0.15rem 0.7rem;
        font-size: 0.78rem;
        margin-bottom: 0.6rem;
    }
    .attraction-item {
        color: #c5cad6;
        font-size: 0.88rem;
        padding: 0.2rem 0;
    }
    .meal-item {
        color: #8b95a1;
        font-size: 0.83rem;
        font-style: italic;
    }

    .summary-box {
        background: linear-gradient(135deg, #1a1d27 0%, #252840 100%);
        border: 1px solid #667eea44;
        border-radius: 12px;
        padding: 1.4rem 1.6rem;
        color: #c5cad6;
        font-size: 1rem;
        line-height: 1.7;
        margin-top: 1rem;
    }

    .tag {
        display: inline-block;
        background: #252840;
        color: #667eea;
        border-radius: 6px;
        padding: 0.1rem 0.5rem;
        font-size: 0.75rem;
        margin-right: 0.3rem;
        margin-top: 0.2rem;
    }

    div[data-testid="stButton"] > button {
        width: 100%;
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.65rem 1.5rem;
        font-size: 1rem;
        font-weight: 600;
        cursor: pointer;
    }
    div[data-testid="stButton"] > button:hover {
        opacity: 0.9;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────

def strategy_label(name: str) -> str:
    return {
        "react": "ReAct",
        "plan": "Plan-then-Execute",
        "critique": "Self-Critique",
        "baseline": "Zero-Shot Baseline",
    }.get(name, name)


def run_strategy(query: str, strategy_key: str, mode: str):
    from src.tools import create_tool_registry
    from src.strategies.react import ReActStrategy
    from src.strategies.plan_execute import PlanExecuteStrategy
    from src.strategies.self_critique import SelfCritiqueStrategy
    from src.baseline import ZeroShotBaseline

    tools = create_tool_registry(mode=mode)
    strategies = {
        "react": ReActStrategy(tools=tools),
        "plan": PlanExecuteStrategy(tools=tools),
        "critique": SelfCritiqueStrategy(tools=tools),
        "baseline": ZeroShotBaseline(),
    }
    return strategies[strategy_key].run(query)


# ── Header ───────────────────────────────────────────────────────────

st.markdown('<p class="hero-title"> Agentic Travel Planner</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-sub">Comparing reasoning strategies for automated itinerary generation</p>', unsafe_allow_html=True)

# ── Input panel ──────────────────────────────────────────────────────

with st.container():
    query = st.text_area(
        "Your travel request",
        value="Plan a 5-day trip to Paris from JFK, June 15-20, 2026. Budget $2000. I love museums and food.",
        height=90,
        placeholder="e.g. 5 days in Tokyo from JFK, June 15-20, 2026. Budget $2500. I love food and temples.",
    )

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        strategy_key = st.selectbox(
            "Strategy",
            options=["react", "plan", "critique", "baseline"],
            format_func=strategy_label,
        )
    with col2:
        mode = st.selectbox("Data mode", options=["live", "mock"])
    with col3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        run = st.button("Plan my trip →")

# ── Run ───────────────────────────────────────────────────────────────

if run:
    if not os.getenv("OPENAI_API_KEY"):
        st.error("Missing OPENAI_API_KEY in .env")
        st.stop()

    with st.spinner(f"Planning your trip with {strategy_label(strategy_key)}..."):
        try:
            result = run_strategy(query, strategy_key, mode)
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

    st.divider()

    # ── Trip overview ─────────────────────────────────────────────────
    st.markdown(f"### 🗺️ {result.destination}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Depart", result.travel_dates[0])
    m2.metric("Return", result.travel_dates[1])
    m3.metric("Total Cost", f"${result.total_estimated_cost:,.0f}")
    m4.metric("Tokens Used", f"{result.tokens_used:,}")
    m5.metric("Latency", f"{result.latency_seconds}s")

    st.divider()

    left, right = st.columns(2)

    # ── Flights ───────────────────────────────────────────────────────
    with left:
        st.markdown("#### ✈️ Flights")
        if result.flights:
            labels = ["Outbound", "Return"]
            for i, f in enumerate(result.flights):
                label = labels[i] if i < len(labels) else f"Flight {i+1}"
                st.markdown(f"""
<div class="card">
    <div class="card-title">{label}</div>
    <div class="card-value">{f.airline} &nbsp;·&nbsp; {f.flight_number}</div>
    <div class="card-sub">{f.origin} → {f.destination}</div>
    <div class="card-sub" style="margin-top:0.5rem">
        🕐 {f.departure_time} &nbsp;→&nbsp; {f.arrival_time}<br>
        ⏱ {f.duration_hours}h &nbsp;·&nbsp; {"Nonstop" if f.stops == 0 else f"{f.stops} stop(s)"}
    </div>
    <div class="card-value" style="margin-top:0.6rem; color:#a78bfa">${f.price:,.0f}</div>
</div>
""", unsafe_allow_html=True)
        else:
            st.info("No flight data")

    # ── Hotel ─────────────────────────────────────────────────────────
    with right:
        st.markdown("#### 🏨 Hotel")
        h = result.hotel
        stars = "⭐" * round(h.rating)
        amenity_tags = " ".join(f'<span class="tag">{a}</span>' for a in h.amenities[:6])
        st.markdown(f"""
<div class="card">
    <div class="card-title">Accommodation</div>
    <div class="card-value">{h.name}</div>
    <div class="card-sub">{h.address}</div>
    <div class="card-sub" style="margin-top:0.4rem">{stars} &nbsp; {h.rating}/5</div>
    <div style="margin-top:0.4rem">{amenity_tags}</div>
    <div style="margin-top:0.6rem">
        <span class="card-value" style="color:#a78bfa">${h.price_per_night:,.0f}/night</span>
        <span class="card-sub"> &nbsp;·&nbsp; Total ${h.total_price:,.0f}</span>
    </div>
</div>
""", unsafe_allow_html=True)

    # ── Weather summary ───────────────────────────────────────────────
    st.markdown("#### 🌤️ Weather")
    st.markdown(f'<div class="summary-box">🌍 {result.weather_summary}</div>', unsafe_allow_html=True)

    # ── Daily plan ────────────────────────────────────────────────────
    st.markdown("#### 📅 Daily Plan")
    for day in result.daily_plan:
        attractions_html = "".join(
            f'<div class="attraction-item">🎯 <b>{a.name}</b> '
            f'<span style="color:#8b95a1">({a.category}'
            f'{f", &#36;{a.price:.0f}" if a.price > 0 else ""}'
            f'{f", {a.duration_hours}h" if a.duration_hours > 0 else ""})</span></div>'
            for a in day.attractions
        )
        meals_html = "".join(
            f'<div class="meal-item">🍽 {m}</div>' for m in day.meals
        )
        cost_str = f"{day.estimated_cost:,.0f}"
        day_html = (
            f'<div class="day-card">'
            f'<div class="day-header">{day.date}</div>'
            f'<div class="weather-badge">🌡 {day.weather}</div>'
            f'{attractions_html}'
            f'<div style="margin-top:0.5rem">{meals_html}</div>'
            f'<div style="margin-top:0.5rem; font-size:0.82rem; color:#667eea">Est. daily cost: &#36;{cost_str}</div>'
            f'</div>'
        )
        st.markdown(day_html, unsafe_allow_html=True)

    # ── Summary ───────────────────────────────────────────────────────
    st.markdown("#### 📝 Summary")
    st.markdown(f'<div class="summary-box">{result.natural_language_summary}</div>', unsafe_allow_html=True)

    # ── Strategy badge ────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:1.5rem; text-align:right; color:#8b95a1; font-size:0.8rem'>"
        f"Generated with <b style='color:#667eea'>{strategy_label(result.strategy_used)}</b> "
        f"strategy &nbsp;·&nbsp; {mode} mode</div>",
        unsafe_allow_html=True,
    )
