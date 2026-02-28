from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
import time
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy import select

from webapp.models import Trust, FilingAlert, TrustCandidate

log = logging.getLogger(__name__)

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
FORM_TYPES = "485BPOS,485APOS,485BXT"
PAUSE = 0.35
USER_AGENT = "REX-ETP-Tracker/2.0 (relasmar@rexfin.com)"


@dataclass
class EdgarHit:
    cik: str
    company_name: str
    accession_number: str
    form_type: str
    filed_date: str


@dataclass
class WatcherResult:
    alerts_created: int = 0
    alerts_skipped: int = 0
    candidates_new: int = 0
    candidates_updated: int = 0
    errors: list = field(default_factory=list)


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def poll_recent_filings(db, lookback_days: int = 1, form_types: str | None = None) -> WatcherResult:
    known_rows = db.execute(select(Trust.cik, Trust.id)).fetchall()
    cik_to_trust = {str(int(row[0])): row[1] for row in known_rows}
    known_ciks = set(cik_to_trust.keys())

    today = date.today()
    start = today - timedelta(days=lookback_days)
    hits = _query_edgar(form_types or FORM_TYPES, start.isoformat(), today.isoformat())

    result = WatcherResult()
    for hit in hits:
        try:
            if hit.cik in known_ciks:
                created = _upsert_filing_alert(db, cik_to_trust[hit.cik], hit)
                if created:
                    result.alerts_created += 1
                else:
                    result.alerts_skipped += 1
            else:
                is_new = _upsert_trust_candidate(db, hit)
                if is_new:
                    result.candidates_new += 1
                else:
                    result.candidates_updated += 1
        except Exception as e:
            result.errors.append(f"CIK {hit.cik}: {e}")
            log.warning("Error processing hit for CIK %s: %s", hit.cik, e)

    db.commit()
    return result


def _query_edgar(form_types: str, start_date: str, end_date: str) -> list[EdgarHit]:
    session = _get_session()
    hits: list[EdgarHit] = []
    offset = 0

    while True:
        params = {
            "forms": form_types,
            "dateRange": "custom",
            "startdt": start_date,
            "enddt": end_date,
            "from": offset,
        }
        time.sleep(PAUSE)
        try:
            resp = session.get(EFTS_URL, params=params, timeout=15)
        except requests.RequestException as e:
            log.error("EFTS request failed: %s", e)
            break

        if resp.status_code != 200:
            log.error("EFTS returned %d", resp.status_code)
            break

        data = resp.json()
        page_hits = data.get("hits", {}).get("hits", [])
        if not page_hits:
            break

        for h in page_hits:
            src = h.get("_source", {})
            ciks = src.get("ciks", [])
            if not ciks:
                continue
            hits.append(EdgarHit(
                cik=str(int(ciks[0])),
                company_name=src.get("entity_name", "Unknown"),
                accession_number=src.get("adsh", ""),
                form_type=src.get("form_type", ""),
                filed_date=src.get("file_date", ""),
            ))

        total = data.get("hits", {}).get("total", {}).get("value", 0)
        offset += len(page_hits)
        if offset >= total:
            break

    return hits


def _upsert_filing_alert(db, trust_id: int, hit: EdgarHit) -> bool:
    existing = db.query(FilingAlert).filter_by(accession_number=hit.accession_number).first()
    if existing:
        return False
    filed = None
    if hit.filed_date:
        try:
            filed = date.fromisoformat(hit.filed_date)
        except ValueError:
            pass
    alert = FilingAlert(
        trust_id=trust_id,
        accession_number=hit.accession_number,
        form_type=hit.form_type,
        filed_date=filed,
    )
    db.add(alert)
    return True


def _upsert_trust_candidate(db, hit: EdgarHit) -> bool:
    existing = db.query(TrustCandidate).filter_by(cik=hit.cik).first()
    if existing:
        existing.last_seen = datetime.utcnow()
        existing.filing_count += 1
        seen = json.loads(existing.form_types_seen or "[]")
        if hit.form_type not in seen:
            seen.append(hit.form_type)
            existing.form_types_seen = json.dumps(sorted(seen))
        return False
    candidate = TrustCandidate(
        cik=hit.cik,
        company_name=hit.company_name,
        form_types_seen=json.dumps([hit.form_type]),
    )
    db.add(candidate)
    return True
