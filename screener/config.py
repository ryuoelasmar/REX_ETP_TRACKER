"""Screener configuration: scoring weights, thresholds, file paths."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "SCREENER" / "decision_support_data.xlsx"

# --- Scoring weights (must sum to 1.0) ---
SCORING_WEIGHTS = {
    "Total Call OI": 0.25,
    "Total OI": 0.15,
    "Avg Volume 30D": 0.15,
    "Avg Volume 10D": 0.10,
    "Mkt Cap": 0.15,
    "Turnover / Traded Value": 0.10,
    "Short Interest Ratio": 0.05,
    "News Sentiment Daily Avg": 0.05,
}

# --- Threshold filters ---
THRESHOLD_FILTERS = {
    "min_mkt_cap": 10_000,  # $10B in millions
}

# --- Competitive density categories ---
DENSITY_UNCONTESTED = "Uncontested"
DENSITY_EARLY = "Early Stage"
DENSITY_COMPETITIVE = "Competitive"
DENSITY_CROWDED = "Crowded"

# --- Leverage types & directions ---
LEVERAGE_TYPES = ["2x", "3x", "1x", "4x"]
DIRECTIONS = ["Long", "Short", "Tactical"]

# --- etp_data columns to load (not all 102) ---
ETP_COLS_NEEDED = [
    # Identifiers
    "ticker", "fund_name", "issuer", "listed_exchange", "inception_date",
    "fund_type", "asset_class_focus", "is_singlestock",
    "uses_leverage", "leverage_amount", "is_rex",
    # Leverage & Inverse mapping
    "q_category_attributes.map_li_category",
    "q_category_attributes.map_li_subcategory",
    "q_category_attributes.map_li_direction",
    "q_category_attributes.map_li_leverage_amount",
    "q_category_attributes.map_li_underlier",
    # Trading quality
    "t_w2.expense_ratio", "t_w2.average_bidask_spread",
    "t_w2.nav_tracking_error", "t_w2.percentage_premium",
    "t_w2.average_percent_premium_52week", "t_w2.average_vol_30day",
    # Returns
    "t_w3.total_return_1month", "t_w3.total_return_3month",
    "t_w3.total_return_ytd", "t_w3.total_return_1year",
    # Fund flows
    "t_w4.fund_flow_1month", "t_w4.fund_flow_3month",
    "t_w4.fund_flow_6month", "t_w4.fund_flow_ytd",
    "t_w4.fund_flow_1year",
    # AUM (current + 36 months historical)
    "t_w4.aum",
] + [f"t_w4.aum_{i}" for i in range(1, 37)] + [
    # Categories
    "etp_category", "issuer_display", "category_display", "fund_category_key",
]

# --- PDF styling ---
PDF_COLORS = {
    "primary": "#1a1a2e",
    "secondary": "#0984e3",
    "text": "#000000",
    "light_bg": "#f5f7fa",
    "border": "#cccccc",
}
