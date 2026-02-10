"""
Email Alerts - Daily Digest

Interactive HTML digest with:
- What changed today summary
- REX trusts highlighted section
- Collapsible trust sections with search/filter
- Smart columns: Days Since Filing, Expected Effective Date
- Status filter pills, form type tooltips
- Grouped downloads by trust
- Sticky nav, back-to-top

Uses smtplib (built-in). Configure SMTP settings via environment variables.
"""
from __future__ import annotations
import smtplib
import os
import html as html_mod
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

_REX_TRUSTS = {"REX ETF Trust", "ETF Opportunities Trust"}

_FORM_TOOLTIPS = {
    "485BPOS": "Post-effective amendment - fund is actively trading",
    "485BXT": "Extension filing - extends time for fund to go effective",
    "485APOS": "Initial filing - fund has 75 days to become effective",
    "497": "Supplement to existing prospectus",
    "497K": "Summary prospectus supplement",
}


def _load_recipients(project_root: Path | None = None) -> list[str]:
    if project_root is None:
        project_root = Path(__file__).parent.parent
    recipients_file = project_root / "email_recipients.txt"
    if recipients_file.exists():
        lines = recipients_file.read_text().strip().splitlines()
        return [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    env_to = os.environ.get("SMTP_TO", "")
    return [e.strip() for e in env_to.split(",") if e.strip()]


def _get_smtp_config() -> dict:
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


def _clean_ticker(val) -> str:
    s = str(val).strip() if val is not None else ""
    if s.upper() in ("NAN", "SYMBOL", "N/A", "NA", "NONE", "TBD", ""):
        return ""
    if len(s) < 2:
        return ""
    return s


def _days_since(date_str: str, today: datetime) -> str:
    try:
        dt = pd.to_datetime(date_str, errors="coerce")
        if pd.isna(dt):
            return ""
        delta = (today - dt).days
        return str(delta)
    except Exception:
        return ""


def _expected_effective(form: str, filing_date: str, eff_date: str) -> str:
    """Compute expected effective date based on form type."""
    if eff_date and str(eff_date).strip() and str(eff_date) != "nan":
        return str(eff_date).strip()
    form_upper = str(form).upper()
    if form_upper.startswith("485A"):
        try:
            dt = pd.to_datetime(filing_date, errors="coerce")
            if not pd.isna(dt):
                return (dt + timedelta(days=75)).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""


def _esc(val) -> str:
    """HTML-escape a value."""
    return html_mod.escape(str(val)) if val is not None else ""


def _trust_id(name: str) -> str:
    return name.lower().replace(" ", "-").replace("'", "")


def build_digest_html(
    output_dir: Path,
    dashboard_url: str = "",
    since_date: str | None = None,
) -> str:
    today = datetime.now()
    if not since_date:
        since_date = today.strftime("%Y-%m-%d")

    # --- Load data ---
    all_status = []
    all_names = []
    trust_csvs: dict[str, list[Path]] = {}  # trust -> list of csv paths
    excel_files: list[Path] = []

    for folder in sorted(output_dir.iterdir()):
        if not folder.is_dir():
            continue
        trust_name = folder.name
        trust_csvs[trust_name] = []
        f4 = list(folder.glob("*_4_Fund_Status.csv"))
        if f4:
            df = pd.read_csv(f4[0], dtype=str)
            all_status.append(df)
            trust_csvs[trust_name].append(f4[0])
        f5 = list(folder.glob("*_5_Name_History.csv"))
        if f5:
            all_names.append(pd.read_csv(f5[0], dtype=str))
            trust_csvs[trust_name].append(f5[0])

    for f in output_dir.glob("*.xlsx"):
        excel_files.append(f)

    df_all = pd.concat(all_status, ignore_index=True) if all_status else pd.DataFrame()
    df_names = pd.concat(all_names, ignore_index=True) if all_names else pd.DataFrame()

    if not df_all.empty and "Ticker" in df_all.columns:
        df_all["Ticker"] = df_all["Ticker"].apply(_clean_ticker)

    # --- Compute derived fields ---
    if not df_all.empty:
        df_all["Days Since Filing"] = df_all["Latest Filing Date"].apply(lambda x: _days_since(x, today))
        df_all["Expected Effective"] = df_all.apply(
            lambda r: _expected_effective(r.get("Latest Form", ""), r.get("Latest Filing Date", ""), r.get("Effective Date", "")),
            axis=1,
        )
        df_all["Is Today"] = df_all["Latest Filing Date"].fillna("") == since_date

    # --- Sections ---
    new_filings = pd.DataFrame()
    if not df_all.empty and "Latest Filing Date" in df_all.columns:
        date_mask = df_all["Latest Filing Date"].fillna("") >= since_date
        form_mask = df_all["Latest Form"].fillna("").str.upper().str.startswith("485")
        new_filings = df_all[date_mask & form_mask]

    newly_effective = pd.DataFrame()
    if not df_all.empty:
        eff_mask = (
            (df_all["Status"] == "EFFECTIVE")
            & (df_all["Effective Date"].fillna("") >= since_date)
        )
        newly_effective = df_all[eff_mask]

    name_changes = pd.DataFrame()
    if not df_names.empty:
        multi = df_names.groupby("Series ID").size()
        changed_sids = multi[multi > 1].index
        name_changes = df_names[df_names["Series ID"].isin(changed_sids)]

    total = len(df_all) if not df_all.empty else 0
    eff_count = len(df_all[df_all["Status"] == "EFFECTIVE"]) if not df_all.empty else 0
    pend_count = len(df_all[df_all["Status"] == "PENDING"]) if not df_all.empty else 0
    delay_count = len(df_all[df_all["Status"] == "DELAYED"]) if not df_all.empty else 0
    trusts = sorted(df_all["Trust"].unique()) if not df_all.empty else []
    changed_count = name_changes["Series ID"].nunique() if not name_changes.empty else 0

    # --- Build HTML ---
    h = []

    # HTML head with CSS + JS
    h.append(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETP Filing Tracker - {today.strftime('%Y-%m-%d')}</title>
<style>
:root {{ --navy: #1a1a2e; --green: #27ae60; --orange: #e67e22; --red: #e74c3c; --blue: #0984e3; --gray: #636e72; --light: #f8f9fa; --border: #dee2e6; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--navy); background: #fff; line-height: 1.5; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}

/* Sticky Nav */
.sticky-nav {{ position: sticky; top: 0; background: var(--navy); color: white; padding: 10px 20px; z-index: 100; display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }}
.sticky-nav a {{ color: white; text-decoration: none; font-size: 13px; opacity: 0.85; }}
.sticky-nav a:hover {{ opacity: 1; text-decoration: underline; }}
.sticky-nav select {{ padding: 4px 8px; border-radius: 4px; border: none; font-size: 13px; }}
.sticky-nav .brand {{ font-weight: bold; font-size: 15px; margin-right: 10px; opacity: 1; }}

/* Header */
.header {{ padding: 30px 0 15px; }}
.header h1 {{ font-size: 28px; color: var(--navy); }}
.header .date {{ color: var(--gray); font-size: 14px; margin-top: 4px; }}

/* KPIs */
.kpi-row {{ display: flex; gap: 12px; margin: 20px 0; flex-wrap: wrap; }}
.kpi {{ background: var(--light); border-radius: 8px; padding: 16px 20px; flex: 1; min-width: 100px; text-align: center; border: 1px solid var(--border); }}
.kpi .num {{ font-size: 32px; font-weight: 700; }}
.kpi .label {{ font-size: 11px; color: var(--gray); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}

/* What Changed */
.what-changed {{ background: #e3f2fd; border-left: 4px solid var(--blue); padding: 15px 20px; margin: 20px 0; border-radius: 0 8px 8px 0; }}
.what-changed h2 {{ font-size: 16px; margin-bottom: 8px; }}
.what-changed .stat {{ display: inline-block; margin-right: 20px; font-size: 14px; }}
.what-changed .stat b {{ font-size: 18px; }}

/* Section headers */
.section-header {{ display: flex; align-items: center; justify-content: space-between; margin: 25px 0 10px; padding-bottom: 8px; border-bottom: 2px solid var(--navy); }}
.section-header h2 {{ font-size: 20px; }}
.section-header .badge {{ background: var(--navy); color: white; padding: 2px 10px; border-radius: 12px; font-size: 13px; }}

/* REX highlight */
.rex-section {{ background: #fff8e1; border: 2px solid var(--orange); border-radius: 8px; padding: 20px; margin: 15px 0; }}
.rex-section h3 {{ color: var(--orange); margin-bottom: 5px; }}
.rex-section .sub {{ color: var(--gray); font-size: 13px; margin-bottom: 10px; }}

/* Trust accordion */
.trust-block {{ border: 1px solid var(--border); border-radius: 8px; margin: 10px 0; overflow: hidden; }}
.trust-header {{ background: var(--light); padding: 12px 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; user-select: none; }}
.trust-header:hover {{ background: #eee; }}
.trust-header h3 {{ font-size: 15px; margin: 0; }}
.trust-header .stats {{ font-size: 12px; color: var(--gray); }}
.trust-header .arrow {{ transition: transform 0.2s; font-size: 12px; }}
.trust-block.open .arrow {{ transform: rotate(90deg); }}
.trust-body {{ display: none; padding: 0; }}
.trust-block.open .trust-body {{ display: block; }}

/* Filters */
.filter-bar {{ display: flex; gap: 8px; padding: 10px 16px; background: #f5f5f5; align-items: center; flex-wrap: wrap; }}
.filter-bar input {{ padding: 6px 12px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px; width: 220px; }}
.pill {{ padding: 4px 12px; border-radius: 16px; font-size: 12px; cursor: pointer; border: 1px solid var(--border); background: white; }}
.pill.active {{ background: var(--navy); color: white; border-color: var(--navy); }}
.pill:hover {{ background: #ddd; }}
.pill.active:hover {{ background: #333; }}
.filter-bar .count {{ font-size: 12px; color: var(--gray); margin-left: auto; }}

/* Tables */
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: var(--navy); color: white; padding: 8px 10px; text-align: left; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.3px; position: sticky; top: 42px; z-index: 10; cursor: pointer; }}
th:hover {{ background: #2d2d52; }}
td {{ padding: 6px 10px; border-bottom: 1px solid #eee; }}
tr:hover {{ background: #f8f9ff; }}
tr.today-highlight {{ background: #e8f5e9; }}
tr.pending-group {{ border-top: 2px solid var(--orange); }}
.status-effective {{ color: var(--green); font-weight: 600; }}
.status-pending {{ color: var(--orange); font-weight: 600; }}
.status-delayed {{ color: var(--red); font-weight: 600; }}
.form-link {{ position: relative; }}
.form-link .tooltip {{ display: none; position: absolute; background: #333; color: white; padding: 6px 10px; border-radius: 4px; font-size: 11px; white-space: nowrap; bottom: 100%; left: 0; z-index: 20; }}
.form-link:hover .tooltip {{ display: block; }}
.days-col {{ text-align: center; font-size: 12px; color: var(--gray); }}
.ticker-col {{ font-family: monospace; font-weight: 600; }}

/* Downloads */
.downloads {{ margin: 20px 0; }}
.dl-group {{ border: 1px solid var(--border); border-radius: 8px; margin: 8px 0; }}
.dl-group-header {{ background: var(--light); padding: 10px 16px; font-weight: 600; font-size: 14px; cursor: pointer; display: flex; justify-content: space-between; }}
.dl-group-header:hover {{ background: #eee; }}
.dl-group-body {{ display: none; padding: 10px 16px; }}
.dl-group.open .dl-group-body {{ display: block; }}
.dl-btn {{ display: inline-block; padding: 6px 14px; margin: 3px 4px; border-radius: 4px; font-size: 12px; color: white; text-decoration: none; }}
.dl-btn.excel {{ background: var(--green); }}
.dl-btn.csv {{ background: var(--blue); }}
.dl-btn:hover {{ opacity: 0.85; }}

/* Back to top */
.back-top {{ position: fixed; bottom: 30px; right: 30px; background: var(--navy); color: white; width: 40px; height: 40px; border-radius: 50%; display: none; align-items: center; justify-content: center; cursor: pointer; font-size: 18px; z-index: 200; border: none; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }}
.back-top.visible {{ display: flex; }}

/* Footer */
.footer {{ color: var(--gray); font-size: 12px; margin-top: 40px; padding: 15px 0; border-top: 1px solid var(--border); }}
</style>
</head><body>
""")

    # Sticky nav
    trust_options = "".join(f'<option value="{_trust_id(t)}">{t}</option>' for t in trusts)
    h.append(f"""
<div class="sticky-nav">
  <span class="brand">ETP Tracker</span>
  <a href="#what-changed">Today</a>
  <a href="#rex-trusts">REX</a>
  <a href="#new-filings">New Filings</a>
  <a href="#newly-effective">Effective</a>
  <a href="#name-changes">Names</a>
  <a href="#downloads">Downloads</a>
  <select onchange="jumpToTrust(this.value)" style="margin-left:auto">
    <option value="">Jump to Trust...</option>
    {trust_options}
  </select>
</div>
""")

    h.append('<div class="container">')

    # Header
    h.append(f"""
<div class="header">
  <h1>ETP Filing Tracker</h1>
  <div class="date">{today.strftime('%A, %B %d, %Y at %I:%M %p')}</div>
</div>
""")

    # KPIs
    h.append(f"""
<div class="kpi-row">
  <div class="kpi"><div class="num">{len(trusts)}</div><div class="label">Trusts</div></div>
  <div class="kpi"><div class="num">{total}</div><div class="label">Total Funds</div></div>
  <div class="kpi"><div class="num" style="color:var(--green)">{eff_count}</div><div class="label">Effective</div></div>
  <div class="kpi"><div class="num" style="color:var(--orange)">{pend_count}</div><div class="label">Pending</div></div>
  <div class="kpi"><div class="num" style="color:var(--red)">{delay_count}</div><div class="label">Delayed</div></div>
</div>
""")

    # What Changed Today
    today_filed = len(df_all[df_all["Is Today"]]) if not df_all.empty else 0
    h.append(f"""
<div class="what-changed" id="what-changed">
  <h2>What Changed Today ({since_date})</h2>
  <div>
    <span class="stat"><b>{len(new_filings)}</b> new prospectus filings</span>
    <span class="stat"><b>{len(newly_effective)}</b> newly effective</span>
    <span class="stat"><b>{changed_count}</b> name changes</span>
    <span class="stat"><b>{today_filed}</b> funds filed today</span>
  </div>
</div>
""")

    # === REX TRUSTS ===
    h.append(f"""
<div class="section-header" id="rex-trusts">
  <h2>REX Trusts</h2>
</div>
""")
    for rex_trust in sorted(_REX_TRUSTS):
        if df_all.empty:
            continue
        rex_df = df_all[df_all["Trust"] == rex_trust]
        if rex_df.empty:
            continue
        rex_eff = len(rex_df[rex_df["Status"] == "EFFECTIVE"])
        rex_pend = len(rex_df[rex_df["Status"] == "PENDING"])
        rex_delay = len(rex_df[rex_df["Status"] == "DELAYED"])

        h.append(f'<div class="rex-section">')
        h.append(f'<h3>{_esc(rex_trust)}</h3>')
        h.append(f'<div class="sub">{len(rex_df)} funds: {rex_eff} effective, {rex_pend} pending, {rex_delay} delayed</div>')
        h.append(_build_trust_table(rex_df, today, f"rex-{_trust_id(rex_trust)}"))
        h.append('</div>')

    # === NEW PROSPECTUS FILINGS ===
    h.append(f"""
<div class="section-header" id="new-filings">
  <h2>New Prospectus Filings</h2>
  <span class="badge">{len(new_filings)}</span>
</div>
<p style="color:var(--gray); font-size:12px; margin-bottom:10px;">485APOS/485BPOS/485BXT only. 497 supplements excluded.</p>
""")
    if not new_filings.empty:
        h.append(_build_trust_table(new_filings, today, "new-filings-tbl"))
    else:
        h.append('<p style="padding:20px; color:var(--gray);">No new prospectus filings since last check.</p>')

    # === NEWLY EFFECTIVE ===
    h.append(f"""
<div class="section-header" id="newly-effective">
  <h2>Newly Effective</h2>
  <span class="badge">{len(newly_effective)}</span>
</div>
""")
    if not newly_effective.empty:
        h.append(_build_trust_table(newly_effective, today, "newly-effective-tbl"))
    else:
        h.append('<p style="padding:20px; color:var(--gray);">No funds went effective since last check.</p>')

    # === NAME CHANGES ===
    h.append(f"""
<div class="section-header" id="name-changes">
  <h2>Name Changes</h2>
  <span class="badge">{changed_count}</span>
</div>
""")
    if changed_count:
        h.append('<table><tr><th>Series ID</th><th>Old Name</th><th>New Name</th><th>Changed On</th></tr>')
        for sid in name_changes["Series ID"].unique()[:30]:
            rows = name_changes[name_changes["Series ID"] == sid].sort_values("First Seen Date")
            if len(rows) >= 2:
                old_name = _esc(rows.iloc[0]["Name"])
                new_name = _esc(rows.iloc[-1]["Name"])
                change_date = _esc(rows.iloc[-1]["First Seen Date"])
                h.append(f"<tr><td>{_esc(sid)}</td><td>{old_name}</td><td><b>{new_name}</b></td><td>{change_date}</td></tr>")
        h.append('</table>')
    else:
        h.append('<p style="padding:20px; color:var(--gray);">No name changes detected.</p>')

    # === ALL TRUSTS (collapsible) ===
    h.append(f"""
<div class="section-header" id="all-trusts">
  <h2>All Trusts</h2>
  <span class="badge">{len(trusts)} trusts</span>
</div>
<div style="margin-bottom:10px;">
  <input type="text" id="global-search" placeholder="Search all funds by name or ticker..." style="padding:8px 14px; border:1px solid var(--border); border-radius:6px; width:100%; max-width:400px; font-size:14px;" oninput="globalSearch(this.value)">
</div>
""")

    for trust_name in trusts:
        t_df = df_all[df_all["Trust"] == trust_name]
        t_eff = len(t_df[t_df["Status"] == "EFFECTIVE"])
        t_pend = len(t_df[t_df["Status"] == "PENDING"])
        t_delay = len(t_df[t_df["Status"] == "DELAYED"])
        is_rex = trust_name in _REX_TRUSTS
        tid = _trust_id(trust_name)
        rex_label = ' <span style="color:var(--orange); font-size:11px;">[REX]</span>' if is_rex else ""

        h.append(f"""
<div class="trust-block" id="trust-{tid}" data-trust="{_esc(trust_name)}">
  <div class="trust-header" onclick="toggleTrust(this)">
    <h3>{_esc(trust_name)}{rex_label}</h3>
    <div>
      <span class="stats">{len(t_df)} funds: {t_pend} pending | {t_eff} effective | {t_delay} delayed</span>
      <span class="arrow">&#9654;</span>
    </div>
  </div>
  <div class="trust-body">
""")
        h.append(_build_trust_table(t_df, today, f"tbl-{tid}", with_filter=True))
        h.append('</div></div>')

    # === DOWNLOADS ===
    h.append(f"""
<div class="section-header" id="downloads">
  <h2>Downloads</h2>
</div>
<div class="downloads">
""")
    # Excel summary group
    if excel_files:
        h.append('<div class="dl-group open">')
        h.append('<div class="dl-group-header" onclick="toggleDl(this)"><span>Summary Files (Excel)</span><span>&#9660;</span></div>')
        h.append('<div class="dl-group-body">')
        for ef in sorted(excel_files):
            h.append(f'<a class="dl-btn excel" href="file:///{ef.resolve().as_posix()}">{ef.name}</a>')
        h.append('</div></div>')

    # Per-trust CSV groups
    for trust_name in trusts:
        csvs = trust_csvs.get(trust_name, [])
        if not csvs:
            continue
        h.append(f'<div class="dl-group">')
        h.append(f'<div class="dl-group-header" onclick="toggleDl(this)"><span>{_esc(trust_name)}</span><span>&#9654;</span></div>')
        h.append('<div class="dl-group-body">')
        for csv_path in sorted(csvs):
            label = csv_path.name.replace(trust_name + "_", "").replace(".csv", "")
            h.append(f'<a class="dl-btn csv" href="file:///{csv_path.resolve().as_posix()}">{label}</a>')
        h.append('</div></div>')

    h.append('</div>')

    # Footer
    h.append(f"""
<div class="footer">
  <p>Generated by ETP Filing Tracker | {today.strftime('%Y-%m-%d %H:%M:%S')}</p>
  <p>Tracking {len(trusts)} trusts, {total} funds | {eff_count} effective | {pend_count} pending | {delay_count} delayed</p>
</div>
</div><!-- /container -->

<button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">&#8593;</button>

<script>
// Toggle trust accordion
function toggleTrust(el) {{
  el.parentElement.classList.toggle('open');
}}

// Toggle download group
function toggleDl(el) {{
  el.parentElement.classList.toggle('open');
}}

// Jump to trust from dropdown
function jumpToTrust(id) {{
  if (!id) return;
  var el = document.getElementById('trust-' + id);
  if (el) {{
    el.classList.add('open');
    el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
  }}
}}

// Filter table rows
function filterTable(tableId, query, statusFilter) {{
  var table = document.getElementById(tableId);
  if (!table) return;
  var rows = table.querySelectorAll('tbody tr');
  var q = (query || '').toLowerCase();
  var shown = 0;
  rows.forEach(function(row) {{
    var name = (row.getAttribute('data-name') || '').toLowerCase();
    var ticker = (row.getAttribute('data-ticker') || '').toLowerCase();
    var status = row.getAttribute('data-status') || '';
    var matchText = !q || name.indexOf(q) >= 0 || ticker.indexOf(q) >= 0;
    var matchStatus = !statusFilter || statusFilter === 'ALL' || status === statusFilter;
    if (matchText && matchStatus) {{
      row.style.display = '';
      shown++;
    }} else {{
      row.style.display = 'none';
    }}
  }});
  // Update count
  var countEl = table.parentElement.querySelector('.filter-count');
  if (countEl) countEl.textContent = shown + ' of ' + rows.length + ' funds';
}}

// Status pill click
function setStatusFilter(btn, tableId) {{
  var bar = btn.closest('.filter-bar');
  bar.querySelectorAll('.pill').forEach(function(p) {{ p.classList.remove('active'); }});
  btn.classList.add('active');
  var search = bar.querySelector('input');
  filterTable(tableId, search ? search.value : '', btn.getAttribute('data-status'));
}}

// Global search across all trust blocks
function globalSearch(query) {{
  var q = query.toLowerCase();
  document.querySelectorAll('.trust-block').forEach(function(block) {{
    var table = block.querySelector('table');
    if (!table) return;
    var rows = table.querySelectorAll('tbody tr');
    var anyMatch = false;
    rows.forEach(function(row) {{
      var name = (row.getAttribute('data-name') || '').toLowerCase();
      var ticker = (row.getAttribute('data-ticker') || '').toLowerCase();
      if (!q || name.indexOf(q) >= 0 || ticker.indexOf(q) >= 0) {{
        row.style.display = '';
        anyMatch = true;
      }} else {{
        row.style.display = 'none';
      }}
    }});
    if (q && anyMatch) {{
      block.classList.add('open');
    }}
  }});
}}

// Column sorting
function sortTable(tableId, colIdx) {{
  var table = document.getElementById(tableId);
  if (!table) return;
  var tbody = table.querySelector('tbody');
  var rows = Array.from(tbody.querySelectorAll('tr'));
  var asc = table.getAttribute('data-sort-dir') !== 'asc';
  table.setAttribute('data-sort-dir', asc ? 'asc' : 'desc');
  rows.sort(function(a, b) {{
    var aVal = a.cells[colIdx] ? a.cells[colIdx].textContent.trim() : '';
    var bVal = b.cells[colIdx] ? b.cells[colIdx].textContent.trim() : '';
    // Try numeric sort
    var aNum = parseFloat(aVal);
    var bNum = parseFloat(bVal);
    if (!isNaN(aNum) && !isNaN(bNum)) {{
      return asc ? aNum - bNum : bNum - aNum;
    }}
    return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  }});
  rows.forEach(function(row) {{ tbody.appendChild(row); }});
}}

// Back to top visibility
window.addEventListener('scroll', function() {{
  document.getElementById('backTop').classList.toggle('visible', window.scrollY > 300);
}});
</script>
</body></html>""")

    return "\n".join(h)


def _build_trust_table(df: pd.DataFrame, today: datetime, table_id: str, with_filter: bool = False) -> str:
    """Build an interactive table for a set of funds."""
    h = []

    if with_filter:
        h.append(f"""
<div class="filter-bar">
  <input type="text" placeholder="Filter by name or ticker..." oninput="filterTable('{table_id}', this.value, this.closest('.filter-bar').querySelector('.pill.active')?.getAttribute('data-status') || 'ALL')">
  <span class="pill active" data-status="ALL" onclick="setStatusFilter(this, '{table_id}')">All</span>
  <span class="pill" data-status="PENDING" onclick="setStatusFilter(this, '{table_id}')">Pending</span>
  <span class="pill" data-status="EFFECTIVE" onclick="setStatusFilter(this, '{table_id}')">Effective</span>
  <span class="pill" data-status="DELAYED" onclick="setStatusFilter(this, '{table_id}')">Delayed</span>
  <span class="count filter-count">{len(df)} of {len(df)} funds</span>
</div>
""")

    h.append(f'<table id="{table_id}">')
    h.append(f"""<thead><tr>
  <th onclick="sortTable('{table_id}',0)">Fund Name</th>
  <th onclick="sortTable('{table_id}',1)">Ticker</th>
  <th onclick="sortTable('{table_id}',2)">Status</th>
  <th onclick="sortTable('{table_id}',3)">Form</th>
  <th onclick="sortTable('{table_id}',4)">Filing Date</th>
  <th onclick="sortTable('{table_id}',5)">Days</th>
  <th onclick="sortTable('{table_id}',6)">Expected Effective</th>
</tr></thead><tbody>""")

    # Sort: pending first, then by filing date descending
    status_order = {"PENDING": 0, "DELAYED": 1, "EFFECTIVE": 2, "UNKNOWN": 3}
    sort_df = df.copy()
    sort_df["_status_sort"] = sort_df["Status"].map(status_order).fillna(3)
    sort_df["_fdt_sort"] = pd.to_datetime(sort_df["Latest Filing Date"], errors="coerce")
    sort_df = sort_df.sort_values(["_status_sort", "_fdt_sort"], ascending=[True, False])

    for _, r in sort_df.iterrows():
        name = _esc(r.get("Fund Name", ""))
        ticker = _clean_ticker(r.get("Ticker", ""))
        status = str(r.get("Status", ""))
        form = str(r.get("Latest Form", ""))
        filing_date = str(r.get("Latest Filing Date", ""))
        link = str(r.get("Prospectus Link", ""))
        days = str(r.get("Days Since Filing", ""))
        expected = str(r.get("Expected Effective", ""))
        is_today = r.get("Is Today", False)

        status_cls = f"status-{status.lower()}" if status in ("EFFECTIVE", "PENDING", "DELAYED") else ""
        row_cls = ' class="today-highlight"' if is_today else ""

        # Form with tooltip
        form_upper = form.upper()
        tooltip = _FORM_TOOLTIPS.get(form_upper, "")
        if not tooltip:
            for key in _FORM_TOOLTIPS:
                if form_upper.startswith(key[:4]):
                    tooltip = _FORM_TOOLTIPS[key]
                    break
        if link and link != "nan":
            form_html = f'<span class="form-link"><a href="{_esc(link)}">{_esc(form)}</a>'
            if tooltip:
                form_html += f'<span class="tooltip">{tooltip}</span>'
            form_html += '</span>'
        else:
            form_html = _esc(form)

        if expected and expected != "nan":
            # Highlight if expected effective is soon (within 14 days)
            try:
                exp_dt = pd.to_datetime(expected, errors="coerce")
                if not pd.isna(exp_dt):
                    days_until = (exp_dt - today).days
                    if days_until <= 0:
                        expected_html = f'<span style="color:var(--green); font-weight:600">{_esc(expected)}</span>'
                    elif days_until <= 14:
                        expected_html = f'<span style="color:var(--orange); font-weight:600">{_esc(expected)} ({days_until}d)</span>'
                    else:
                        expected_html = f'{_esc(expected)} ({days_until}d)'
                else:
                    expected_html = _esc(expected)
            except Exception:
                expected_html = _esc(expected)
        else:
            expected_html = ""

        h.append(
            f'<tr{row_cls} data-name="{name}" data-ticker="{_esc(ticker)}" data-status="{status}">'
            f'<td>{name}</td>'
            f'<td class="ticker-col">{_esc(ticker)}</td>'
            f'<td><span class="{status_cls}">{status}</span></td>'
            f'<td>{form_html}</td>'
            f'<td>{_esc(filing_date)}</td>'
            f'<td class="days-col">{_esc(days)}</td>'
            f'<td>{expected_html}</td>'
            f'</tr>'
        )

    h.append('</tbody></table>')
    return "\n".join(h)


def send_digest_email(
    output_dir: Path,
    dashboard_url: str = "",
    since_date: str | None = None,
) -> bool:
    """
    Build and send the daily digest email.
    Tries Azure Graph API first, falls back to SMTP.
    Returns True if sent successfully.
    """
    recipients = _load_recipients()
    if not recipients:
        print("No recipients configured. Add emails to email_recipients.txt.")
        return False

    html_body = build_digest_html(output_dir, dashboard_url, since_date)
    subject = f"ETP Filing Tracker - Daily Digest ({datetime.now().strftime('%Y-%m-%d')})"

    # --- Try Azure Graph API first ---
    try:
        from webapp.services.graph_email import is_configured, send_email
        if is_configured():
            print("  Sending via Azure Graph API...")
            if send_email(subject=subject, html_body=html_body, recipients=recipients):
                print(f"  Digest sent via Azure to {', '.join(recipients)}")
                return True
            else:
                print("  Azure Graph API failed. Trying SMTP fallback...")
    except ImportError:
        pass  # webapp not installed, skip Azure

    # --- Fall back to SMTP ---
    config = _get_smtp_config()
    if not config["user"] or not config["password"] or not config["from_addr"]:
        print("Neither Azure nor SMTP configured.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from_addr"]
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(config["host"], config["port"]) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["user"], config["password"])
            server.sendmail(config["from_addr"], recipients, msg.as_string())
        print(f"  Digest sent via SMTP to {', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"  Failed to send email: {e}")
        return False
