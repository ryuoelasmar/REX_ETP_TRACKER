"""Screener configuration: scoring weights, thresholds, file paths."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "SCREENER" / "datatest.xlsx"
REPORTS_DIR = PROJECT_ROOT / "reports"

# --- Scoring weights (data-driven from correlation analysis, n=64 underliers) ---
# Dropped: Last Price (irrelevant to 2x product success), Twitter Sentiment (mostly zeros).
# Added: Volatility 30D (retail traders want vol, drives leveraged product demand).
# Short Interest Ratio is INVERTED (lower = better for product demand).
SCORING_WEIGHTS = {
    "Turnover / Traded Value": 0.30,  # r_log=0.742 - strongest predictor
    "Total OI": 0.30,                 # r_log=0.646 - direct options demand signal
    "Mkt Cap": 0.20,                  # r_log=0.612 - market viability / swap support
    "Volatility 30D": 0.10,           # retail traders want vol = leveraged demand
    "Short Interest Ratio": 0.10,     # r_log=-0.499 - contrarian interest (inverted)
}

# Factors where LOWER = BETTER (percentile ranked ascending)
INVERTED_FACTORS = {"Short Interest Ratio"}

# --- Threshold filters ---
THRESHOLD_FILTERS = {
    "min_mkt_cap": 10_000,  # $10B in millions
}

# --- Competitive penalty (applied after base scoring) ---
# Penalize stocks where existing leveraged products have low AUM (market rejection signal).
COMPETITIVE_PENALTY = {
    "rejected_max_aum": 10,       # $10M total AUM
    "rejected_min_age_days": 180,  # 6 months old
    "rejected_penalty": -25,       # points off composite score
    "low_traction_max_aum": 50,   # $50M total AUM
    "low_traction_min_age_days": 365,  # 12 months old
    "low_traction_penalty": -15,   # points off composite score
}

# --- Competitive density categories ---
DENSITY_UNCONTESTED = "Uncontested"
DENSITY_EARLY = "Early Stage"
DENSITY_COMPETITIVE = "Competitive"
DENSITY_CROWDED = "Crowded"

# --- Candidate evaluation pillar thresholds ---
DEMAND_THRESHOLDS = {
    "high_pctl": 75,    # 75th percentile = HIGH demand
    "medium_pctl": 40,  # 40th percentile = MEDIUM demand
}

# --- Leverage types & directions ---
LEVERAGE_TYPES = ["2x", "3x", "1x", "4x"]
DIRECTIONS = ["Long", "Short", "Tactical"]

# --- PDF styling ---
PDF_COLORS = {
    "primary": "#1a1a2e",
    "secondary": "#0984e3",
    "text": "#000000",
    "light_bg": "#f5f7fa",
    "border": "#cccccc",
}
