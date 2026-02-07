"""
Email Alerts - Daily Digest

Sends HTML email with:
- New filings detected
- Funds that went effective
- Name changes detected

Uses smtplib (built-in). Configure SMTP settings via environment variables.
"""
from __future__ import annotations
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
import pandas as pd


def _load_recipients(project_root: Path | None = None) -> list[str]:
    """
    Load recipients from email_recipients.txt (one email per line).
    Falls back to SMTP_TO env var if file not found.
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent
    recipients_file = project_root / "email_recipients.txt"
    if recipients_file.exists():
        lines = recipients_file.read_text().strip().splitlines()
        return [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    # Fallback to env var
    env_to = os.environ.get("SMTP_TO", "")
    return [e.strip() for e in env_to.split(",") if e.strip()]


def _get_smtp_config() -> dict:
    """Read SMTP config from .env file or environment variables."""
    # Try reading from .env file in project root
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    env_vars = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip().strip('"').strip("'")

    return {
        "host": env_vars.get("SMTP_HOST", os.environ.get("SMTP_HOST", "smtp.gmail.com")),
        "port": int(env_vars.get("SMTP_PORT", os.environ.get("SMTP_PORT", "587"))),
        "user": env_vars.get("SMTP_USER", os.environ.get("SMTP_USER", "")),
        "password": env_vars.get("SMTP_PASSWORD", os.environ.get("SMTP_PASSWORD", "")),
        "from_addr": env_vars.get("SMTP_FROM", os.environ.get("SMTP_FROM", "")),
        "to_addrs": _load_recipients(project_root),
    }


def build_digest_html(
    output_dir: Path,
    dashboard_url: str = "",
    since_date: str | None = None,
) -> str:
    """
    Build HTML email body summarizing today's changes.

    Args:
        output_dir: Path to outputs folder
        dashboard_url: URL to Streamlit dashboard
        since_date: Only show filings on or after this date (YYYY-MM-DD)
    """
    if not since_date:
        since_date = datetime.now().strftime("%Y-%m-%d")

    # Collect all fund status
    all_status = []
    all_names = []
    for folder in output_dir.iterdir():
        if not folder.is_dir():
            continue
        f4 = list(folder.glob("*_4_Fund_Status.csv"))
        if f4:
            all_status.append(pd.read_csv(f4[0], dtype=str))
        f5 = list(folder.glob("*_5_Name_History.csv"))
        if f5:
            all_names.append(pd.read_csv(f5[0], dtype=str))

    df_status = pd.concat(all_status, ignore_index=True) if all_status else pd.DataFrame()
    df_names = pd.concat(all_names, ignore_index=True) if all_names else pd.DataFrame()

    # --- New filings (filed today or since_date) ---
    new_filings = pd.DataFrame()
    if not df_status.empty and "Latest Filing Date" in df_status.columns:
        mask = df_status["Latest Filing Date"].fillna("") >= since_date
        new_filings = df_status[mask]

    # --- Funds that went effective ---
    newly_effective = pd.DataFrame()
    if not df_status.empty:
        eff_mask = (
            (df_status["Status"] == "EFFECTIVE")
            & (df_status["Effective Date"].fillna("") >= since_date)
        )
        newly_effective = df_status[eff_mask]

    # --- Name changes ---
    name_changes = pd.DataFrame()
    if not df_names.empty:
        multi = df_names.groupby("Series ID").size()
        changed_sids = multi[multi > 1].index
        name_changes = df_names[df_names["Series ID"].isin(changed_sids)]

    # Build HTML
    html_parts = []
    html_parts.append(f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
    <h1 style="color: #1a1a2e;">ETP Filing Tracker - Daily Digest</h1>
    <p style="color: #666;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    <hr>
    """)

    # New filings section
    html_parts.append(f"<h2>New Filings ({len(new_filings)})</h2>")
    if not new_filings.empty:
        html_parts.append('<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%;">')
        html_parts.append("<tr style='background:#f0f0f0'><th>Fund</th><th>Trust</th><th>Form</th><th>Status</th><th>Filing</th></tr>")
        for _, r in new_filings.head(50).iterrows():
            link = r.get("Prospectus Link", "")
            form = r.get("Latest Form", "")
            link_html = f'<a href="{link}">{form}</a>' if link else form
            html_parts.append(
                f"<tr><td>{r.get('Fund Name','')}</td>"
                f"<td>{r.get('Trust','')}</td>"
                f"<td>{link_html}</td>"
                f"<td>{r.get('Status','')}</td>"
                f"<td>{r.get('Latest Filing Date','')}</td></tr>"
            )
        html_parts.append("</table>")
    else:
        html_parts.append("<p>No new filings.</p>")

    # Newly effective section
    html_parts.append(f"<h2>Newly Effective ({len(newly_effective)})</h2>")
    if not newly_effective.empty:
        html_parts.append('<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%;">')
        html_parts.append("<tr style='background:#f0f0f0'><th>Fund</th><th>Ticker</th><th>Trust</th><th>Effective Date</th></tr>")
        for _, r in newly_effective.head(30).iterrows():
            html_parts.append(
                f"<tr><td>{r.get('Fund Name','')}</td>"
                f"<td>{r.get('Ticker','')}</td>"
                f"<td>{r.get('Trust','')}</td>"
                f"<td>{r.get('Effective Date','')}</td></tr>"
            )
        html_parts.append("</table>")
    else:
        html_parts.append("<p>No funds went effective.</p>")

    # Name changes section
    changed_count = name_changes["Series ID"].nunique() if not name_changes.empty else 0
    html_parts.append(f"<h2>Name Changes Tracked ({changed_count} funds)</h2>")
    if changed_count:
        html_parts.append('<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%;">')
        html_parts.append("<tr style='background:#f0f0f0'><th>Series ID</th><th>Old Name</th><th>New Name</th></tr>")
        for sid in name_changes["Series ID"].unique()[:20]:
            rows = name_changes[name_changes["Series ID"] == sid].sort_values("First Seen Date")
            if len(rows) >= 2:
                old_name = rows.iloc[0]["Name"]
                new_name = rows.iloc[-1]["Name"]
                html_parts.append(f"<tr><td>{sid}</td><td>{old_name}</td><td>{new_name}</td></tr>")
        html_parts.append("</table>")
    else:
        html_parts.append("<p>No name changes detected.</p>")

    # Footer
    if dashboard_url:
        html_parts.append(f'<hr><p><a href="{dashboard_url}">View Full Dashboard</a></p>')

    # Summary stats
    if not df_status.empty:
        total = len(df_status)
        eff = len(df_status[df_status["Status"] == "EFFECTIVE"])
        pend = len(df_status[df_status["Status"] == "PENDING"])
        delay = len(df_status[df_status["Status"] == "DELAYED"])
        html_parts.append(
            f"<hr><p style='color:#999; font-size:12px;'>"
            f"Total tracked: {total} funds | {eff} effective | {pend} pending | {delay} delayed</p>"
        )

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


def send_digest_email(
    output_dir: Path,
    dashboard_url: str = "",
    since_date: str | None = None,
) -> bool:
    """
    Build and send the daily digest email.

    Returns True if sent successfully.
    Requires SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TO env vars.
    """
    config = _get_smtp_config()
    if not config["user"] or not config["from_addr"] or not any(config["to_addrs"]):
        print("SMTP not configured. Set SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TO env vars.")
        return False

    html_body = build_digest_html(output_dir, dashboard_url, since_date)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"ETP Filing Tracker - Daily Digest ({datetime.now().strftime('%Y-%m-%d')})"
    msg["From"] = config["from_addr"]
    msg["To"] = ", ".join(config["to_addrs"])
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(config["host"], config["port"]) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["user"], config["password"])
            server.sendmail(config["from_addr"], config["to_addrs"], msg.as_string())
        print(f"Digest sent to {', '.join(config['to_addrs'])}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
