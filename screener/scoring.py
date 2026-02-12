"""Percentile rank scoring engine for ETF launch candidates.

Weights are derived from correlation analysis (n=64 underliers with AUM > 0).
Factors are de-duplicated to avoid collinearity.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from screener.config import SCORING_WEIGHTS, INVERTED_FACTORS, THRESHOLD_FILTERS, COMPETITIVE_PENALTY

log = logging.getLogger(__name__)


def derive_rex_benchmarks(
    etp_df: pd.DataFrame,
    stock_df: pd.DataFrame,
) -> dict[str, float]:
    """Compute median stock metrics for successful REX leveraged single-stock funds.

    "Successful" = is_rex, Single Stock subcategory, AUM > 0.
    Returns median values of the underlying stocks for these funds.
    """
    underlier_col = "q_category_attributes.map_li_underlier"
    subcat_col = "q_category_attributes.map_li_subcategory"

    if underlier_col not in etp_df.columns or "t_w4.aum" not in etp_df.columns:
        log.warning("Cannot derive benchmarks: missing columns")
        return {}

    rex_lev = etp_df[
        (etp_df.get("is_rex") == True)
        & (etp_df.get("uses_leverage") == True)
        & (etp_df.get(subcat_col) == "Single Stock")
        & (etp_df["t_w4.aum"].fillna(0) > 0)
    ]

    if rex_lev.empty:
        log.warning("No REX leveraged single-stock funds with AUM > 0 found")
        return {}

    underliers = rex_lev[underlier_col].dropna().unique()
    log.info("REX benchmark: %d funds, %d unique underliers", len(rex_lev), len(underliers))

    # Match underliers to stock_data
    matched = stock_df[stock_df["ticker_raw"].isin(underliers)]
    if matched.empty:
        log.warning("No stock_data matches for REX underliers")
        return {}

    benchmarks = {}
    for key in SCORING_WEIGHTS:
        if key in matched.columns:
            val = matched[key].median()
            if pd.notna(val):
                benchmarks[key] = float(val)

    log.info("REX benchmarks derived: %s", benchmarks)
    return benchmarks


def compute_percentile_scores(
    stock_df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Compute percentile rank composite score for all stocks.

    Returns a copy of stock_df with added columns:
      - {factor}_pctl: percentile rank (0-100) for each scoring factor
      - composite_score: weighted composite (0-100)
      - rank: 1-based rank (1 = best)
    """
    if weights is None:
        weights = SCORING_WEIGHTS

    df = stock_df.copy()
    composite = np.zeros(len(df), dtype=np.float64)

    for factor, weight in weights.items():
        if factor not in df.columns:
            log.warning("Scoring factor '%s' not in data, skipping", factor)
            continue

        values = pd.to_numeric(df[factor], errors="coerce")

        # Inverted factors: lower value = better, so rank ascending
        if factor in INVERTED_FACTORS:
            pctl = values.rank(pct=True, ascending=True, na_option="bottom") * 100
        else:
            pctl = values.rank(pct=True, na_option="bottom") * 100

        col_name = f"{factor}_pctl"
        df[col_name] = pctl.round(1)
        composite += pctl.fillna(0) * weight

    df["composite_score"] = composite.round(1)
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    log.info("Scored %d stocks. Top: %s (%.1f), Bottom: %s (%.1f)",
             len(df),
             df.iloc[0].get("Ticker", "?"), df.iloc[0]["composite_score"],
             df.iloc[-1].get("Ticker", "?"), df.iloc[-1]["composite_score"])

    return df


def apply_threshold_filters(
    scored_df: pd.DataFrame,
    benchmarks: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Apply must-pass threshold filters. Adds 'passes_filters' boolean column."""
    df = scored_df.copy()
    passes = pd.Series(True, index=df.index)

    # Market cap filter
    min_mkt_cap = THRESHOLD_FILTERS.get("min_mkt_cap", 10_000)
    if "Mkt Cap" in df.columns:
        passes &= pd.to_numeric(df["Mkt Cap"], errors="coerce").fillna(0) >= min_mkt_cap

    # Dynamic filters from REX benchmarks (only for non-inverted factors)
    if benchmarks:
        for key, threshold in benchmarks.items():
            if key in df.columns and key not in INVERTED_FACTORS:
                passes &= pd.to_numeric(df[key], errors="coerce").fillna(0) >= threshold

    df["passes_filters"] = passes
    n_pass = passes.sum()
    log.info("Threshold filters: %d / %d pass (%.1f%%)", n_pass, len(df), 100 * n_pass / max(len(df), 1))

    return df


def apply_competitive_penalty(
    scored_df: pd.DataFrame,
    density_df: pd.DataFrame,
) -> pd.DataFrame:
    """Penalize stocks where existing leveraged products have low AUM (market rejection).

    Modifies composite_score and adds 'market_signal' column:
      - "Market Rejected" (-25 pts): total AUM < $10M, oldest product > 6 months
      - "Low Traction" (-15 pts): total AUM < $50M, oldest product > 12 months
      - "REX Active": REX already has a product (no penalty, just label)
      - None: no existing products or passes thresholds
    """
    df = scored_df.copy()
    df["market_signal"] = None

    if density_df.empty:
        return df

    ticker_col = "ticker_clean" if "ticker_clean" in df.columns else "Ticker"

    # Build lookup from density data: underlier (clean) -> density row
    density_lookup = {}
    for _, row in density_df.iterrows():
        underlier = str(row["underlier"]).replace(" US", "").replace(" Curncy", "").upper()
        density_lookup[underlier] = row

    rejected_aum = COMPETITIVE_PENALTY["rejected_max_aum"]
    rejected_age = COMPETITIVE_PENALTY["rejected_min_age_days"]
    rejected_pen = COMPETITIVE_PENALTY["rejected_penalty"]
    low_aum = COMPETITIVE_PENALTY["low_traction_max_aum"]
    low_age = COMPETITIVE_PENALTY["low_traction_min_age_days"]
    low_pen = COMPETITIVE_PENALTY["low_traction_penalty"]

    penalties_applied = 0
    for idx, row in df.iterrows():
        ticker = str(row.get(ticker_col, "")).upper()
        d = density_lookup.get(ticker)
        if d is None:
            continue

        is_rex_active = d.get("is_rex_active", False)
        total_aum = d.get("total_aum", 0)
        oldest_days = d.get("oldest_product_days")

        if is_rex_active:
            df.at[idx, "market_signal"] = "REX Active"

        if oldest_days is None:
            continue

        if total_aum < rejected_aum and oldest_days >= rejected_age:
            df.at[idx, "composite_score"] = max(0, df.at[idx, "composite_score"] + rejected_pen)
            df.at[idx, "market_signal"] = "Market Rejected"
            penalties_applied += 1
        elif total_aum < low_aum and oldest_days >= low_age:
            df.at[idx, "composite_score"] = max(0, df.at[idx, "composite_score"] + low_pen)
            df.at[idx, "market_signal"] = "Low Traction"
            penalties_applied += 1

    if penalties_applied:
        df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
        df["rank"] = range(1, len(df) + 1)
        log.info("Competitive penalty: %d stocks penalized", penalties_applied)

    return df
