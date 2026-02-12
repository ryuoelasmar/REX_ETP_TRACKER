"""Load and validate Bloomberg data from the decision support Excel file."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from screener.config import DATA_FILE, ETP_COLS_NEEDED

log = logging.getLogger(__name__)


def _resolve_path(path: Path | str | None = None) -> Path:
    """Return the data file path, defaulting to config."""
    p = Path(path) if path else DATA_FILE
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {p}")
    return p


def load_stock_data(path: Path | str | None = None) -> pd.DataFrame:
    """Load stock_data sheet (US equity universe, ~4,992 rows x 23 cols)."""
    p = _resolve_path(path)
    df = pd.read_excel(p, sheet_name="stock_data", engine="openpyxl")
    log.info("stock_data loaded: %d rows x %d cols", len(df), len(df.columns))

    # Normalize ticker: strip " US" suffix, store original
    if "Ticker" in df.columns:
        df["ticker_raw"] = df["Ticker"]
        df["ticker_clean"] = df["Ticker"].str.replace(r"\s+US$", "", regex=True)

    # Optimize dtypes
    float_cols = [
        "Mkt Cap", "Volatility 10D", "Volatility 30D", "Volatility 90D",
        "Short Interest Ratio", "Institutional Owner % Shares Outstanding",
        "% Insider Shares Outstanding", "News Sentiment Daily Avg",
        "Last Price", "52W High", "52W Low", "Turnover / Traded Value",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float32")

    return df


def load_etp_data(path: Path | str | None = None) -> pd.DataFrame:
    """Load etp_data sheet (full US ETP universe, select needed columns only)."""
    p = _resolve_path(path)

    # Read all columns first to filter available ones
    all_cols = pd.read_excel(p, sheet_name="etp_data", engine="openpyxl", nrows=0).columns.tolist()
    use_cols = [c for c in ETP_COLS_NEEDED if c in all_cols]
    missing = set(ETP_COLS_NEEDED) - set(all_cols)
    if missing:
        log.warning("etp_data missing columns (skipped): %s", missing)

    df = pd.read_excel(p, sheet_name="etp_data", usecols=use_cols, engine="openpyxl")
    log.info("etp_data loaded: %d rows x %d cols (of %d available)", len(df), len(df.columns), len(all_cols))

    # Normalize underlier ticker
    underlier_col = "q_category_attributes.map_li_underlier"
    if underlier_col in df.columns:
        df["underlier_clean"] = df[underlier_col].fillna("").str.replace(r"\s+US$", "", regex=True)

    return df


def load_filing_data(path: Path | str | None = None) -> pd.DataFrame:
    """Load filing_data sheet (pipeline output, ~281 rows)."""
    p = _resolve_path(path)
    df = pd.read_excel(p, sheet_name="filing_data", engine="openpyxl")
    log.info("filing_data loaded: %d rows x %d cols", len(df), len(df.columns))
    return df


def load_rex_funds(path: Path | str | None = None) -> pd.DataFrame:
    """Load rex_funds sheet (REX product list, ~91 rows)."""
    p = _resolve_path(path)
    df = pd.read_excel(p, sheet_name="rex_funds", engine="openpyxl")
    log.info("rex_funds loaded: %d rows x %d cols", len(df), len(df.columns))
    return df


def load_all(path: Path | str | None = None) -> dict[str, pd.DataFrame]:
    """Load all four datasets, return as dict."""
    p = _resolve_path(path)
    return {
        "stock_data": load_stock_data(p),
        "etp_data": load_etp_data(p),
        "filing_data": load_filing_data(p),
        "rex_funds": load_rex_funds(p),
    }
