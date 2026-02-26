"""
One-time migration: Import trust requests and digest subscribers from flat files into DB.

Run once after deploying the DB-based admin panel:
    python scripts/migrate_admin_to_db.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from webapp.database import init_db, SessionLocal
from webapp.models import TrustRequest, DigestSubscriber

REQUESTS_FILE = PROJECT_ROOT / "config" / "trust_requests.txt"
SUBSCRIBERS_FILE = PROJECT_ROOT / "config" / "digest_subscribers.txt"


def normalize_cik(cik: str) -> str:
    """Strip leading zeros for consistent CIK comparison."""
    return str(int(cik)) if cik and cik.strip().isdigit() else cik.strip()


def migrate_trust_requests(db):
    """Import trust_requests.txt into trust_requests table."""
    if not REQUESTS_FILE.exists():
        print(f"  {REQUESTS_FILE} not found, skipping.")
        return 0

    count = 0
    for line in REQUESTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 4:
            print(f"  Skipping malformed line: {line}")
            continue

        status, cik, name, timestamp = parts[0], parts[1], parts[2], parts[3]
        cik = normalize_cik(cik)

        # Check for existing entry
        existing = db.query(TrustRequest).filter(
            TrustRequest.cik == cik
        ).first()
        if existing:
            print(f"  Already exists: CIK {cik} ({name}) - skipping")
            continue

        try:
            requested_at = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            requested_at = datetime.utcnow()

        resolved_at = datetime.utcnow() if status != "PENDING" else None

        db.add(TrustRequest(
            cik=cik,
            name=name,
            status=status,
            requested_at=requested_at,
            resolved_at=resolved_at,
        ))
        count += 1

    db.commit()
    return count


def migrate_subscribers(db):
    """Import digest_subscribers.txt into digest_subscribers table."""
    if not SUBSCRIBERS_FILE.exists():
        print(f"  {SUBSCRIBERS_FILE} not found, skipping.")
        return 0

    count = 0
    for line in SUBSCRIBERS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            print(f"  Skipping malformed line: {line}")
            continue

        status, email, timestamp = parts[0], parts[1].strip().lower(), parts[2]

        # Check for existing entry
        existing = db.query(DigestSubscriber).filter(
            DigestSubscriber.email == email
        ).first()
        if existing:
            print(f"  Already exists: {email} - skipping")
            continue

        try:
            requested_at = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            requested_at = datetime.utcnow()

        resolved_at = datetime.utcnow() if status != "PENDING" else None

        db.add(DigestSubscriber(
            email=email,
            status=status,
            requested_at=requested_at,
            resolved_at=resolved_at,
        ))
        count += 1

    db.commit()
    return count


def main():
    print("=== Migrating admin state to database ===\n")

    init_db()
    db = SessionLocal()

    try:
        print("[1/2] Migrating trust requests...")
        n = migrate_trust_requests(db)
        print(f"  Imported {n} trust requests.\n")

        print("[2/2] Migrating digest subscribers...")
        n = migrate_subscribers(db)
        print(f"  Imported {n} subscribers.\n")

        print("=== Migration complete ===")
        print("Flat files are no longer needed for admin operations.")
        print("They can be kept as backup or removed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
