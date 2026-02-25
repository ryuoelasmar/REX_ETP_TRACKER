"""
REX ETF Weekly Report - Executive Email Digest v3

Email-client-compatible HTML digest (inline styles, table layout, no JS).
Combines Bloomberg market data (ETF-only) and SEC filing activity into a
comprehensive executive-ready weekly email for REX Financial team members.

Sections:
  PART 1 - Overview
    1. Header
    2. Filing Activity (top-of-email)

  PART 2 - REX Products
    3. REX Scorecard (4 KPI cards with growth sub-labels)
    4. AUM by Suite (stacked bar, Outlook-safe)
    5. 1M Flows by Suite (horizontal bar chart)
    6. Winners, Losers & Yielders (combined section)

  PART 3 - Category Landscape
    7. Section header
    8. Per-category cards (5 categories, 4 KPIs + top 5 issuers each)

  PART 4 - Close
    9. Dashboard CTA
    10. Footer
"""
from __future__ import annotations

import logging
import math
import smtplib
from datetime import datetime, timedelta, date as date_type
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pandas as pd

from etp_tracker.email_alerts import (
    _NAVY, _GREEN, _ORANGE, _RED, _BLUE, _GRAY, _LIGHT, _BORDER, _WHITE,
    _esc, _load_recipients, _get_smtp_config,
)

log = logging.getLogger(__name__)

# Suites to exclude from the digest
_EXCLUDED_SUITES = {"MicroSector", "L&I Other"}

# Suite colors (v3 palette)
_SUITE_COLORS = {
    "T-REX": "#e74c3c",
    "Growth & Income": "#f39c12",
    "Premium Income": "#0984e3",
    "Crypto": "#8e44ad",
    "Thematic": "#27ae60",
    "Defined Outcome": "#00b894",
}

# Income categories for yield filtering
_INCOME_CATEGORIES = {"Income - Single Stock", "Income - Index/Basket/ETF Based"}

# Category landscape: (internal_name, display_name, border_color)
_LANDSCAPE_CATS = [
    ("Leverage & Inverse - Single Stock", "Leveraged Single Stock", "#e74c3c"),
    ("Income - Single Stock", "Covered Call (Single Stock)", "#f39c12"),
    ("Income - Index/Basket/ETF Based", "Covered Call (Index/ETF)", "#0984e3"),
    ("Crypto", "Crypto", "#8e44ad"),
    ("Thematic", "Thematic", "#27ae60"),
]

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
_SECTION_TITLE = (
    f"font-size:16px;font-weight:700;color:{_NAVY};margin:0 0 12px 0;"
    f"padding-bottom:8px;border-bottom:2px solid {_BLUE};"
)
_KPI_BOX = f"padding:12px 8px;background:{_LIGHT};border-radius:8px;text-align:center;"
_KPI_VALUE = f"font-size:24px;font-weight:700;color:{_NAVY};"
_KPI_LABEL = f"font-size:10px;color:{_GRAY};text-transform:uppercase;letter-spacing:0.5px;"
_TABLE_HEADER = (
    f"padding:8px 12px;background:{_NAVY};color:{_WHITE};"
    f"font-size:12px;font-weight:600;text-align:left;"
)
_TABLE_HEADER_RIGHT = (
    f"padding:8px 12px;background:{_NAVY};color:{_WHITE};"
    f"font-size:12px;font-weight:600;text-align:right;"
)
_TABLE_CELL = f"padding:6px 12px;border-bottom:1px solid {_BORDER};font-size:12px;"
_TABLE_CELL_RIGHT = (
    f"padding:6px 12px;border-bottom:1px solid {_BORDER};"
    f"font-size:12px;text-align:right;"
)

_DEFAULT_DASHBOARD_URL = "https://rex-etp-tracker.onrender.com"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _fmt_change(val) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return f'<span style="color:{_GRAY};">--</span>'
    color = _GREEN if val >= 0 else _RED
    sign = "+" if val >= 0 else ""
    return f'<span style="color:{color};font-weight:600;">{sign}{val:.1f}%</span>'


def _fmt_return(val) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return f'<span style="color:{_GRAY};">--</span>'
    color = _GREEN if val >= 0 else _RED
    sign = "+" if val >= 0 else ""
    return f'<span style="color:{color};font-weight:600;">{sign}{val:.2f}%</span>'


def _fmt_currency_safe(val) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "$0"
    if abs(val) >= 1_000:
        return f"${val / 1_000:,.1f}B"
    if abs(val) >= 1:
        return f"${val:,.1f}M"
    return f"${val:.2f}M"


def _fmt_flow_safe(val) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "$0"
    sign = "+" if val >= 0 else ""
    return f"{sign}{_fmt_currency_safe(val)}"


def _flow_color(val) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return _GRAY
    return _GREEN if val >= 0 else _RED


def _filter_suites(suites: list[dict]) -> list[dict]:
    return [s for s in suites if s.get("rex_name", s.get("name", "")) not in _EXCLUDED_SUITES]


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------
def _gather_market_data() -> dict | None:
    """Gather Bloomberg data: ETF-only summary + raw DataFrame for category breakdowns."""
    try:
        from webapp.services.market_data import (
            data_available, get_rex_summary, get_data_as_of,
            get_category_summary, get_master_data,
        )
        if not data_available():
            return None

        summary = get_rex_summary(fund_structure="ETF")
        master = get_master_data()

        # Filter master to ETF-only for rex_df
        fund_type_col = next((c for c in master.columns if c.lower().strip() == "fund_type"), None)
        if fund_type_col:
            etf_master = master[master[fund_type_col] == "ETF"].copy()
        else:
            etf_master = master.copy()

        rex_df = etf_master[etf_master["is_rex"] == True].copy()
        if "ticker_clean" in rex_df.columns:
            rex_df = rex_df.drop_duplicates(subset=["ticker_clean"], keep="first")

        # Gather category landscape data for the 5 categories
        landscape = {}
        for cat_name, display_name, color in _LANDSCAPE_CATS:
            try:
                cat_data = get_category_summary(cat_name)
                landscape[cat_name] = cat_data
            except Exception as exc:
                log.warning("Category summary failed for %s: %s", cat_name, exc)

        return {
            "kpis": summary.get("kpis", {}),
            "suites": summary.get("suites", []),
            "flow_chart": summary.get("flow_chart", {}),
            "perf_metrics": summary.get("perf_metrics", {}),
            "data_as_of": get_data_as_of(),
            "rex_df": rex_df,
            "master": master,
            "landscape": landscape,
        }
    except Exception as exc:
        log.warning("Weekly digest: Bloomberg data unavailable: %s", exc)
        return None


def _gather_filing_data(db_session, days: int = 7) -> dict:
    from sqlalchemy import func, select
    from webapp.models import Trust, Filing, FundStatus

    cutoff = date_type.today() - timedelta(days=days)

    # Fund filings: 485* forms only (prospectus-related)
    fund_filings = db_session.execute(
        select(func.count(Filing.id))
        .where(Filing.filing_date >= cutoff)
        .where(Filing.form.ilike("485%"))
    ).scalar() or 0

    newly_effective = db_session.execute(
        select(func.count(FundStatus.id))
        .where(FundStatus.status == "EFFECTIVE")
        .where(FundStatus.effective_date >= cutoff)
    ).scalar() or 0

    # Pending funds: total count of PENDING status
    pending_funds = db_session.execute(
        select(func.count(FundStatus.id))
        .where(FundStatus.status == "PENDING")
    ).scalar() or 0

    trust_count = db_session.execute(
        select(func.count(Trust.id)).where(Trust.is_active == True)
    ).scalar() or 0

    return {
        "fund_filings": fund_filings,
        "newly_effective": newly_effective,
        "pending_funds": pending_funds,
        "trust_count": trust_count,
        "cutoff": cutoff.isoformat(),
    }


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------
def _render_header(week_ending: str, data_as_of: str) -> str:
    subtitle_parts = [f"Week ending {_esc(week_ending)}"]
    if data_as_of:
        subtitle_parts.append(f"Data as of {_esc(data_as_of)}")
    subtitle = " | ".join(subtitle_parts)
    return f"""
<tr><td style="background:{_NAVY};padding:28px 30px;">
  <div style="color:{_WHITE};font-size:24px;font-weight:700;margin-bottom:4px;">
    REX ETF Weekly Report
  </div>
  <div style="color:rgba(255,255,255,0.7);font-size:13px;">{subtitle}</div>
</td></tr>"""


def _render_filing_activity(filing_data: dict) -> str:
    filings = filing_data.get("fund_filings", 0)
    effective = filing_data.get("newly_effective", 0)
    pending = filing_data.get("pending_funds", 0)
    trust_count = filing_data.get("trust_count", 0)

    return f"""
<tr><td style="padding:20px 30px 10px;">
  <div style="{_SECTION_TITLE}">Filing Activity (Last 7 Days)</div>
  <div style="font-size:12px;color:{_GRAY};margin-bottom:10px;">
    Scanning {trust_count} trusts across the ETP landscape
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#e3f2fd;border-left:4px solid {_BLUE};border-radius:0 8px 8px 0;">
    <tr><td style="padding:15px 20px;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="padding-right:28px;font-size:14px;">
          <span style="font-size:22px;font-weight:700;color:{_BLUE};">{filings}</span> fund filings
        </td>
        <td style="padding-right:28px;font-size:14px;">
          <span style="font-size:22px;font-weight:700;color:{_GREEN};">{effective}</span> newly effective
        </td>
        <td style="font-size:14px;">
          <span style="font-size:22px;font-weight:700;color:{_ORANGE};">{pending}</span> pending funds
        </td>
      </tr></table>
    </td></tr>
  </table>
</td></tr>"""


def _render_scorecard(kpis: dict, rex_df: pd.DataFrame = None) -> str:
    total_aum = kpis.get("total_aum_fmt", "$0")
    flow_1w = kpis.get("flow_1w_fmt", "$0")
    flow_1w_val = kpis.get("flow_1w", 0)
    flow_1m = kpis.get("flow_1m_fmt", "$0")
    flow_1m_val = kpis.get("flow_1m", 0)
    num_products = kpis.get("num_products", kpis.get("count", 0))

    # AUM MoM sub-label
    aum_mom = kpis.get("aum_mom_pct", 0)
    aum_sub = ""
    if aum_mom and not (isinstance(aum_mom, float) and math.isnan(aum_mom)):
        mom_color = _GREEN if aum_mom >= 0 else _RED
        mom_sign = "+" if aum_mom >= 0 else ""
        aum_sub = (
            f'<div style="font-size:11px;color:{mom_color};font-weight:600;margin-top:2px;">'
            f'{mom_sign}{aum_mom:.1f}% MoM</div>'
        )

    # New products sub-label (inception_date in last 30 days)
    products_sub = ""
    if rex_df is not None and not rex_df.empty and "inception_date" in rex_df.columns:
        cutoff_30d = pd.Timestamp.now() - pd.Timedelta(days=30)
        inception = pd.to_datetime(rex_df["inception_date"], errors="coerce")
        new_count = int((inception >= cutoff_30d).sum())
        if new_count > 0:
            products_sub = (
                f'<div style="font-size:11px;color:{_GREEN};font-weight:600;margin-top:2px;">'
                f'+{new_count} new</div>'
            )

    def _card(value: str, label: str, color: str = _NAVY, sub_label: str = "") -> str:
        return (
            f'<td width="23%" align="center" style="{_KPI_BOX}">'
            f'<div style="font-size:24px;font-weight:700;color:{color};">{value}</div>'
            f'{sub_label}'
            f'<div style="{_KPI_LABEL}">{_esc(label)}</div>'
            f'</td>'
        )

    return f"""
<tr><td style="padding:20px 30px 10px;">
  <div style="{_SECTION_TITLE}">REX Scorecard</div>
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      {_card(total_aum, "Total AUM", sub_label=aum_sub)}
      <td width="2%"></td>
      {_card(flow_1w, "1W Net Flows", _flow_color(flow_1w_val))}
      <td width="2%"></td>
      {_card(flow_1m, "1M Net Flows", _flow_color(flow_1m_val))}
      <td width="2%"></td>
      {_card(str(num_products), "Products", sub_label=products_sub)}
    </tr>
  </table>
</td></tr>"""


def _render_scorecard_unavailable() -> str:
    return f"""
<tr><td style="padding:20px 30px 10px;">
  <div style="{_SECTION_TITLE}">REX Scorecard</div>
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr><td style="{_KPI_BOX}padding:24px;">
      <div style="font-size:14px;color:{_GRAY};text-align:center;">
        Market data not available. Bloomberg data file has not been loaded.
      </div>
    </td></tr>
  </table>
</td></tr>"""


def _render_aum_stacked_bar(suites: list[dict]) -> str:
    """AUM by Suite as a single stacked horizontal bar + legend (Outlook-safe)."""
    filtered = _filter_suites(suites)
    if not filtered:
        return ""
    sorted_suites = sorted(filtered, key=lambda s: s.get("kpis", {}).get("total_aum", 0), reverse=True)
    total = sum(s.get("kpis", {}).get("total_aum", 0) for s in sorted_suites)
    if total <= 0:
        return ""

    # Build stacked bar segments
    bar_cells = []
    legend_rows = []
    for s in sorted_suites:
        name = s.get("rex_name", s.get("name", ""))
        aum = s.get("kpis", {}).get("total_aum", 0)
        pct = (aum / total * 100) if total > 0 else 0
        color = _SUITE_COLORS.get(name, _BLUE)

        if pct < 0.5:
            continue  # skip tiny slices in the bar

        bar_cells.append(
            f'<td width="{pct:.1f}%" style="background:{color};"></td>'
        )

        legend_rows.append(
            f'<tr>'
            f'<td style="padding:4px 6px;width:14px;">'
            f'<div style="width:12px;height:12px;background:{color};border-radius:2px;"></div>'
            f'</td>'
            f'<td style="padding:4px 6px;font-size:12px;font-weight:600;">{_esc(name)}</td>'
            f'<td style="padding:4px 6px;font-size:12px;text-align:right;">{_fmt_currency_safe(aum)}</td>'
            f'<td style="padding:4px 6px;font-size:11px;text-align:right;color:{_GRAY};">{pct:.1f}%</td>'
            f'</tr>'
        )

    if not bar_cells:
        return ""

    return f"""
<tr><td style="padding:15px 30px;">
  <div style="{_SECTION_TITLE}">AUM by Suite</div>
  <div style="font-size:12px;color:{_GRAY};margin-bottom:10px;">
    Total: {_fmt_currency_safe(total)}
  </div>
  <table width="100%" cellpadding="0" cellspacing="0"
         style="border-radius:6px;overflow:hidden;">
    <tr style="height:24px;">
      {''.join(bar_cells)}
    </tr>
  </table>
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="margin-top:10px;">
    {''.join(legend_rows)}
  </table>
</td></tr>"""


def _render_bar_chart(title: str, items: list[tuple[str, float]], subtitle: str = "") -> str:
    """Render a horizontal bar chart. items = [(label, value), ...]"""
    if not items:
        return ""

    max_abs = max(abs(v) for _, v in items) if items else 1
    if max_abs == 0:
        max_abs = 1

    sub_html = f'<div style="font-size:12px;color:{_GRAY};margin-bottom:8px;">{_esc(subtitle)}</div>' if subtitle else ""
    rows = []
    for label, val in items:
        color = _SUITE_COLORS.get(label, _BLUE)
        bar_width = max(abs(val) / max_abs * 100, 2)
        val_fmt = _fmt_flow_safe(val)
        val_color = _flow_color(val)

        rows.append(
            f'<tr>'
            f'<td style="padding:4px 8px;font-size:12px;font-weight:600;width:120px;'
            f'white-space:nowrap;">{_esc(label)}</td>'
            f'<td style="padding:4px 8px;">'
            f'<div style="background:{_LIGHT};border-radius:4px;overflow:hidden;">'
            f'<div style="background:{color};height:18px;width:{bar_width:.1f}%;'
            f'border-radius:4px;min-width:4px;"></div>'
            f'</div></td>'
            f'<td style="padding:4px 8px;font-size:12px;text-align:right;width:80px;'
            f'font-weight:600;color:{val_color};">{val_fmt}</td>'
            f'</tr>'
        )

    return f"""
<tr><td style="padding:15px 30px;">
  <div style="{_SECTION_TITLE}">{_esc(title)}</div>
  {sub_html}
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    {''.join(rows)}
  </table>
</td></tr>"""


def _render_flow_chart(suites: list[dict], flow_chart: dict) -> str:
    """1M Flows by suite as a horizontal bar chart."""
    suite_names = flow_chart.get("suites", [])
    flow_1m = flow_chart.get("flow_1m", [])
    if not suite_names or not flow_1m:
        return ""

    items = []
    for name, val in zip(suite_names, flow_1m):
        if name in _EXCLUDED_SUITES:
            continue
        items.append((name, val))

    # Sort by absolute flow descending
    items.sort(key=lambda x: abs(x[1]), reverse=True)
    total_flow = sum(v for _, v in items)

    return _render_bar_chart("1M Net Flows by Suite", items,
                             subtitle=f"Total: {_fmt_flow_safe(total_flow)}")


def _render_winners_losers_yielders(perf_metrics: dict, rex_df: pd.DataFrame) -> str:
    """Winners, Losers & Yielders combined in one section."""
    ret_data = perf_metrics.get("return_1w", {})
    winners = ret_data.get("best5", []) if ret_data else []
    losers = ret_data.get("worst5", []) if ret_data else []

    yield_data = perf_metrics.get("yield", {})
    all_yielders = yield_data.get("best5", []) if yield_data else []

    # Filter yielders to income-suite tickers
    if all_yielders and not rex_df.empty and "category_display" in rex_df.columns:
        income_tickers = set(
            rex_df[rex_df["category_display"].isin(_INCOME_CATEGORIES)]["ticker_clean"]
        ) if "ticker_clean" in rex_df.columns else set()
        yielders = [y for y in all_yielders if y.get("ticker", "") in income_tickers]
    else:
        yielders = all_yielders

    if not winners and not losers and not yielders:
        return ""

    def _table(title: str, items: list, title_color: str) -> str:
        header = (
            f'<div style="font-size:13px;font-weight:700;color:{title_color};'
            f'margin-bottom:6px;">{_esc(title)}</div>'
        )
        rows = []
        for item in items[:5]:
            ticker = _esc(item.get("ticker", ""))
            name = _esc(item.get("fund_name", ""))
            if len(name) > 28:
                name = name[:25] + "..."
            value = _esc(item.get("value_fmt", ""))
            rows.append(
                f'<tr>'
                f'<td style="padding:3px 6px;font-size:11px;font-weight:600;'
                f'border-bottom:1px solid {_BORDER};white-space:nowrap;">{ticker}</td>'
                f'<td style="padding:3px 6px;font-size:10px;color:{_GRAY};'
                f'border-bottom:1px solid {_BORDER};">{name}</td>'
                f'<td style="padding:3px 6px;font-size:11px;text-align:right;font-weight:600;'
                f'border-bottom:1px solid {_BORDER};color:{title_color};">{value}</td>'
                f'</tr>'
            )
        return (
            f'{header}'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
            f' style="border-collapse:collapse;">'
            f'{"".join(rows)}'
            f'</table>'
        )

    # Winners & Losers side by side
    wl_html = ""
    if winners or losers:
        left = _table("Winners (1W Return)", winners, _GREEN)
        right = _table("Losers (1W Return)", losers, _RED)
        wl_html = f"""
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td width="48%" valign="top">{left}</td>
      <td width="4%"></td>
      <td width="48%" valign="top">{right}</td>
    </tr>
  </table>"""

    # Yielders full-width below
    yielders_html = ""
    if yielders:
        yielders_html = (
            f'<div style="margin-top:12px;">'
            f'{_table("Top Yielders (Income Suites)", yielders, _GREEN)}'
            f'</div>'
        )

    return f"""
<tr><td style="padding:15px 30px;">
  <div style="{_SECTION_TITLE}">Winners, Losers & Yielders</div>
  {wl_html}
  {yielders_html}
</td></tr>"""


def _render_landscape_header() -> str:
    """Part 3 section divider."""
    return f"""
<tr><td style="padding:20px 30px 5px;">
  <div style="font-size:18px;font-weight:700;color:{_NAVY};margin:0;
    padding-bottom:8px;border-bottom:3px solid {_NAVY};">
    Market Landscape
  </div>
  <div style="font-size:12px;color:{_GRAY};margin-top:6px;">
    Full competitive picture across REX-relevant ETP categories
  </div>
</td></tr>"""


def _render_category_card(
    cat_name: str,
    display_name: str,
    border_color: str,
    cat_data: dict,
    master: pd.DataFrame = None,
) -> str:
    """Render a single category landscape card with 4 KPIs (with growth) and top 5 issuers."""
    cat_kpis = cat_data.get("cat_kpis", {})
    rex_share = cat_data.get("rex_share", 0)

    cat_aum = cat_kpis.get("total_aum", 0)
    flow_1m = cat_kpis.get("flow_1m", 0)
    num_products = cat_kpis.get("num_products", cat_kpis.get("count", 0))

    # Growth computations from master DataFrame
    aum_growth_sub = ""
    share_change_sub = ""
    products_new_sub = ""

    if master is not None and not master.empty and "category_display" in master.columns:
        cat_df = master[master["category_display"] == cat_name].copy()

        if not cat_df.empty:
            # AUM MoM growth
            if "t_w4.aum" in cat_df.columns and "t_w4.aum_1" in cat_df.columns:
                aum_curr = float(cat_df["t_w4.aum"].sum())
                aum_prev = float(cat_df["t_w4.aum_1"].sum())
                if aum_prev > 0:
                    aum_growth = (aum_curr - aum_prev) / aum_prev * 100
                    g_color = _GREEN if aum_growth >= 0 else _RED
                    g_sign = "+" if aum_growth >= 0 else ""
                    aum_growth_sub = (
                        f'<div style="font-size:9px;color:{g_color};font-weight:600;">'
                        f'{g_sign}{aum_growth:.1f}% MoM</div>'
                    )

            # REX share pp change
            if "t_w4.aum" in cat_df.columns and "t_w4.aum_1" in cat_df.columns:
                aum_curr_total = float(cat_df["t_w4.aum"].sum())
                aum_prev_total = float(cat_df["t_w4.aum_1"].sum())
                rex_cat = cat_df[cat_df["is_rex"] == True]
                if not rex_cat.empty and aum_curr_total > 0 and aum_prev_total > 0:
                    share_curr = float(rex_cat["t_w4.aum"].sum()) / aum_curr_total * 100
                    share_prev = float(rex_cat["t_w4.aum_1"].sum()) / aum_prev_total * 100
                    share_delta = share_curr - share_prev
                    s_color = _GREEN if share_delta >= 0 else _RED
                    s_sign = "+" if share_delta >= 0 else ""
                    share_change_sub = (
                        f'<div style="font-size:9px;color:{s_color};font-weight:600;">'
                        f'{s_sign}{share_delta:.1f}pp</div>'
                    )

            # New products (inception in last 30 days)
            if "inception_date" in cat_df.columns:
                cutoff_30d = pd.Timestamp.now() - pd.Timedelta(days=30)
                inception = pd.to_datetime(cat_df["inception_date"], errors="coerce")
                new_count = int((inception >= cutoff_30d).sum())
                if new_count > 0:
                    products_new_sub = (
                        f'<div style="font-size:9px;color:{_GREEN};font-weight:600;">'
                        f'+{new_count} new</div>'
                    )

    # Flow color
    flow_color = _flow_color(flow_1m)

    # 4 KPI row (24% each)
    _kpi_cell = f"padding:6px 4px;background:{_LIGHT};border-radius:6px;text-align:center;"
    kpi_html = f"""
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
    <tr>
      <td width="24%" style="{_kpi_cell}">
        <div style="font-size:15px;font-weight:700;color:{_NAVY};">{_fmt_currency_safe(cat_aum)}</div>
        {aum_growth_sub}
        <div style="font-size:9px;color:{_GRAY};text-transform:uppercase;">Total AUM</div>
      </td>
      <td width="1%"></td>
      <td width="24%" style="{_kpi_cell}">
        <div style="font-size:15px;font-weight:700;color:{_BLUE};">{rex_share:.1f}%</div>
        {share_change_sub}
        <div style="font-size:9px;color:{_GRAY};text-transform:uppercase;">REX Share</div>
      </td>
      <td width="1%"></td>
      <td width="24%" style="{_kpi_cell}">
        <div style="font-size:15px;font-weight:700;color:{flow_color};">{_fmt_flow_safe(flow_1m)}</div>
        <div style="font-size:9px;color:{_GRAY};text-transform:uppercase;">1M Flows</div>
      </td>
      <td width="1%"></td>
      <td width="24%" style="{_kpi_cell}">
        <div style="font-size:15px;font-weight:700;color:{_NAVY};">{num_products}</div>
        {products_new_sub}
        <div style="font-size:9px;color:{_GRAY};text-transform:uppercase;">Products</div>
      </td>
    </tr>
  </table>"""

    # Top 5 issuers table (aggregated from master)
    issuer_table = ""
    if master is not None and not master.empty and "category_display" in master.columns:
        cat_df = master[master["category_display"] == cat_name].copy()
        if not cat_df.empty and "issuer_display" in cat_df.columns:
            # Identify REX issuers
            rex_issuers = set()
            rex_rows = cat_df[cat_df["is_rex"] == True]
            if not rex_rows.empty and "issuer_display" in rex_rows.columns:
                rex_issuers = set(rex_rows["issuer_display"].dropna().unique())

            issuer_agg = cat_df.groupby("issuer_display").agg(
                aum=("t_w4.aum", "sum"),
                flow_1m=("t_w4.fund_flow_1month", "sum"),
                count=("t_w4.aum", "size"),
            ).sort_values("aum", ascending=False).head(5)

            issuer_rows = []
            for rank, (issuer_name, row) in enumerate(issuer_agg.iterrows(), 1):
                i_name = _esc(str(issuer_name))
                if len(i_name) > 22:
                    i_name = i_name[:19] + "..."
                i_aum = float(row["aum"])
                i_flow = float(row["flow_1m"])
                i_count = int(row["count"])
                is_rex_issuer = str(issuer_name) in rex_issuers

                if is_rex_issuer:
                    name_cell = (
                        f'<td style="{_TABLE_CELL}font-weight:700;color:{_BLUE};">'
                        f'{i_name} '
                        f'<span style="background:{_BLUE};color:{_WHITE};padding:1px 5px;'
                        f'border-radius:3px;font-size:8px;font-weight:700;vertical-align:middle;">REX</span>'
                        f'</td>'
                    )
                else:
                    name_cell = f'<td style="{_TABLE_CELL}font-weight:600;">{i_name}</td>'

                issuer_rows.append(
                    f'<tr>'
                    f'<td style="{_TABLE_CELL}text-align:center;width:26px;color:{_GRAY};">{rank}</td>'
                    f'{name_cell}'
                    f'<td style="{_TABLE_CELL_RIGHT}">{_fmt_currency_safe(i_aum)}</td>'
                    f'<td style="{_TABLE_CELL_RIGHT}color:{_flow_color(i_flow)};">'
                    f'{_fmt_flow_safe(i_flow)}</td>'
                    f'<td style="{_TABLE_CELL_RIGHT}">{i_count}</td>'
                    f'</tr>'
                )

            if issuer_rows:
                issuer_table = (
                    f'<div style="font-size:11px;color:{_GRAY};margin-top:6px;margin-bottom:2px;">'
                    f'Top issuers by AUM</div>'
                    f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
                    f' style="border-collapse:collapse;">'
                    f'<tr>'
                    f'<th style="{_TABLE_HEADER}text-align:center;width:26px;">#</th>'
                    f'<th style="{_TABLE_HEADER}">Issuer</th>'
                    f'<th style="{_TABLE_HEADER_RIGHT}">AUM</th>'
                    f'<th style="{_TABLE_HEADER_RIGHT}">1M Flow</th>'
                    f'<th style="{_TABLE_HEADER_RIGHT}"># Products</th>'
                    f'</tr>'
                    f'{"".join(issuer_rows)}'
                    f'</table>'
                )

    return f"""
<tr><td style="padding:12px 30px 5px;">
  <div style="font-size:15px;font-weight:700;color:{_NAVY};margin:0 0 8px 0;
    padding-bottom:6px;border-bottom:3px solid {border_color};">
    {_esc(display_name)}
  </div>
  {kpi_html}
  {issuer_table}
</td></tr>"""


def _render_landscape(landscape: dict, master: pd.DataFrame = None) -> str:
    """Render all category landscape cards."""
    if not landscape:
        return ""

    cards = []
    for cat_name, display_name, color in _LANDSCAPE_CATS:
        cat_data = landscape.get(cat_name)
        if not cat_data:
            continue
        cards.append(_render_category_card(cat_name, display_name, color, cat_data, master))

    if not cards:
        return ""

    return _render_landscape_header() + "\n".join(cards)


def _render_dashboard_cta(dashboard_url: str) -> str:
    url = _esc(dashboard_url)
    return f"""
<tr><td style="padding:20px 30px;" align="center">
  <table cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="background:{_BLUE};border-radius:8px;padding:16px 40px;">
      <a href="{url}" style="color:{_WHITE};text-decoration:none;
         font-size:16px;font-weight:700;">Open Dashboard</a>
    </td>
  </tr></table>
  <div style="font-size:12px;color:{_GRAY};margin-top:8px;">
    View full details, filings, and market intelligence
  </div>
</td></tr>"""


def _render_footer(week_ending: str) -> str:
    return f"""
<tr><td style="padding:16px 30px;border-top:1px solid {_BORDER};">
  <div style="font-size:11px;color:{_GRAY};text-align:center;">
    REX ETF Weekly Report | Week of {_esc(week_ending)}
  </div>
  <div style="font-size:10px;color:{_GRAY};text-align:center;margin-top:4px;">
    Data sourced from Bloomberg and SEC EDGAR
  </div>
  <div style="font-size:10px;color:{_GRAY};text-align:center;margin-top:4px;">
    To unsubscribe, contact relasmar@rexfin.com
  </div>
</td></tr>"""


def _render_market_unavailable() -> str:
    return f"""
<tr><td style="padding:15px 30px;">
  <div style="padding:16px;background:{_LIGHT};border-radius:8px;text-align:center;
              font-size:13px;color:{_GRAY};">
    Market data not available. Bloomberg data file has not been loaded.
  </div>
</td></tr>"""


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------
def build_weekly_digest_html(
    db_session,
    dashboard_url: str = "",
) -> str:
    today = datetime.now()
    week_ending = today.strftime("%B %d, %Y")
    dash_url = dashboard_url or _DEFAULT_DASHBOARD_URL

    market = _gather_market_data()
    filing = _gather_filing_data(db_session, days=7)

    data_as_of = market["data_as_of"] if market else ""

    sections = []

    # --- PART 1: Overview ---
    # 1. Header
    sections.append(_render_header(week_ending, data_as_of))

    # 2. Filing Activity (top of email)
    sections.append(_render_filing_activity(filing))

    if market:
        rex_df = market.get("rex_df", pd.DataFrame())

        # --- PART 2: REX Products ---
        # 3. Scorecard (with growth sub-labels)
        sections.append(_render_scorecard(market["kpis"], rex_df))

        # 4. AUM by Suite (stacked bar)
        aum_chart = _render_aum_stacked_bar(market["suites"])
        if aum_chart:
            sections.append(aum_chart)

        # 5. 1M Flows by Suite
        flow_chart = _render_flow_chart(market["suites"], market["flow_chart"])
        if flow_chart:
            sections.append(flow_chart)

        # 6. Winners, Losers & Yielders (combined)
        wly = _render_winners_losers_yielders(market["perf_metrics"], rex_df)
        if wly:
            sections.append(wly)

        # --- PART 3: Category Landscape ---
        landscape = market.get("landscape", {})
        master_df = market.get("master", pd.DataFrame())
        landscape_html = _render_landscape(landscape, master_df)
        if landscape_html:
            sections.append(landscape_html)
    else:
        sections.append(_render_scorecard_unavailable())
        sections.append(_render_market_unavailable())

    # --- PART 4: Close ---
    # 10. Dashboard CTA
    sections.append(_render_dashboard_cta(dash_url))

    # 11. Footer
    sections.append(_render_footer(week_ending))

    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>REX ETF Weekly Report - {_esc(week_ending)}</title>
</head>
<body style="margin:0;padding:0;background:{_LIGHT};
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  color:{_NAVY};line-height:1.5;">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{_LIGHT};">
<tr><td align="center" style="padding:20px 10px;">
<table width="600" cellpadding="0" cellspacing="0" border="0"
       style="background:{_WHITE};border-radius:8px;overflow:hidden;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
{body}
</table>
</td></tr></table>
</body></html>"""


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------
def send_weekly_digest(
    db_session,
    dashboard_url: str = "",
) -> bool:
    recipients = _load_recipients()
    if not recipients:
        log.warning("Weekly digest: no recipients configured")
        return False

    html_body = build_weekly_digest_html(db_session, dashboard_url)
    today = datetime.now()
    week_ending = today.strftime("%B %d, %Y")
    subject = f"REX ETF Weekly Report - Week of {week_ending}"

    # Try Azure Graph API first
    try:
        from webapp.services.graph_email import is_configured, send_email
        if is_configured():
            if send_email(subject=subject, html_body=html_body, recipients=recipients):
                log.info("Weekly digest sent via Graph API to %d recipients", len(recipients))
                return True
    except ImportError:
        pass

    # Fall back to SMTP
    config = _get_smtp_config()
    if not config["user"] or not config["password"] or not config["from_addr"]:
        log.warning("Weekly digest: SMTP not configured")
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
        log.info("Weekly digest sent via SMTP to %d recipients", len(recipients))
        return True
    except Exception as exc:
        log.error("Weekly digest send failed: %s", exc)
        return False
