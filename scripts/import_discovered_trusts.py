"""
Bulk import discovered trusts into the rexfinhub database.

Reads data/discovered_trusts.json (1,944 entries from SEC EDGAR discovery)
and upserts into the trusts table. Existing curated trusts are updated with
new metadata but retain source="curated". New trusts get source="bulk_discovery".

Usage:
    python scripts/import_discovered_trusts.py
    python scripts/import_discovered_trusts.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webapp.database import SessionLocal, init_db, engine
from webapp.models import Trust

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REX_CIKS = {"2043954", "1771146"}

_485_FORMS = {"485APOS", "485BPOS", "485BXT", "497", "497J", "497K"}
_S_FORMS = {"S-1", "S-1/A", "S-3", "S-3/A"}

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "discovered_trusts.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _normalise_cik(raw: str) -> str:
    """Strip leading zeros: '0001605941' -> '1605941'."""
    return str(int(raw))


def _classify_entity_type(entry: dict) -> str:
    """Determine entity_type from JSON record."""
    forms = set(entry.get("forms_485", []))
    has_485 = bool(forms & _485_FORMS)

    if entry.get("entity_type") == "investment" and has_485:
        return "etf_trust"
    if entry.get("entity_type") == "operating":
        return "grantor_trust"
    return "unknown"


def _classify_regulatory_act(entry: dict) -> str:
    """Determine regulatory_act from forms list."""
    forms = set(entry.get("forms_485", []))
    has_485 = bool(forms & _485_FORMS)
    has_s = bool(forms & _S_FORMS)

    if has_485:
        return "40_act"
    if has_s:
        return "33_act"
    return "unknown"


def _parse_date(date_str: str | None) -> date | None:
    """Parse ISO date string, return None on failure."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _ensure_columns(eng):
    """Add missing Phase 1a columns to the trusts table if needed.

    init_db() only creates tables that don't exist; it won't ALTER
    existing ones. This handles the migration inline.
    """
    import sqlite3

    conn = eng.raw_connection()
    try:
        cursor = conn.cursor()
        existing = {row[1] for row in cursor.execute("PRAGMA table_info(trusts)").fetchall()}

        migrations = [
            ("entity_type", "VARCHAR(30)"),
            ("regulatory_act", "VARCHAR(20)"),
            ("sic_code", "VARCHAR(10)"),
            ("filing_count", "INTEGER"),
            ("first_filed", "DATE"),
            ("last_filed", "DATE"),
            ("source", "VARCHAR(30)"),
        ]

        added = []
        for col, col_type in migrations:
            if col not in existing:
                cursor.execute(f"ALTER TABLE trusts ADD COLUMN {col} {col_type}")
                added.append(col)

        if added:
            conn.commit()
            print(f"Migrated trusts table: added columns {added}")
        else:
            print("Trusts table schema up to date -- no migration needed.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import discovered trusts into DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    # Load JSON
    if not DATA_FILE.exists():
        print(f"FATAL: {DATA_FILE} not found")
        sys.exit(1)

    with open(DATA_FILE, encoding="utf-8") as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries from {DATA_FILE.name}")

    # Init DB + migrate schema if needed
    init_db()
    _ensure_columns(engine)
    session = SessionLocal()

    try:
        _run_import(session, entries, dry_run=args.dry_run)
    finally:
        session.close()


def _run_import(session, entries: list[dict], *, dry_run: bool = False):
    """Core import logic."""

    # Build lookup of existing trusts by CIK
    existing = {t.cik: t for t in session.query(Trust).all()}
    print(f"Existing trusts in DB: {len(existing)}")

    # Track slugs already in DB + newly created to detect collisions
    used_slugs: set[str] = {t.slug for t in existing.values()}

    # Counters
    created = 0
    updated = 0
    skipped = 0
    type_counts: dict[str, int] = {}

    for entry in entries:
        cik = _normalise_cik(entry["cik"])
        name = entry["name"].strip()
        entity_type = _classify_entity_type(entry)
        regulatory_act = _classify_regulatory_act(entry)
        sic_code = entry.get("sic", "").strip() or None
        filing_count = len(entry.get("forms_485", []))
        last_filed = _parse_date(entry.get("latest_485"))
        is_rex = cik in _REX_CIKS

        # Track classification
        type_counts[entity_type] = type_counts.get(entity_type, 0) + 1

        # Generate slug, handle duplicates
        slug = _slugify(name)
        if not slug:
            slug = f"trust-{cik}"
        if slug in used_slugs:
            # Check if the collision is the same trust (same CIK owns that slug)
            owns_slug = cik in existing and existing[cik].slug == slug
            if not owns_slug:
                slug = f"{slug}-{cik}"

        if cik in existing:
            # UPDATE existing trust
            trust = existing[cik]
            trust.is_active = True
            trust.entity_type = entity_type
            trust.regulatory_act = regulatory_act
            if sic_code:
                trust.sic_code = sic_code
            trust.filing_count = filing_count
            if last_filed:
                trust.last_filed = last_filed
            trust.is_rex = is_rex
            # Preserve curated source -- existing trusts predate bulk discovery
            if trust.source not in ("curated",):
                trust.source = "curated"
            trust.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            # CREATE new trust
            trust = Trust(
                cik=cik,
                name=name,
                slug=slug,
                is_rex=is_rex,
                is_active=True,
                entity_type=entity_type,
                regulatory_act=regulatory_act,
                sic_code=sic_code,
                filing_count=filing_count,
                last_filed=last_filed,
                source="bulk_discovery",
            )
            session.add(trust)
            used_slugs.add(slug)
            created += 1

    # Summary
    print("")
    print("=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"  Entries processed : {len(entries)}")
    print(f"  New trusts created: {created}")
    print(f"  Existing updated  : {updated}")
    print(f"  Skipped           : {skipped}")
    print("")
    print("Classification breakdown:")
    for etype, count in sorted(type_counts.items()):
        print(f"  {etype:20s}: {count}")
    print("")

    if dry_run:
        print("DRY RUN -- no changes committed. Rolling back.")
        session.rollback()
    else:
        session.commit()
        print("Committed to database.")

    # Post-commit verification
    total = session.query(Trust).count()
    print(f"Total trusts in DB now: {total}")


if __name__ == "__main__":
    main()
