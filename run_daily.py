"""
Daily Pipeline Runner

Run this script daily at 5pm via Windows Task Scheduler.
It refreshes all trust data, generates Excel files, and sends email digest.

Setup Task Scheduler:
    schtasks /create /tn "ETP_Filing_Tracker" /tr "python D:\\REX_ETP_TRACKER\\run_daily.py" /sc daily /st 17:00

To run manually:
    python run_daily.py
"""
from __future__ import annotations
import time
import sys
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from etp_tracker.run_pipeline import run_pipeline
from etp_tracker.trusts import get_all_ciks, get_overrides
from etp_tracker.email_alerts import send_digest_email


OUTPUT_DIR = Path("outputs")
SINCE_DATE = "2024-11-14"  # Earliest REX filing
USER_AGENT = "REX-ETP-Tracker/2.0 (relasmar@rexfin.com)"
DASHBOARD_URL = ""  # Set after deploying to Streamlit Cloud


def export_excel(output_dir: Path) -> None:
    """Generate combined Excel files from all trust outputs."""
    import pandas as pd

    # Combine all fund status
    frames_status = []
    frames_names = []
    for folder in output_dir.iterdir():
        if not folder.is_dir():
            continue
        for f4 in folder.glob("*_4_Fund_Status.csv"):
            frames_status.append(pd.read_csv(f4, dtype=str))
        for f5 in folder.glob("*_5_Name_History.csv"):
            frames_names.append(pd.read_csv(f5, dtype=str))

    if frames_status:
        df = pd.concat(frames_status, ignore_index=True)
        df.to_excel(output_dir / "etp_tracker_summary.xlsx", index=False, engine="openpyxl")
        print(f"  Excel: etp_tracker_summary.xlsx ({len(df)} funds)")

    if frames_names:
        df = pd.concat(frames_names, ignore_index=True)
        df.to_excel(output_dir / "etp_name_history.xlsx", index=False, engine="openpyxl")
        print(f"  Excel: etp_name_history.xlsx ({len(df)} entries)")


def main():
    start = time.time()
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== ETP Filing Tracker - Daily Run ({today}) ===")

    # Step 1: Run pipeline
    print("\n[1/3] Running pipeline...")
    n = run_pipeline(
        ciks=get_all_ciks(),
        overrides=get_overrides(),
        since=SINCE_DATE,
        refresh_submissions=True,
        user_agent=USER_AGENT,
    )
    print(f"  Processed {n} trusts")

    # Step 2: Export Excel
    print("\n[2/3] Exporting Excel...")
    export_excel(OUTPUT_DIR)

    # Step 3: Save digest + send email if configured
    print("\n[3/3] Building digest...")
    from etp_tracker.email_alerts import build_digest_html, send_digest_email
    html = build_digest_html(OUTPUT_DIR, DASHBOARD_URL)
    digest_path = OUTPUT_DIR / "daily_digest.html"
    digest_path.write_text(html, encoding="utf-8")
    print(f"  Saved: {digest_path}")

    sent = send_digest_email(OUTPUT_DIR, DASHBOARD_URL)
    if not sent:
        print("  Email skipped (SMTP not configured). Opening digest in browser...")
        import webbrowser
        webbrowser.open(str(digest_path.resolve()))

    elapsed = time.time() - start
    print(f"\n=== Done in {elapsed:.0f}s ({elapsed/60:.1f}m) ===")


if __name__ == "__main__":
    main()
