"""
13F Institutional Holdings Pipeline

Ingests SEC 13F-HR quarterly bulk datasets and maps holdings
to our ETP universe via CUSIP. Supports both historical (bulk ZIP)
and incremental (EFTS search) ingestion.

Usage:
    python -m etp_tracker.thirteen_f seed
    python -m etp_tracker.thirteen_f ingest 2025q4
    python -m etp_tracker.thirteen_f incremental
"""
from __future__ import annotations

import io
import logging
import os
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Project path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webapp.database import SessionLocal, init_db
from webapp.models import CusipMapping, Holding, Institution, MktMasterData

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BATCH_SIZE = 1000
SEC_BULK_URL = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/13f{quarter}.zip"
SEC_EFTS_URL = (
    "https://efts.sec.gov/LATEST/search-index"
    "?q=%2213F-HR%22&dateRange=custom&startdt={start}&enddt={end}&forms=13F-HR"
)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
def _fetch(url: str, user_agent: str, timeout: int = 30) -> requests.Response:
    """GET with SEC-mandated rate limit and proper User-Agent."""
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    time.sleep(0.35)  # SEC rate limit
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# 1. seed_cusip_mappings
# ---------------------------------------------------------------------------
def seed_cusip_mappings() -> int:
    """Seed cusip_mappings from mkt_master_data.

    Upserts on CUSIP: if a CUSIP already exists in the mapping table,
    update ticker/fund_name; otherwise insert a new row.

    Returns:
        Count of CUSIPs seeded or updated.
    """
    db = SessionLocal()
    try:
        # Pull all mkt_master_data rows that have a non-empty CUSIP
        master_rows = db.execute(
            select(MktMasterData.cusip, MktMasterData.ticker, MktMasterData.fund_name)
            .where(MktMasterData.cusip.isnot(None))
            .where(MktMasterData.cusip != "")
        ).all()

        log.info("Found %d rows with CUSIPs in mkt_master_data", len(master_rows))

        count = 0
        for cusip, ticker, fund_name in master_rows:
            cusip = cusip.strip()
            if not cusip:
                continue

            existing = db.execute(
                select(CusipMapping).where(CusipMapping.cusip == cusip)
            ).scalar_one_or_none()

            if existing:
                existing.ticker = ticker
                existing.fund_name = fund_name
                existing.source = "mkt_master"
            else:
                db.add(CusipMapping(
                    cusip=cusip,
                    ticker=ticker,
                    fund_name=fund_name,
                    source="mkt_master",
                ))
            count += 1

            if count % BATCH_SIZE == 0:
                db.commit()
                log.info("  Committed %d CUSIP mappings...", count)

        db.commit()
        log.info("Seeded %d CUSIP mappings from mkt_master_data", count)
        return count
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. ingest_13f_dataset  (bulk historical)
# ---------------------------------------------------------------------------
def ingest_13f_dataset(
    quarter: str,
    user_agent: str,
    cache_dir: str = "http_cache",
) -> dict:
    """Download and ingest a quarterly 13F bulk dataset from SEC.

    Args:
        quarter: e.g. "2025q4"
        user_agent: SEC-compliant User-Agent string
        cache_dir: directory for caching downloaded ZIPs

    Returns:
        Stats dict with counts for institutions, holdings, matched CUSIPs, etc.
    """
    stats = {
        "quarter": quarter,
        "institutions_upserted": 0,
        "holdings_inserted": 0,
        "cusips_matched": 0,
        "errors": [],
    }

    # ------------------------------------------------------------------
    # Step 1: Download ZIP (with cache)
    # ------------------------------------------------------------------
    cache_path = Path(cache_dir) / "13f"
    cache_path.mkdir(parents=True, exist_ok=True)
    zip_file = cache_path / f"13f{quarter}.zip"

    if zip_file.exists():
        log.info("Using cached ZIP: %s", zip_file)
    else:
        url = SEC_BULK_URL.format(quarter=quarter)
        log.info("Downloading %s ...", url)
        try:
            resp = _fetch(url, user_agent, timeout=120)
            zip_file.write_bytes(resp.content)
            log.info("Downloaded %s (%.1f MB)", zip_file.name, len(resp.content) / 1e6)
        except requests.HTTPError as exc:
            msg = f"Failed to download {url}: {exc}"
            log.error(msg)
            stats["errors"].append(msg)
            return stats

    # ------------------------------------------------------------------
    # Step 2: Extract TSVs from ZIP
    # ------------------------------------------------------------------
    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            names = zf.namelist()
            log.info("ZIP contents: %s", names)

            tsv_data = {}
            for target in ("INFOTABLE.tsv", "SUBMISSION.tsv", "COVERPAGE.tsv"):
                # Case-insensitive match (SEC varies casing across quarters)
                match = next((n for n in names if n.upper() == target.upper()), None)
                if match is None:
                    msg = f"Missing {target} in ZIP"
                    log.error(msg)
                    stats["errors"].append(msg)
                    return stats
                raw = zf.read(match)
                tsv_data[target.upper()] = raw.decode("utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        msg = f"Corrupt ZIP file: {exc}"
        log.error(msg)
        stats["errors"].append(msg)
        return stats

    # ------------------------------------------------------------------
    # Step 3: Parse SUBMISSION + COVERPAGE -> upsert Institutions
    # ------------------------------------------------------------------
    sub_df = pd.read_csv(
        io.StringIO(tsv_data["SUBMISSION.TSV"]),
        sep="\t",
        engine="python",
        on_bad_lines="skip",
        dtype=str,
    )
    cover_df = pd.read_csv(
        io.StringIO(tsv_data["COVERPAGE.TSV"]),
        sep="\t",
        engine="python",
        on_bad_lines="skip",
        dtype=str,
    )

    # Normalise column names to uppercase
    sub_df.columns = [c.strip().upper() for c in sub_df.columns]
    cover_df.columns = [c.strip().upper() for c in cover_df.columns]

    log.info("SUBMISSION rows: %d, COVERPAGE rows: %d", len(sub_df), len(cover_df))

    # Build accession -> CIK + report date from SUBMISSION
    accession_map: dict[str, dict] = {}
    for _, row in sub_df.iterrows():
        acc = str(row.get("ACCESSION_NUMBER", "")).strip()
        if not acc:
            continue
        accession_map[acc] = {
            "cik": str(row.get("CIK", "")).strip(),
            "filing_date": str(row.get("FILING_DATE", "")).strip(),
            "report_date": str(row.get("PERIODOFREPORT", "")).strip(),
        }

    # Build CIK -> company name from COVERPAGE
    cik_names: dict[str, str] = {}
    for _, row in cover_df.iterrows():
        cik = str(row.get("CIK", "")).strip()
        name = str(row.get("COMPANYNAME", "")).strip()
        if cik and name:
            cik_names[cik] = name

    # Upsert institutions
    db = SessionLocal()
    try:
        cik_to_inst_id: dict[str, int] = {}
        unique_ciks = set(cik_names.keys()) | {v["cik"] for v in accession_map.values() if v["cik"]}

        for cik in unique_ciks:
            if not cik:
                continue
            existing = db.execute(
                select(Institution).where(Institution.cik == cik)
            ).scalar_one_or_none()

            name = cik_names.get(cik, f"CIK {cik}")

            if existing:
                existing.name = name
                existing.filing_count = existing.filing_count + 1
                existing.updated_at = datetime.utcnow()
                cik_to_inst_id[cik] = existing.id
            else:
                inst = Institution(cik=cik, name=name, filing_count=1)
                db.add(inst)
                db.flush()  # get the id
                cik_to_inst_id[cik] = inst.id
            stats["institutions_upserted"] += 1

        db.commit()
        log.info("Upserted %d institutions", stats["institutions_upserted"])

        # ------------------------------------------------------------------
        # Step 4: Parse INFOTABLE -> insert Holdings
        # ------------------------------------------------------------------
        info_df = pd.read_csv(
            io.StringIO(tsv_data["INFOTABLE.TSV"]),
            sep="\t",
            engine="python",
            on_bad_lines="skip",
            dtype=str,
        )
        info_df.columns = [c.strip().upper() for c in info_df.columns]
        log.info("INFOTABLE rows: %d", len(info_df))

        # Pre-load CUSIP mappings for matching
        cusip_set = set(
            row[0] for row in db.execute(select(CusipMapping.cusip)).all()
        )

        batch: list[Holding] = []
        for idx, row in info_df.iterrows():
            acc = str(row.get("ACCESSION_NUMBER", "")).strip()
            acc_info = accession_map.get(acc, {})
            cik = acc_info.get("cik", "")
            inst_id = cik_to_inst_id.get(cik)

            if inst_id is None:
                continue

            # Parse report date
            report_date_str = acc_info.get("report_date", "")
            try:
                report_dt = datetime.strptime(report_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                report_dt = date(1900, 1, 1)

            # Parse value (in thousands as reported by SEC)
            try:
                value = float(row.get("VALUE", 0))
            except (ValueError, TypeError):
                value = None

            # Parse shares
            try:
                shares = float(row.get("SSHPRNAMT", 0))
            except (ValueError, TypeError):
                shares = None

            # Parse voting authorities
            def _safe_int(val):
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return None

            cusip = str(row.get("CUSIP", "")).strip()

            holding = Holding(
                institution_id=inst_id,
                report_date=report_dt,
                filing_accession=acc,
                issuer_name=str(row.get("NAMEOFISSUER", "")).strip() or None,
                cusip=cusip or None,
                value_usd=value,
                shares=shares,
                share_type=str(row.get("SSHPRNAMTTYPE", "")).strip() or None,
                investment_discretion=str(row.get("INVESTMENTDISCRETION", "")).strip() or None,
                voting_sole=_safe_int(row.get("VOTINGAUTHORITY_SOLE")),
                voting_shared=_safe_int(row.get("VOTINGAUTHORITY_SHARED")),
                voting_none=_safe_int(row.get("VOTINGAUTHORITY_NONE")),
            )
            batch.append(holding)

            # Track CUSIP matches
            if cusip and cusip in cusip_set:
                stats["cusips_matched"] += 1

            if len(batch) >= BATCH_SIZE:
                db.add_all(batch)
                db.commit()
                stats["holdings_inserted"] += len(batch)
                if stats["holdings_inserted"] % 10000 == 0:
                    log.info("  Inserted %d holdings...", stats["holdings_inserted"])
                batch = []

        # Final batch
        if batch:
            db.add_all(batch)
            db.commit()
            stats["holdings_inserted"] += len(batch)

        log.info(
            "Ingestion complete: %d institutions, %d holdings, %d CUSIP matches",
            stats["institutions_upserted"],
            stats["holdings_inserted"],
            stats["cusips_matched"],
        )

    except Exception as exc:
        db.rollback()
        msg = f"Error during ingestion: {exc}"
        log.error(msg, exc_info=True)
        stats["errors"].append(msg)
    finally:
        db.close()

    return stats


# ---------------------------------------------------------------------------
# 3. ingest_13f_incremental  (stub)
# ---------------------------------------------------------------------------
def ingest_13f_incremental(
    user_agent: str,
    days_back: int = 7,
    cache_dir: str = "http_cache",
) -> list[str]:
    """Search EDGAR EFTS for recent 13F-HR filings.

    This is a stub -- it discovers accession numbers but does not yet
    parse the individual XML infotables. Full XML parsing is TODO.

    Args:
        user_agent: SEC-compliant User-Agent string
        days_back: how many days back to search
        cache_dir: directory for caching (unused in stub)

    Returns:
        List of accession numbers found.
    """
    end = date.today()
    start = end - timedelta(days=days_back)

    url = SEC_EFTS_URL.format(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
    )
    log.info("Searching EFTS for 13F-HR filings: %s to %s", start, end)

    accessions: list[str] = []
    try:
        resp = _fetch(url, user_agent)
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            acc = source.get("file_num") or source.get("accession_no", "")
            if acc:
                accessions.append(acc)
        log.info("Found %d recent 13F-HR filings (stub -- not parsed)", len(accessions))
    except Exception as exc:
        log.error("EFTS search failed: %s", exc)

    # TODO: For each accession, fetch the 13F-HR XML infotable and parse
    #       individual holdings. The bulk ZIP approach handles historical
    #       data; this path is for near-real-time updates between quarters.

    return accessions


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    init_db()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m etp_tracker.thirteen_f seed")
        print("  python -m etp_tracker.thirteen_f ingest 2025q4")
        print("  python -m etp_tracker.thirteen_f incremental")
        sys.exit(1)

    cmd = sys.argv[1]
    user_agent = "REX-ETP-FilingTracker/2.0 (contact: relasmar@rexfin.com)"

    if cmd == "seed":
        n = seed_cusip_mappings()
        print(f"Seeded {n} CUSIP mappings from mkt_master_data.")

    elif cmd == "ingest":
        if len(sys.argv) < 3:
            print("Error: provide quarter, e.g. 2025q4")
            sys.exit(1)
        quarter = sys.argv[2]
        result = ingest_13f_dataset(quarter, user_agent)
        print(f"Quarter: {result['quarter']}")
        print(f"  Institutions upserted: {result['institutions_upserted']}")
        print(f"  Holdings inserted:     {result['holdings_inserted']}")
        print(f"  CUSIPs matched:        {result['cusips_matched']}")
        if result["errors"]:
            print(f"  Errors: {len(result['errors'])}")
            for e in result["errors"]:
                print(f"    - {e}")

    elif cmd == "incremental":
        accessions = ingest_13f_incremental(user_agent)
        print(f"Found {len(accessions)} recent 13F-HR filings (stub).")
        for acc in accessions[:10]:
            print(f"  {acc}")
        if len(accessions) > 10:
            print(f"  ... and {len(accessions) - 10} more")

    else:
        print(f"Unknown command: {cmd}")
        print("Valid commands: seed, ingest, incremental")
        sys.exit(1)
