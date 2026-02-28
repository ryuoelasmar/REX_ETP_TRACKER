"""Fetch SEC EDGAR daily form index to detect new filings without per-CIK queries.

The daily index is a pipe-delimited flat file published each trading day at::

    https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/form{date}.idx

This lets us check for new 485-series filings in a single HTTP request instead
of hitting every CIK individually -- useful for fast incremental runs.

Usage::

    from etp_tracker.index_client import get_todays_485_filings
    result = get_todays_485_filings(known_ciks={"12345", "67890"})
    # result = {"known": [...], "unknown": [...], "total_485": N}
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import requests

log = logging.getLogger(__name__)

try:
    from .config import USER_AGENT_DEFAULT
except Exception:
    USER_AGENT_DEFAULT = "REX-ETP-FilingTracker/1.0 (contact: set USER_AGENT)"

DAILY_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/daily-index/"
    "{year}/QTR{qtr}/form{date}.idx"
)
FORM_PREFIX = "485"  # matches 485BPOS, 485APOS, 485BXT, etc.


def _quarter(d: date) -> int:
    """Calendar quarter (1-4) for a date."""
    return (d.month - 1) // 3 + 1


def fetch_daily_index(
    target_date: Optional[date] = None,
    user_agent: str = USER_AGENT_DEFAULT,
    timeout: int = 30,
) -> list[dict]:
    """Download and parse a daily form index.

    Returns list of ``{cik, company, form, date, filename}`` dicts.
    Returns empty list on weekends/holidays (HTTP 404).
    """
    d = target_date or date.today()
    url = DAILY_INDEX_URL.format(
        year=d.year,
        qtr=_quarter(d),
        date=d.strftime("%Y%m%d"),
    )

    headers = {"User-Agent": user_agent}
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code == 404:
        log.info("No daily index for %s (likely weekend/holiday)", d)
        return []
    resp.raise_for_status()

    filings = []
    lines = resp.text.splitlines()

    # Skip header lines until the dashed separator
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith("---"):
            data_start = i + 1
            break

    for line in lines[data_start:]:
        parts = line.split("|")
        if len(parts) < 5:
            continue
        cik_raw, company, form_type, filed_date, filename = [
            p.strip() for p in parts[:5]
        ]
        try:
            cik_norm = str(int(cik_raw))
        except (ValueError, TypeError):
            continue
        filings.append({
            "cik": cik_norm,
            "company": company,
            "form": form_type,
            "date": filed_date,
            "filename": filename,
        })

    log.info("Parsed %d filings from daily index for %s", len(filings), d)
    return filings


def get_todays_485_filings(
    known_ciks: Optional[set[str]] = None,
    user_agent: str = USER_AGENT_DEFAULT,
    target_date: Optional[date] = None,
) -> dict:
    """Get today's 485-series filings. Optionally filter to known CIKs.

    Returns:
        If ``known_ciks`` provided::

            {"known": [...], "unknown": [...], "total_485": N}

        Otherwise::

            {"all": [...], "total_485": N}
    """
    filings = fetch_daily_index(
        target_date=target_date, user_agent=user_agent
    )

    # Filter to 485-series forms
    filings_485 = [f for f in filings if f["form"].startswith(FORM_PREFIX)]

    if known_ciks is not None:
        known = [f for f in filings_485 if f["cik"] in known_ciks]
        unknown = [f for f in filings_485 if f["cik"] not in known_ciks]
        return {"known": known, "unknown": unknown, "total_485": len(filings_485)}

    return {"all": filings_485, "total_485": len(filings_485)}
