"""PDF Executive Report Generator using ReportLab."""
from __future__ import annotations

import io
import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

log = logging.getLogger(__name__)

# Colors matching the webapp design
NAVY = colors.HexColor("#1a1a2e")
BLUE = colors.HexColor("#0984e3")
GREEN = colors.HexColor("#27ae60")
ORANGE = colors.HexColor("#e67e22")
RED = colors.HexColor("#e74c3c")
LIGHT_BG = colors.HexColor("#f5f7fa")
BORDER = colors.HexColor("#cccccc")


def _build_styles():
    """Create paragraph styles for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=22, textColor=NAVY, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "SectionHead", parent=styles["Heading2"],
        fontSize=14, textColor=NAVY, spaceBefore=16, spaceAfter=8,
        borderWidth=1, borderColor=NAVY, borderPadding=4,
    ))
    styles.add(ParagraphStyle(
        "SubHead", parent=styles["Heading3"],
        fontSize=11, textColor=BLUE, spaceBefore=10, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "ReportBody", parent=styles["Normal"],
        fontSize=9, leading=12, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "SmallNote", parent=styles["Normal"],
        fontSize=7, textColor=colors.grey, leading=9,
    ))
    return styles


def _table_style():
    """Standard table style matching the webapp."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])


def generate_executive_report(
    results: list[dict],
    rex_funds: list[dict] | None = None,
    model_info: dict | None = None,
    data_date: str | None = None,
) -> bytes:
    """Generate the executive PDF report.

    Args:
        results: List of scored candidate dicts (from ScreenerResult)
        rex_funds: Optional list of REX fund performance dicts
        model_info: Optional dict with model_type, r_squared, n_training
        data_date: Optional date string for data freshness

    Returns:
        PDF bytes
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    styles = _build_styles()
    story = []

    report_date = datetime.now().strftime("%B %d, %Y")

    # ===== PAGE 1: EXECUTIVE SUMMARY =====
    story.append(Paragraph("ETF Launch Screener", styles["ReportTitle"]))
    story.append(Paragraph("Executive Report", styles["SubHead"]))
    story.append(Paragraph(
        f"Report Date: {report_date} | Data as of: {data_date or report_date}",
        styles["SmallNote"],
    ))
    story.append(Spacer(1, 12))

    # Top 5 candidates
    story.append(Paragraph("Top Launch Candidates", styles["SectionHead"]))
    story.append(Paragraph(
        "Ranked by composite percentile score across options liquidity, volume, "
        "market cap, and momentum indicators. Higher score = stronger candidate.",
        styles["SmallNote"],
    ))
    story.append(Spacer(1, 6))

    top5 = results[:5]
    if top5:
        header = ["Rank", "Ticker", "Sector", "Score", "Pred. AUM ($M)", "Filing Status", "Density"]
        data = [header]
        for i, r in enumerate(top5):
            data.append([
                str(i + 1),
                str(r.get("ticker", "")),
                str(r.get("sector", "-"))[:20],
                f"{r.get('composite_score', 0):.1f}",
                f"${r.get('predicted_aum', 0):,.0f}" if r.get("predicted_aum") else "-",
                str(r.get("filing_status", "Not Filed"))[:30],
                str(r.get("competitive_density", "-")),
            ])

        t = Table(data, colWidths=[35, 55, 100, 40, 75, 120, 70])
        t.setStyle(_table_style())
        story.append(t)

    story.append(Spacer(1, 16))

    # Key insights
    filed_count = sum(1 for r in results if r.get("filing_status", "").startswith("REX Filed"))
    qualified = sum(1 for r in results if r.get("passes_filters"))
    story.append(Paragraph("Key Insights", styles["SubHead"]))
    story.append(Paragraph(
        f"<b>{len(results):,}</b> stocks screened | "
        f"<b>{qualified}</b> pass all threshold filters | "
        f"<b>{filed_count}</b> have REX filings",
        styles["ReportBody"],
    ))

    story.append(PageBreak())

    # ===== PAGE 2: FULL SCREENING RESULTS (TOP 20) =====
    story.append(Paragraph("Screening Results - Top 20", styles["SectionHead"]))
    story.append(Paragraph(
        "Composite Score (0-100): Weighted percentile rank across call open interest (25%), "
        "total OI (15%), volume (25%), market cap (15%), turnover (10%), and sentiment indicators (10%).",
        styles["SmallNote"],
    ))
    story.append(Spacer(1, 6))

    top20 = results[:20]
    if top20:
        header = ["#", "Ticker", "Sector", "Score", "Pred AUM", "Mkt Cap", "Call OI%", "Density", "Filing", "Pass"]
        data = [header]
        for i, r in enumerate(top20):
            data.append([
                str(i + 1),
                str(r.get("ticker", "")),
                str(r.get("sector", "-"))[:15],
                f"{r.get('composite_score', 0):.1f}",
                f"${r.get('predicted_aum', 0):,.0f}" if r.get("predicted_aum") else "-",
                f"${r.get('mkt_cap', 0):,.0f}" if r.get("mkt_cap") else "-",
                f"{r.get('call_oi_pctl', 0):.0f}" if r.get("call_oi_pctl") else "-",
                str(r.get("competitive_density", "-")),
                str(r.get("filing_status", "-"))[:20],
                "Y" if r.get("passes_filters") else "N",
            ])

        t = Table(data, colWidths=[20, 48, 65, 35, 52, 58, 38, 55, 85, 25])
        ts = _table_style()
        # Highlight qualified rows
        for i, r in enumerate(top20):
            if r.get("passes_filters"):
                ts.add("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#e8f5e9"))
        t.setStyle(ts)
        story.append(t)

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Predicted AUM: Regression estimate based on characteristics of existing successful leveraged ETFs. "
        "Green rows pass all threshold filters (market cap, call OI, volume above REX fund medians).",
        styles["SmallNote"],
    ))

    story.append(PageBreak())

    # ===== PAGE 3: COMPETITIVE LANDSCAPE =====
    story.append(Paragraph("Competitive Landscape", styles["SectionHead"]))
    story.append(Paragraph(
        "Competitive Density: Number of existing leveraged ETFs on each underlier. "
        "'Crowded' = 5+ products, 'Competitive' = 3-4, 'Early Stage' = 1-2, 'Uncontested' = 0.",
        styles["SmallNote"],
    ))
    story.append(Spacer(1, 8))

    # Group top 20 by density category
    for category in ["Uncontested", "Early Stage", "Competitive", "Crowded"]:
        cat_results = [r for r in top20 if r.get("competitive_density") == category]
        if not cat_results:
            continue

        story.append(Paragraph(f"{category} ({len(cat_results)} candidates)", styles["SubHead"]))
        header = ["Ticker", "Score", "Pred AUM", "# Products", "Total AUM", "Filing"]
        data = [header]
        for r in cat_results:
            data.append([
                str(r.get("ticker", "")),
                f"{r.get('composite_score', 0):.1f}",
                f"${r.get('predicted_aum', 0):,.0f}" if r.get("predicted_aum") else "-",
                str(r.get("competitor_count", 0)),
                f"${r.get('total_competitor_aum', 0):,.0f}" if r.get("total_competitor_aum") else "-",
                str(r.get("filing_status", "-"))[:25],
            ])
        t = Table(data, colWidths=[60, 45, 70, 60, 70, 120])
        t.setStyle(_table_style())
        story.append(t)
        story.append(Spacer(1, 8))

    # Uncontested with no density data
    no_density = [r for r in top20 if not r.get("competitive_density")]
    if no_density:
        story.append(Paragraph(f"No Existing Products ({len(no_density)} candidates)", styles["SubHead"]))
        story.append(Paragraph(
            "These candidates have no existing leveraged ETFs - potential first-mover opportunities.",
            styles["ReportBody"],
        ))

    story.append(PageBreak())

    # ===== PAGE 4: REX FUND PERFORMANCE =====
    if rex_funds:
        story.append(Paragraph("REX Fund Performance", styles["SectionHead"]))

        total_aum = sum(f.get("aum", 0) for f in rex_funds)
        total_flow = sum(f.get("flow_1m", 0) for f in rex_funds)
        story.append(Paragraph(
            f"Total REX Leveraged AUM: <b>${total_aum:,.0f}M</b> | "
            f"Net Flows (1M): <b>${total_flow:,.0f}M</b> | "
            f"Funds: <b>{len(rex_funds)}</b>",
            styles["ReportBody"],
        ))
        story.append(Spacer(1, 8))

        header = ["Ticker", "Underlier", "AUM ($M)", "Flow 1M", "Flow 3M", "Flow YTD", "Ret YTD"]
        data = [header]
        for f in sorted(rex_funds, key=lambda x: x.get("aum", 0), reverse=True)[:25]:
            data.append([
                str(f.get("ticker", "")),
                str(f.get("underlier", ""))[:12],
                f"{f.get('aum', 0):,.1f}",
                f"{f.get('flow_1m', 0):,.1f}",
                f"{f.get('flow_3m', 0):,.1f}",
                f"{f.get('flow_ytd', 0):,.1f}",
                f"{f.get('return_ytd', 0):.1f}%",
            ])

        t = Table(data, colWidths=[55, 65, 55, 55, 55, 55, 50])
        t.setStyle(_table_style())
        story.append(t)

        story.append(PageBreak())

    # ===== PAGE 5: METHODOLOGY =====
    story.append(Paragraph("Methodology & Diagnostics", styles["SectionHead"]))

    # Scoring weights
    story.append(Paragraph("Scoring Weights", styles["SubHead"]))
    from screener.config import SCORING_WEIGHTS
    weights_data = [["Factor", "Weight"]]
    for factor, weight in SCORING_WEIGHTS.items():
        weights_data.append([factor, f"{weight:.0%}"])
    t = Table(weights_data, colWidths=[200, 60])
    t.setStyle(_table_style())
    story.append(t)
    story.append(Spacer(1, 12))

    # Model diagnostics
    if model_info:
        story.append(Paragraph("Regression Model", styles["SubHead"]))
        story.append(Paragraph(
            f"Model Type: <b>{model_info.get('model_type', 'N/A')}</b> | "
            f"R-squared: <b>{model_info.get('r_squared', 0):.3f}</b> | "
            f"Training Samples: <b>{model_info.get('n_training', 0)}</b>",
            styles["ReportBody"],
        ))
        story.append(Spacer(1, 8))

    # Data sources
    story.append(Paragraph("Data Sources", styles["SubHead"]))
    story.append(Paragraph(
        f"Stock Universe: {len(results):,} US equities (Bloomberg) | "
        f"ETP Universe: 5,068 ETPs (Bloomberg) | "
        f"Filing Data: SEC EDGAR pipeline",
        styles["ReportBody"],
    ))
    story.append(Spacer(1, 12))

    # Disclaimer
    story.append(Paragraph("Disclaimer", styles["SubHead"]))
    story.append(Paragraph(
        "Model outputs are directional estimates, not guarantees. Predicted AUM values "
        "reflect statistical relationships observed in existing leveraged ETFs and should "
        "be interpreted as relative indicators, not precise forecasts. All data sourced "
        "from Bloomberg and SEC EDGAR.",
        styles["SmallNote"],
    ))

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"REX Financial | ETF Launch Screener | Generated {report_date}",
        styles["SmallNote"],
    ))

    # Build PDF
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    log.info("PDF report generated: %d bytes, %d candidates", len(pdf_bytes), len(results))
    return pdf_bytes
