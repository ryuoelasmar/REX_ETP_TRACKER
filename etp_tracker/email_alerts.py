"""
Email Alerts - Daily Digest

Sends HTML email with:
- REX trusts highlighted section
- New prospectus filings (485-type only, NOT 497 supplements)
- Funds that went effective
- Name changes detected
- Trust-by-trust summary with navigation
- CSV download links

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

_REX_TRUSTS = {"REX ETF Trust", "ETF Opportunities Trust"}

_STYLE = """
<style>
  body { font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; color: #1a1a2e; }
  h1 { color: #1a1a2e; border-bottom: 3px solid #1a1a2e; padding-bottom: 10px; }
  h2 { color: #2d3436; margin-top: 30px; }
  h3 { color: #636e72; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0 20px 0; font-size: 13px; }
  th { background: #1a1a2e; color: white; padding: 8px 10px; text-align: left; }
  td { padding: 6px 10px; border-bottom: 1px solid #ddd; }
  tr:hover { background: #f5f5f5; }
  a { color: #0984e3; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .nav { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; }
  .nav a { margin-right: 15px; font-weight: bold; }
  .kpi-row { display: flex; gap: 15px; margin: 15px 0; }
  .kpi { background: #f8f9fa; border-radius: 8px; padding: 15px 20px; flex: 1; text-align: center; }
  .kpi .num { font-size: 28px; font-weight: bold; color: #1a1a2e; }
  .kpi .label { font-size: 12px; color: #636e72; margin-top: 4px; }
  .rex-highlight { background: #fff3e0; border-left: 4px solid #e67e22; padding: 10px 15px; margin: 10px 0; }
  .status-effective { color: #27ae60; font-weight: bold; }
  .status-pending { color: #e67e22; font-weight: bold; }
  .status-delayed { color: #e74c3c; font-weight: bold; }
  .download-section { background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 20px 0; }
  .download-section a { display: inline-block; margin: 5px 10px 5px 0; padding: 8px 16px; background: #27ae60; color: white; border-radius: 4px; font-weight: bold; }
  .download-section a:hover { background: #219a52; text-decoration: none; }
  .footer { color: #999; font-size: 12px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 10px; }
</style>
"""


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


def _status_span(status: str) -> str:
    """Wrap status in a colored span."""
    cls = f"status-{status.lower()}" if status in ("EFFECTIVE", "PENDING", "DELAYED") else ""
    return f'<span class="{cls}">{status}</span>'


def _clean_ticker_display(val) -> str:
    """Clean ticker for display - remove nan/SYMBOL/empty."""
    s = str(val).strip() if val is not None else ""
    if s.upper() in ("NAN", "SYMBOL", "N/A", "NA", "NONE", "TBD", ""):
        return ""
    return s


def _trust_anchor(name: str) -> str:
    """Create anchor ID from trust name."""
    return name.lower().replace(" ", "-").replace("'", "")


def build_digest_html(
    output_dir: Path,
    dashboard_url: str = "",
    since_date: str | None = None,
) -> str:
    """
    Build HTML digest summarizing today's changes.

    Sections:
    1. KPI summary
    2. Navigation bar
    3. REX Trusts (highlighted)
    4. New Prospectus Filings (485-type only)
    5. Newly Effective Funds
    6. Name Changes
    7. Trust-by-Trust Summary
    8. Download CSVs
    """
    if not since_date:
        since_date = datetime.now().strftime("%Y-%m-%d")

    # Collect all fund status and name history
    all_status = []
    all_names = []
    csv_files = []
    for folder in sorted(output_dir.iterdir()):
        if not folder.is_dir():
            continue
        f4 = list(folder.glob("*_4_Fund_Status.csv"))
        if f4:
            df = pd.read_csv(f4[0], dtype=str)
            all_status.append(df)
            csv_files.append(f4[0])
        f5 = list(folder.glob("*_5_Name_History.csv"))
        if f5:
            all_names.append(pd.read_csv(f5[0], dtype=str))
            csv_files.append(f5[0])

    df_status = pd.concat(all_status, ignore_index=True) if all_status else pd.DataFrame()
    df_names = pd.concat(all_names, ignore_index=True) if all_names else pd.DataFrame()

    # Clean tickers in display data
    if not df_status.empty and "Ticker" in df_status.columns:
        df_status["Ticker"] = df_status["Ticker"].apply(_clean_ticker_display)

    # --- Compute sections ---

    # New prospectus filings (485-type ONLY, NOT 497 supplements)
    new_filings = pd.DataFrame()
    if not df_status.empty and "Latest Filing Date" in df_status.columns:
        date_mask = df_status["Latest Filing Date"].fillna("") >= since_date
        form_mask = df_status["Latest Form"].fillna("").str.upper().str.startswith("485")
        new_filings = df_status[date_mask & form_mask]

    # Newly effective
    newly_effective = pd.DataFrame()
    if not df_status.empty:
        eff_mask = (
            (df_status["Status"] == "EFFECTIVE")
            & (df_status["Effective Date"].fillna("") >= since_date)
        )
        newly_effective = df_status[eff_mask]

    # Name changes (SGML-sourced only - Series IDs with >1 name entry)
    name_changes = pd.DataFrame()
    if not df_names.empty:
        multi = df_names.groupby("Series ID").size()
        changed_sids = multi[multi > 1].index
        name_changes = df_names[df_names["Series ID"].isin(changed_sids)]

    # KPI stats
    total = len(df_status) if not df_status.empty else 0
    eff_count = len(df_status[df_status["Status"] == "EFFECTIVE"]) if not df_status.empty else 0
    pend_count = len(df_status[df_status["Status"] == "PENDING"]) if not df_status.empty else 0
    delay_count = len(df_status[df_status["Status"] == "DELAYED"]) if not df_status.empty else 0
    trust_count = df_status["Trust"].nunique() if not df_status.empty else 0

    # --- Build HTML ---
    h = []

    # Header
    h.append(f"""<html><head>{_STYLE}</head><body>
    <h1>ETP Filing Tracker - Daily Digest</h1>
    <p style="color: #666;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    """)

    # KPIs
    h.append(f"""
    <div class="kpi-row">
      <div class="kpi"><div class="num">{trust_count}</div><div class="label">Trusts</div></div>
      <div class="kpi"><div class="num">{total}</div><div class="label">Total Funds</div></div>
      <div class="kpi"><div class="num" style="color:#27ae60">{eff_count}</div><div class="label">Effective</div></div>
      <div class="kpi"><div class="num" style="color:#e67e22">{pend_count}</div><div class="label">Pending</div></div>
      <div class="kpi"><div class="num" style="color:#e74c3c">{delay_count}</div><div class="label">Delayed</div></div>
    </div>
    """)

    # Navigation
    trusts = sorted(df_status["Trust"].unique()) if not df_status.empty else []
    nav_links = []
    nav_links.append('<a href="#rex-trusts">REX Trusts</a>')
    nav_links.append(f'<a href="#new-filings">New Filings ({len(new_filings)})</a>')
    nav_links.append(f'<a href="#newly-effective">Newly Effective ({len(newly_effective)})</a>')
    nav_links.append(f'<a href="#name-changes">Name Changes</a>')
    nav_links.append('<a href="#all-trusts">All Trusts</a>')
    nav_links.append('<a href="#downloads">Downloads</a>')
    h.append(f'<div class="nav">{" | ".join(nav_links)}</div>')

    # === REX TRUSTS SECTION ===
    h.append('<h2 id="rex-trusts">REX Trusts</h2>')
    for rex_trust in sorted(_REX_TRUSTS):
        if not df_status.empty:
            rex_df = df_status[df_status["Trust"] == rex_trust]
        else:
            rex_df = pd.DataFrame()

        if rex_df.empty:
            continue

        rex_eff = len(rex_df[rex_df["Status"] == "EFFECTIVE"])
        rex_pend = len(rex_df[rex_df["Status"] == "PENDING"])
        h.append(f'<div class="rex-highlight">')
        h.append(f'<h3>{rex_trust} ({len(rex_df)} funds: {rex_eff} effective, {rex_pend} pending)</h3>')
        h.append('<table><tr><th>Fund</th><th>Ticker</th><th>Status</th><th>Form</th><th>Filing Date</th></tr>')
        for _, r in rex_df.iterrows():
            link = str(r.get("Prospectus Link", ""))
            form = str(r.get("Latest Form", ""))
            form_html = f'<a href="{link}">{form}</a>' if link and link != "nan" else form
            ticker = _clean_ticker_display(r.get("Ticker", ""))
            h.append(
                f"<tr><td>{r.get('Fund Name','')}</td>"
                f"<td>{ticker}</td>"
                f"<td>{_status_span(str(r.get('Status','')))}</td>"
                f"<td>{form_html}</td>"
                f"<td>{r.get('Latest Filing Date','')}</td></tr>"
            )
        h.append('</table></div>')

    # === NEW PROSPECTUS FILINGS (485-type only) ===
    h.append(f'<h2 id="new-filings">New Prospectus Filings ({len(new_filings)})</h2>')
    h.append('<p style="color:#636e72; font-size:12px;">Only 485APOS/485BPOS/485BXT filings. 497 supplements are excluded.</p>')
    if not new_filings.empty:
        h.append('<table><tr><th>Fund</th><th>Trust</th><th>Form</th><th>Status</th><th>Filing Date</th></tr>')
        for _, r in new_filings.head(80).iterrows():
            link = str(r.get("Prospectus Link", ""))
            form = str(r.get("Latest Form", ""))
            form_html = f'<a href="{link}">{form}</a>' if link and link != "nan" else form
            h.append(
                f"<tr><td>{r.get('Fund Name','')}</td>"
                f"<td>{r.get('Trust','')}</td>"
                f"<td>{form_html}</td>"
                f"<td>{_status_span(str(r.get('Status','')))}</td>"
                f"<td>{r.get('Latest Filing Date','')}</td></tr>"
            )
        h.append('</table>')
    else:
        h.append('<p>No new prospectus filings since last check.</p>')

    # === NEWLY EFFECTIVE ===
    h.append(f'<h2 id="newly-effective">Newly Effective ({len(newly_effective)})</h2>')
    if not newly_effective.empty:
        h.append('<table><tr><th>Fund</th><th>Ticker</th><th>Trust</th><th>Effective Date</th><th>Reason</th></tr>')
        for _, r in newly_effective.head(50).iterrows():
            ticker = _clean_ticker_display(r.get("Ticker", ""))
            h.append(
                f"<tr><td>{r.get('Fund Name','')}</td>"
                f"<td>{ticker}</td>"
                f"<td>{r.get('Trust','')}</td>"
                f"<td>{r.get('Effective Date','')}</td>"
                f"<td>{r.get('Status Reason','')}</td></tr>"
            )
        h.append('</table>')
    else:
        h.append('<p>No funds went effective since last check.</p>')

    # === NAME CHANGES ===
    changed_count = name_changes["Series ID"].nunique() if not name_changes.empty else 0
    h.append(f'<h2 id="name-changes">Name Changes ({changed_count} funds)</h2>')
    if changed_count:
        h.append('<table><tr><th>Series ID</th><th>Old Name</th><th>New Name</th><th>Changed On</th></tr>')
        for sid in name_changes["Series ID"].unique()[:30]:
            rows = name_changes[name_changes["Series ID"] == sid].sort_values("First Seen Date")
            if len(rows) >= 2:
                old_name = rows.iloc[0]["Name"]
                new_name = rows.iloc[-1]["Name"]
                change_date = rows.iloc[-1]["First Seen Date"]
                h.append(f"<tr><td>{sid}</td><td>{old_name}</td><td>{new_name}</td><td>{change_date}</td></tr>")
        h.append('</table>')
    else:
        h.append('<p>No name changes detected.</p>')

    # === ALL TRUSTS SUMMARY ===
    h.append('<h2 id="all-trusts">All Trusts</h2>')
    h.append('<table><tr><th>Trust</th><th>Funds</th><th>Effective</th><th>Pending</th><th>Delayed</th></tr>')
    for trust_name in trusts:
        t_df = df_status[df_status["Trust"] == trust_name]
        t_eff = len(t_df[t_df["Status"] == "EFFECTIVE"])
        t_pend = len(t_df[t_df["Status"] == "PENDING"])
        t_delay = len(t_df[t_df["Status"] == "DELAYED"])
        anchor = _trust_anchor(trust_name)
        h.append(
            f'<tr><td><a href="#{anchor}">{trust_name}</a></td>'
            f'<td>{len(t_df)}</td><td>{t_eff}</td><td>{t_pend}</td><td>{t_delay}</td></tr>'
        )
    h.append('</table>')

    # Trust detail sections
    for trust_name in trusts:
        anchor = _trust_anchor(trust_name)
        t_df = df_status[df_status["Trust"] == trust_name]
        is_rex = trust_name in _REX_TRUSTS
        h.append(f'<h3 id="{anchor}">{trust_name} ({len(t_df)} funds)</h3>')
        if is_rex:
            h.append('<p><em>REX-related trust</em></p>')
        h.append('<table><tr><th>Fund</th><th>Ticker</th><th>Status</th><th>Form</th><th>Filing Date</th></tr>')
        for _, r in t_df.iterrows():
            link = str(r.get("Prospectus Link", ""))
            form = str(r.get("Latest Form", ""))
            form_html = f'<a href="{link}">{form}</a>' if link and link != "nan" else form
            ticker = _clean_ticker_display(r.get("Ticker", ""))
            h.append(
                f"<tr><td>{r.get('Fund Name','')}</td>"
                f"<td>{ticker}</td>"
                f"<td>{_status_span(str(r.get('Status','')))}</td>"
                f"<td>{form_html}</td>"
                f"<td>{r.get('Latest Filing Date','')}</td></tr>"
            )
        h.append('</table>')

    # === DOWNLOAD CSVs ===
    h.append('<h2 id="downloads">Download CSVs</h2>')
    h.append('<div class="download-section">')

    # Excel summary files
    excel_summary = output_dir / "etp_tracker_summary.xlsx"
    excel_names = output_dir / "etp_name_history.xlsx"
    if excel_summary.exists():
        h.append(f'<a href="file:///{excel_summary.resolve().as_posix()}">Fund Status Summary (Excel)</a>')
    if excel_names.exists():
        h.append(f'<a href="file:///{excel_names.resolve().as_posix()}">Name History (Excel)</a>')

    # Per-trust CSVs
    h.append('<br><br><strong>Per-trust CSVs:</strong><br>')
    for csv_path in sorted(csv_files):
        name = csv_path.name
        h.append(f'<a href="file:///{csv_path.resolve().as_posix()}" style="background:#0984e3; font-size:12px; padding:5px 10px;">{name}</a> ')

    h.append('</div>')

    # Footer
    if dashboard_url:
        h.append(f'<p><a href="{dashboard_url}">View Full Dashboard</a></p>')

    h.append(f"""
    <div class="footer">
      <p>Generated by ETP Filing Tracker | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
      <p>Tracking {trust_count} trusts, {total} funds | {eff_count} effective | {pend_count} pending | {delay_count} delayed</p>
    </div>
    </body></html>""")

    return "\n".join(h)


def send_digest_email(
    output_dir: Path,
    dashboard_url: str = "",
    since_date: str | None = None,
) -> bool:
    """
    Build and send the daily digest email.

    Returns True if sent successfully.
    Requires SMTP_USER, SMTP_PASSWORD, SMTP_FROM, and recipients configured.
    """
    config = _get_smtp_config()
    if not config["user"] or not config["password"] or not config["from_addr"] or not any(config["to_addrs"]):
        print("SMTP not configured. Set SMTP_USER, SMTP_PASSWORD, SMTP_FROM in .env and add recipients to email_recipients.txt.")
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
