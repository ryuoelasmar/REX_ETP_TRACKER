"""
Pipeline Service - Background pipeline execution and DB sync.

Wraps the existing CSV pipeline with database integration.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from webapp.database import SessionLocal
from webapp.models import PipelineRun

log = logging.getLogger(__name__)

_pipeline_lock = threading.Lock()
_pipeline_running = False

OUTPUT_DIR = Path("outputs")
SINCE_DATE = "2024-11-14"
USER_AGENT = "REX-ETP-Tracker/2.0 (relasmar@rexfin.com)"


def is_pipeline_running() -> bool:
    """Check if a pipeline run is in progress."""
    return _pipeline_running


def run_pipeline_background(triggered_by: str = "api") -> None:
    """Run the full pipeline in background, syncing results to DB."""
    global _pipeline_running

    if not _pipeline_lock.acquire(blocking=False):
        log.warning("Pipeline already running, skipping")
        return

    _pipeline_running = True
    db = SessionLocal()

    run = PipelineRun(
        started_at=datetime.utcnow(),
        status="running",
        triggered_by=triggered_by,
    )
    db.add(run)
    db.commit()

    try:
        from etp_tracker.run_pipeline import run_pipeline
        from etp_tracker.trusts import get_all_ciks, get_overrides

        n = run_pipeline(
            ciks=get_all_ciks(),
            overrides=get_overrides(),
            since=SINCE_DATE,
            refresh_submissions=True,
            user_agent=USER_AGENT,
        )

        # Sync to DB
        from webapp.services.sync_service import seed_trusts, sync_all
        seed_trusts(db)
        sync_all(db, OUTPUT_DIR)

        run.status = "completed"
        run.trusts_processed = n
        run.finished_at = datetime.utcnow()
        db.commit()

        log.info("Pipeline completed: %d trusts processed", n)

    except Exception as e:
        log.error("Pipeline failed: %s", e)
        run.status = "failed"
        run.error_message = str(e)[:500]
        run.finished_at = datetime.utcnow()
        db.commit()

    finally:
        db.close()
        _pipeline_running = False
        _pipeline_lock.release()
