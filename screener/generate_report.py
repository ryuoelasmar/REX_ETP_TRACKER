"""CLI entry point for generating screener PDF reports.

Usage:
    # Candidate evaluation + appended rankings (primary use case):
    python -m screener.generate_report SCCO SIL AMPX BHP ERO RIO HBM TECK ZETA

    # Standalone universe rankings report:
    python -m screener.generate_report --rankings
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _compute_rankings(stock_df, etp_df):
    """Compute universe rankings and REX fund data. Shared by both report modes."""
    from screener.scoring import (
        compute_percentile_scores, derive_rex_benchmarks,
        apply_threshold_filters, apply_competitive_penalty,
    )
    from screener.competitive import compute_competitive_density
    from screener.filing_match import match_filings

    # Score
    benchmarks = derive_rex_benchmarks(etp_df, stock_df)
    scored = compute_percentile_scores(stock_df)
    scored = apply_threshold_filters(scored, benchmarks)

    # Competitive density + penalty
    density = compute_competitive_density(etp_df)
    scored = apply_competitive_penalty(scored, density)

    # Filing match
    scored = match_filings(scored, etp_df)

    # Build density lookup
    density_lookup = {}
    if not density.empty:
        for _, row in density.iterrows():
            underlier = str(row["underlier"]).replace(" US", "").replace(" Curncy", "")
            density_lookup[underlier] = row

    # Build results list
    results = []
    for _, row in scored.iterrows():
        ticker_clean = str(row.get("ticker_clean", row.get("Ticker", ""))).upper()
        d_info = density_lookup.get(ticker_clean, {})

        results.append({
            "ticker": str(row.get("Ticker", "")),
            "sector": str(row["GICS Sector"]) if pd.notna(row.get("GICS Sector")) else None,
            "composite_score": float(row.get("composite_score", 0)),
            "mkt_cap": float(row.get("Mkt Cap", 0)) if pd.notna(row.get("Mkt Cap")) else None,
            "total_oi_pctl": float(row.get("Total OI_pctl", 0)) if pd.notna(row.get("Total OI_pctl")) else None,
            "passes_filters": bool(row.get("passes_filters", False)),
            "filing_status": str(row.get("filing_status", "Not Filed")),
            "market_signal": row.get("market_signal"),
            "competitive_density": str(d_info.get("density_category", "")) if hasattr(d_info, "get") and d_info.get("density_category") else None,
        })

    # REX fund data
    rex_all = etp_df[etp_df.get("is_rex") == True].copy()
    rex_funds = []
    seen = set()
    for _, row in rex_all.iterrows():
        t = row.get("ticker", "")
        if t in seen:
            continue
        seen.add(t)
        rex_funds.append({
            "ticker": t,
            "underlier": row.get("q_category_attributes.map_li_underlier", ""),
            "aum": round(float(pd.to_numeric(row.get("t_w4.aum", 0), errors="coerce") or 0), 1),
            "flow_1m": round(float(pd.to_numeric(row.get("t_w4.fund_flow_1month", 0), errors="coerce") or 0), 1),
            "flow_3m": round(float(pd.to_numeric(row.get("t_w4.fund_flow_3month", 0), errors="coerce") or 0), 1),
            "flow_ytd": round(float(pd.to_numeric(row.get("t_w4.fund_flow_ytd", 0), errors="coerce") or 0), 1),
            "return_ytd": round(float(pd.to_numeric(row.get("t_w3.total_return_ytd", 0), errors="coerce") or 0), 1),
        })

    return results, rex_funds


def run_candidate_evaluation(tickers: list[str]) -> Path:
    """Run candidate evaluation + universe rankings combined PDF."""
    from screener.data_loader import load_all
    from screener.candidate_evaluator import evaluate_candidates
    from screener.report_generator import generate_candidate_report
    from screener.config import REPORTS_DIR

    REPORTS_DIR.mkdir(exist_ok=True)

    # Load data once (shared between candidate eval and rankings)
    log.info("Loading data...")
    data = load_all()
    stock_df = data["stock_data"]
    etp_df = data["etp_data"]

    # Candidate evaluation
    log.info("Evaluating %d candidates: %s", len(tickers), ", ".join(tickers))
    candidates = evaluate_candidates(tickers, stock_df=stock_df, etp_df=etp_df)

    # Universe rankings (appended to report)
    log.info("Computing universe rankings...")
    rankings, rex_funds = _compute_rankings(stock_df, etp_df)

    # Generate combined PDF
    pdf_bytes = generate_candidate_report(
        candidates,
        rankings=rankings,
        rex_funds=rex_funds,
    )

    today = datetime.now().strftime("%Y%m%d")
    out_path = REPORTS_DIR / f"Candidate_Evaluation_{today}.pdf"
    out_path.write_bytes(pdf_bytes)

    log.info("PDF saved: %s (%d bytes)", out_path, len(pdf_bytes))

    # Print summary
    for c in candidates:
        status = c["verdict"]
        print(f"  {c['ticker_clean']:8s} {status:10s} {c['reason']}")

    return out_path


def run_rankings_report() -> Path:
    """Run standalone universe rankings PDF."""
    from screener.data_loader import load_all
    from screener.report_generator import generate_rankings_report
    from screener.config import REPORTS_DIR

    REPORTS_DIR.mkdir(exist_ok=True)

    data = load_all()
    stock_df = data["stock_data"]
    etp_df = data["etp_data"]

    results, rex_funds = _compute_rankings(stock_df, etp_df)

    pdf_bytes = generate_rankings_report(results, rex_funds=rex_funds)

    today = datetime.now().strftime("%Y%m%d")
    out_path = REPORTS_DIR / f"ETF_Launch_Screener_{today}.pdf"
    out_path.write_bytes(pdf_bytes)

    log.info("PDF saved: %s (%d bytes)", out_path, len(pdf_bytes))
    return out_path


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python -m screener.generate_report SCCO AMPX ZETA   # Evaluate candidates")
        print("  python -m screener.generate_report --rankings        # Universe rankings")
        sys.exit(1)

    if args[0] == "--rankings":
        path = run_rankings_report()
    else:
        path = run_candidate_evaluation(args)

    print(f"\nReport saved: {path}")


if __name__ == "__main__":
    main()
