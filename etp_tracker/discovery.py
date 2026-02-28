from __future__ import annotations

import json
import logging

from etp_tracker.sec_client import SECClient
from webapp.models import TrustCandidate

log = logging.getLogger(__name__)


def enrich_candidate(client: SECClient, candidate: TrustCandidate) -> dict | None:
    try:
        data = client.load_submissions_json(candidate.cik)
    except Exception as e:
        log.warning("Failed to fetch submissions for CIK %s: %s", candidate.cik, e)
        return None

    entity_type = data.get("entityType", "")
    sic = data.get("sic", "")
    recent = data.get("filings", {}).get("recent", {})
    forms = list(set(recent.get("form", [])))

    score = score_etf_trust_likelihood(entity_type, sic, forms, candidate.company_name)

    return {
        "entity_type": entity_type,
        "sic_code": sic,
        "recent_forms": forms,
        "etf_trust_score": score,
    }


def score_etf_trust_likelihood(
    entity_type: str,
    sic_code: str,
    recent_forms: list[str],
    company_name: str,
) -> float:
    score = 0.0
    if entity_type and "investment company" in entity_type.lower():
        score += 0.35
    if sic_code == "6726":
        score += 0.25
    prospectus_forms = {"485BPOS", "485APOS", "485BXT", "N-1A"}
    if any(f in prospectus_forms for f in recent_forms):
        score += 0.20
    name_lower = company_name.lower()
    if "trust" in name_lower:
        score += 0.10
    if "etf" in name_lower or "fund" in name_lower:
        score += 0.10
    return min(score, 1.0)


def batch_enrich(client: SECClient, db, status: str = "new", max_batch: int = 50) -> int:
    candidates = db.query(TrustCandidate).filter_by(status=status).limit(max_batch).all()
    enriched = 0
    for c in candidates:
        result = enrich_candidate(client, c)
        if result:
            c.etf_trust_score = result["etf_trust_score"]
            enriched += 1
    db.commit()
    return enriched
