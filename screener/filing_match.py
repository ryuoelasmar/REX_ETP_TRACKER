"""Cross-reference screener candidates with SEC filing data."""
from __future__ import annotations

import logging
import re

import pandas as pd

log = logging.getLogger(__name__)

# Patterns to extract underlying ticker from fund names
_TREX_PATTERN = re.compile(
    r"T-REX\s+\d+[Xx]\s+(?:Long|Short|Inverse)\s+(.+?)\s+(?:Daily\s+Target\s+)?ETF",
    re.IGNORECASE,
)
_GENERIC_LEVERAGE_PATTERN = re.compile(
    r"\d+[Xx]\s+(?:Long|Short|Inverse|Bull|Bear)\s+(.+?)\s+(?:Daily|ETF|Fund)",
    re.IGNORECASE,
)

# Map common company names to tickers
_NAME_TO_TICKER = {
    "NVIDIA": "NVDA", "TESLA": "TSLA", "APPLE": "AAPL", "AMAZON": "AMZN",
    "MICROSOFT": "MSFT", "META": "META", "ALPHABET": "GOOGL", "GOOGLE": "GOOGL",
    "COINBASE": "COIN", "MICROSTRATEGY": "MSTR", "PALANTIR": "PLTR",
    "BROADCOM": "AVGO", "AMD": "AMD", "NETFLIX": "NFLX", "UBER": "UBER",
    "SNOWFLAKE": "SNOW", "SHOPIFY": "SHOP", "ALIBABA": "BABA",
    "INTEL": "INTC", "ARM": "ARM", "ELI LILLY": "LLY",
    "COSTCO": "COST", "WALMART": "WMT", "JPMORGAN": "JPM",
    "BOEING": "BA", "DISNEY": "DIS", "ROBINHOOD": "HOOD",
}


def _extract_underlier_from_name(fund_name: str) -> str | None:
    """Try to extract the underlying ticker/name from a fund name."""
    if not fund_name:
        return None

    # Try T-REX pattern first
    m = _TREX_PATTERN.search(fund_name)
    if m:
        name = m.group(1).strip()
        # Check if it's already a ticker (short, all caps)
        if len(name) <= 5 and name.isupper():
            return name
        # Map common names
        for key, ticker in _NAME_TO_TICKER.items():
            if key in name.upper():
                return ticker
        return name

    # Try generic leverage pattern
    m = _GENERIC_LEVERAGE_PATTERN.search(fund_name)
    if m:
        name = m.group(1).strip()
        if len(name) <= 5 and name.isupper():
            return name
        for key, ticker in _NAME_TO_TICKER.items():
            if key in name.upper():
                return ticker
        return name

    return None


def match_filings(
    candidates_df: pd.DataFrame,
    filing_df: pd.DataFrame,
) -> pd.DataFrame:
    """Cross-reference candidate stocks with filing data.

    Adds 'filing_status' column to candidates:
      - "REX Filed - Effective [date]"
      - "REX Filed - Pending [date]"
      - "Not Filed"
      - "Competitor Filing Detected"
    """
    df = candidates_df.copy()
    df["filing_status"] = "Not Filed"

    if filing_df is None or filing_df.empty:
        return df

    # Build lookup: ticker -> filing info
    filing_lookup: dict[str, list[dict]] = {}
    for _, row in filing_df.iterrows():
        fund_name = str(row.get("Fund Name", ""))
        ticker = _extract_underlier_from_name(fund_name)
        if not ticker:
            continue

        ticker_upper = ticker.upper()
        if ticker_upper not in filing_lookup:
            filing_lookup[ticker_upper] = []

        filing_lookup[ticker_upper].append({
            "fund_name": fund_name,
            "status": str(row.get("Status", "")),
            "expected_effective": str(row.get("Expected Effective", "")),
            "is_rex": "T-REX" in fund_name.upper() or "REX" in fund_name.upper(),
        })

    # Match candidates
    ticker_col = "ticker_clean" if "ticker_clean" in df.columns else "Ticker"
    for idx, row in df.iterrows():
        candidate_ticker = str(row.get(ticker_col, "")).upper()
        if not candidate_ticker or candidate_ticker not in filing_lookup:
            continue

        filings = filing_lookup[candidate_ticker]
        rex_filings = [f for f in filings if f["is_rex"]]
        other_filings = [f for f in filings if not f["is_rex"]]

        if rex_filings:
            f = rex_filings[0]
            if f["status"] == "EFFECTIVE":
                df.at[idx, "filing_status"] = f"REX Filed - Effective"
            else:
                effective = f["expected_effective"]
                df.at[idx, "filing_status"] = f"REX Filed - Pending ({effective})"
        elif other_filings:
            df.at[idx, "filing_status"] = "Competitor Filing Detected"

    # Stats
    status_counts = df["filing_status"].value_counts()
    log.info("Filing match results: %s", status_counts.to_dict())

    return df
