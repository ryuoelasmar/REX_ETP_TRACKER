"""Competitive intelligence: density analysis, AUM trajectories, fund flows, trading quality."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from screener.config import (
    DENSITY_COMPETITIVE,
    DENSITY_CROWDED,
    DENSITY_EARLY,
    DENSITY_UNCONTESTED,
)

log = logging.getLogger(__name__)

UNDERLIER_COL = "q_category_attributes.map_li_underlier"
DIRECTION_COL = "q_category_attributes.map_li_direction"
LEVERAGE_COL = "q_category_attributes.map_li_leverage_amount"


def _leveraged_etps(etp_df: pd.DataFrame) -> pd.DataFrame:
    """Filter to leveraged ETPs with a known underlier."""
    mask = (
        (etp_df.get("uses_leverage") == True)
        & (etp_df[UNDERLIER_COL].notna())
        & (etp_df[UNDERLIER_COL] != "")
    )
    return etp_df[mask].copy()


def compute_competitive_density(etp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute competitive landscape per underlier.

    Returns DataFrame with columns:
        underlier, product_count, total_aum, leader_ticker, leader_aum,
        leader_share, hhi, density_category
    """
    lev = _leveraged_etps(etp_df)
    if lev.empty:
        return pd.DataFrame()

    aum_col = "t_w4.aum"
    lev["_aum"] = pd.to_numeric(lev.get(aum_col, 0), errors="coerce").fillna(0)

    # Prepare is_rex flag
    is_rex_col = lev.get("is_rex", pd.Series(False, index=lev.index)).fillna(False)

    results = []
    for underlier, group in lev.groupby(UNDERLIER_COL):
        n = len(group)
        total_aum = group["_aum"].sum()
        leader = group.loc[group["_aum"].idxmax()]
        leader_aum = leader["_aum"]
        leader_share = leader_aum / total_aum if total_aum > 0 else 0

        # REX vs competitor split
        rex_mask = is_rex_col.loc[group.index] == True
        rex_count = int(rex_mask.sum())
        comp_count = n - rex_count
        rex_aum = group.loc[rex_mask, "_aum"].sum() if rex_mask.any() else 0
        comp_aum = total_aum - rex_aum

        # Herfindahl-Hirschman Index
        if total_aum > 0:
            shares = group["_aum"] / total_aum
            hhi = (shares ** 2).sum()
        else:
            hhi = 1.0

        # Oldest product age (for competitive penalty)
        oldest_days = None
        if "inception_date" in group.columns:
            dates = pd.to_datetime(group["inception_date"], errors="coerce")
            valid = dates.dropna()
            if not valid.empty:
                oldest = valid.min()
                oldest_days = (pd.Timestamp.now() - oldest).days

        # Categorize (based on competitor count, not REX count)
        if comp_count == 0 and rex_count == 0:
            cat = DENSITY_UNCONTESTED
        elif comp_count == 0:
            cat = DENSITY_UNCONTESTED  # Only REX products = we own this
        elif comp_count <= 2 and comp_aum < 500:
            cat = DENSITY_EARLY
        elif comp_count <= 4:
            cat = DENSITY_COMPETITIVE
        else:
            cat = DENSITY_CROWDED

        results.append({
            "underlier": underlier,
            "product_count": n,
            "total_aum": round(total_aum, 2),
            "rex_product_count": rex_count,
            "competitor_product_count": comp_count,
            "rex_aum": round(rex_aum, 2),
            "competitor_aum": round(comp_aum, 2),
            "is_rex_active": rex_count > 0,
            "leader_ticker": leader.get("ticker", ""),
            "leader_aum": round(leader_aum, 2),
            "leader_share": round(leader_share, 3),
            "leader_is_rex": bool(is_rex_col.loc[leader.name]) if leader.name in is_rex_col.index else False,
            "hhi": round(hhi, 3),
            "oldest_product_days": oldest_days,
            "density_category": cat,
        })

    out = pd.DataFrame(results)
    log.info("Competitive density: %d underliers analyzed", len(out))
    return out


def compute_aum_trajectories(etp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute AUM growth metrics per fund using 36-month time series.

    Returns DataFrame with: ticker, fund_name, underlier, cagr, momentum_3v12,
        time_to_100m, aum_stability, aum_current, aum_series (list)
    """
    lev = _leveraged_etps(etp_df)
    if lev.empty:
        return pd.DataFrame()

    aum_cols = [f"t_w4.aum_{i}" for i in range(1, 37)]
    available_aum = [c for c in aum_cols if c in lev.columns]

    results = []
    for _, row in lev.iterrows():
        series = [pd.to_numeric(row.get(c), errors="coerce") for c in available_aum]
        series = [v for v in series if pd.notna(v) and v > 0]

        current_aum = pd.to_numeric(row.get("t_w4.aum", 0), errors="coerce")
        if pd.isna(current_aum):
            current_aum = 0

        # CAGR (annualized return from oldest to newest)
        cagr = None
        if len(series) >= 2 and series[-1] > 0:
            years = len(series) / 12
            if years > 0:
                cagr = ((series[0] / series[-1]) ** (1 / years) - 1) * 100

        # Momentum: 3-month vs 12-month growth
        momentum = None
        if len(series) >= 12 and series[2] > 0 and series[11] > 0:
            growth_3m = (series[0] / series[2] - 1) * 100 if series[2] > 0 else None
            growth_12m = (series[0] / series[11] - 1) * 100 if series[11] > 0 else None
            if growth_3m is not None and growth_12m is not None:
                momentum = growth_3m - growth_12m

        # Time to $100M
        time_to_100m = None
        for i, v in enumerate(reversed(series)):
            if v >= 100:
                time_to_100m = len(series) - i
                break

        # Stability (std dev of monthly changes)
        stability = None
        if len(series) >= 3:
            changes = [series[i] / series[i + 1] - 1 for i in range(len(series) - 1) if series[i + 1] > 0]
            if changes:
                stability = float(np.std(changes))

        results.append({
            "ticker": row.get("ticker", ""),
            "fund_name": row.get("fund_name", ""),
            "underlier": row.get(UNDERLIER_COL, ""),
            "cagr": round(cagr, 1) if cagr is not None else None,
            "momentum_3v12": round(momentum, 1) if momentum is not None else None,
            "time_to_100m_months": time_to_100m,
            "aum_stability": round(stability, 3) if stability is not None else None,
            "aum_current": round(current_aum, 2),
            "aum_series": series[:12],  # Last 12 months for charting
        })

    out = pd.DataFrame(results)
    log.info("AUM trajectories: %d funds analyzed", len(out))
    return out


def compute_fund_flows(etp_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fund flows by underlier across all products.

    Returns DataFrame with: underlier, flow_1m, flow_3m, flow_6m, flow_ytd,
        flow_direction, flow_acceleration, rex_flow_1m, competitor_flow_1m
    """
    lev = _leveraged_etps(etp_df)
    if lev.empty:
        return pd.DataFrame()

    flow_cols = {
        "flow_1m": "t_w4.fund_flow_1month",
        "flow_3m": "t_w4.fund_flow_3month",
        "flow_6m": "t_w4.fund_flow_6month",
        "flow_ytd": "t_w4.fund_flow_ytd",
    }

    for alias, col in flow_cols.items():
        if col in lev.columns:
            lev[alias] = pd.to_numeric(lev[col], errors="coerce").fillna(0)
        else:
            lev[alias] = 0

    results = []
    for underlier, group in lev.groupby(UNDERLIER_COL):
        agg = {alias: group[alias].sum() for alias in flow_cols}

        # Direction
        direction = "Inflow" if agg.get("flow_3m", 0) > 0 else "Outflow"

        # Acceleration: is momentum increasing?
        accel = None
        if "flow_1m" in agg and "flow_3m" in agg:
            monthly_avg_3m = agg["flow_3m"] / 3
            if monthly_avg_3m != 0:
                accel = "Accelerating" if agg["flow_1m"] > monthly_avg_3m else "Decelerating"

        # REX vs competitor flows
        is_rex = lev.get("is_rex", pd.Series(False, index=lev.index))
        rex_mask = group.index.isin(lev[is_rex == True].index)
        rex_flow = group.loc[rex_mask, "flow_1m"].sum() if rex_mask.any() else 0
        comp_flow = group.loc[~rex_mask, "flow_1m"].sum()

        results.append({
            "underlier": underlier,
            **{k: round(v, 2) for k, v in agg.items()},
            "flow_direction": direction,
            "flow_acceleration": accel,
            "rex_flow_1m": round(rex_flow, 2),
            "competitor_flow_1m": round(comp_flow, 2),
        })

    out = pd.DataFrame(results)
    log.info("Fund flows: %d underliers analyzed", len(out))
    return out


def compute_trading_quality(etp_df: pd.DataFrame) -> pd.DataFrame:
    """Average trading quality metrics by underlier.

    Returns DataFrame with: underlier, avg_spread, avg_tracking_error,
        avg_premium_52w, volume_ratio
    """
    lev = _leveraged_etps(etp_df)
    if lev.empty:
        return pd.DataFrame()

    metric_cols = {
        "avg_spread": "t_w2.average_bidask_spread",
        "avg_tracking_error": "t_w2.nav_tracking_error",
        "avg_premium_52w": "t_w2.average_percent_premium_52week",
    }

    for alias, col in metric_cols.items():
        if col in lev.columns:
            lev[alias] = pd.to_numeric(lev[col], errors="coerce")
        else:
            lev[alias] = np.nan

    results = []
    for underlier, group in lev.groupby(UNDERLIER_COL):
        row = {"underlier": underlier}
        for alias in metric_cols:
            val = group[alias].mean()
            row[alias] = round(val, 4) if pd.notna(val) else None
        results.append(row)

    out = pd.DataFrame(results)
    log.info("Trading quality: %d underliers analyzed", len(out))
    return out


def get_products_for_underlier(etp_df: pd.DataFrame, underlier: str) -> pd.DataFrame:
    """Get all leveraged products for a specific underlier ticker."""
    lev = _leveraged_etps(etp_df)
    mask = lev[UNDERLIER_COL] == underlier
    return lev[mask].copy()


def compute_market_feedback(etp_df: pd.DataFrame, underlier: str) -> dict:
    """Assess market feedback for a specific underlier based on existing product performance.

    Returns dict with:
        verdict: VALIDATED / MIXED / REJECTED / NO_PRODUCTS
        product_count, total_aum, flow_direction, aum_trend, details (list of product dicts)
    """
    products = get_products_for_underlier(etp_df, underlier)

    if products.empty:
        return {
            "verdict": "NO_PRODUCTS",
            "product_count": 0,
            "total_aum": 0,
            "flow_direction": None,
            "aum_trend": None,
            "details": [],
        }

    aum_col = "t_w4.aum"
    flow_1m_col = "t_w4.fund_flow_1month"
    flow_3m_col = "t_w4.fund_flow_3month"

    products["_aum"] = pd.to_numeric(products.get(aum_col, 0), errors="coerce").fillna(0)
    products["_flow_1m"] = pd.to_numeric(products.get(flow_1m_col, 0), errors="coerce").fillna(0)
    products["_flow_3m"] = pd.to_numeric(products.get(flow_3m_col, 0), errors="coerce").fillna(0)

    total_aum = products["_aum"].sum()
    total_flow_1m = products["_flow_1m"].sum()
    total_flow_3m = products["_flow_3m"].sum()

    # Flow direction
    flow_dir = "Inflow" if total_flow_3m > 0 else "Outflow"

    # AUM trend: compare 3-month flow to current AUM
    aum_trend = None
    if total_aum > 0:
        flow_pct = total_flow_3m / total_aum * 100
        if flow_pct > 10:
            aum_trend = "Growing"
        elif flow_pct < -10:
            aum_trend = "Declining"
        else:
            aum_trend = "Stable"

    # Verdict
    if total_aum >= 100:
        verdict = "VALIDATED"  # $100M+ = market wants this
    elif total_aum >= 20 and total_flow_3m > 0:
        verdict = "VALIDATED"  # Growing with decent AUM
    elif total_aum < 10 and total_flow_3m <= 0:
        verdict = "REJECTED"  # Tiny and shrinking
    else:
        verdict = "MIXED"

    # Build product details
    is_rex_col = products.get("is_rex", pd.Series(False, index=products.index)).fillna(False)
    details = []
    for _, row in products.sort_values("_aum", ascending=False).iterrows():
        details.append({
            "ticker": row.get("ticker", ""),
            "fund_name": row.get("fund_name", ""),
            "issuer": row.get("issuer", ""),
            "is_rex": bool(is_rex_col.loc[row.name]),
            "aum": round(float(row["_aum"]), 1),
            "flow_1m": round(float(row["_flow_1m"]), 1),
            "direction": row.get(DIRECTION_COL, ""),
            "leverage": row.get(LEVERAGE_COL, ""),
        })

    return {
        "verdict": verdict,
        "product_count": len(products),
        "total_aum": round(total_aum, 1),
        "flow_direction": flow_dir,
        "aum_trend": aum_trend,
        "details": details,
    }
