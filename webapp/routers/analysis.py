"""
Analysis router - On-demand Claude AI analysis of SEC filings.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.dependencies import get_db
from webapp.models import Filing, Trust, FundStatus, AnalysisResult
from webapp.services.claude_service import (
    ANALYSIS_TYPES,
    analyze_filing,
    estimate_cost,
    is_configured,
)

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

CACHE_DIR = Path("http_cache/web")


def _get_filing_text(filing: Filing) -> str:
    """Retrieve cached filing text from http_cache."""
    if not filing.primary_link:
        return ""

    # Match the cache key used by sec_client.py
    url_hash = hashlib.sha256(filing.primary_link.encode("utf-8")).hexdigest()
    cache_path = CACHE_DIR / f"{url_hash}.txt"
    if cache_path.exists():
        try:
            return cache_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return ""


@router.get("/analysis/filing/{filing_id}")
def analysis_page(request: Request, filing_id: int, db: Session = Depends(get_db)):
    """Show analysis options for a filing."""
    filing = db.get(Filing, filing_id)
    if not filing:
        return templates.TemplateResponse("analysis.html", {
            "request": request,
            "error": "Filing not found",
            "filing": None,
        })

    trust = db.get(Trust, filing.trust_id)
    filing_text = _get_filing_text(filing)
    cost_estimate = estimate_cost(len(filing_text)) if filing_text else None

    # Get existing analyses for this filing
    existing = db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.filing_id == filing_id)
        .order_by(AnalysisResult.created_at.desc())
    ).scalars().all()

    return templates.TemplateResponse("analysis.html", {
        "request": request,
        "filing": filing,
        "trust": trust,
        "has_text": bool(filing_text),
        "text_length": len(filing_text),
        "cost_estimate": cost_estimate,
        "analysis_types": ANALYSIS_TYPES,
        "existing_analyses": existing,
        "configured": is_configured(),
        "error": None,
    })


@router.post("/analysis/filing/{filing_id}")
def run_analysis(
    request: Request,
    filing_id: int,
    analysis_type: str = Form(...),
    db: Session = Depends(get_db),
):
    """Run Claude analysis on a filing."""
    filing = db.get(Filing, filing_id)
    if not filing:
        return templates.TemplateResponse("analysis.html", {
            "request": request,
            "error": "Filing not found",
            "filing": None,
        })

    trust = db.get(Trust, filing.trust_id)
    filing_text = _get_filing_text(filing)

    if not filing_text:
        return templates.TemplateResponse("analysis.html", {
            "request": request,
            "error": "No cached filing text available. Run the pipeline first to download filings.",
            "filing": filing,
            "trust": trust,
            "has_text": False,
            "text_length": 0,
            "cost_estimate": None,
            "analysis_types": ANALYSIS_TYPES,
            "existing_analyses": [],
            "configured": is_configured(),
        })

    # Run analysis
    result = analyze_filing(
        filing_text=filing_text,
        analysis_type=analysis_type,
        trust_name=trust.name if trust else "",
    )

    if "error" in result:
        existing = db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.filing_id == filing_id)
            .order_by(AnalysisResult.created_at.desc())
        ).scalars().all()

        return templates.TemplateResponse("analysis.html", {
            "request": request,
            "error": result["error"],
            "filing": filing,
            "trust": trust,
            "has_text": True,
            "text_length": len(filing_text),
            "cost_estimate": estimate_cost(len(filing_text)),
            "analysis_types": ANALYSIS_TYPES,
            "existing_analyses": existing,
            "configured": is_configured(),
        })

    # Convert markdown to simple HTML (basic conversion)
    result_html = _markdown_to_html(result["result_text"])

    # Save to database
    analysis = AnalysisResult(
        filing_id=filing_id,
        analysis_type=analysis_type,
        prompt_used=ANALYSIS_TYPES[analysis_type]["prompt"],
        result_text=result["result_text"],
        result_html=result_html,
        model_used=result["model_used"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        requested_by=request.session.get("user", {}).get("email", "local"),
    )
    db.add(analysis)
    db.commit()

    # Reload existing analyses
    existing = db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.filing_id == filing_id)
        .order_by(AnalysisResult.created_at.desc())
    ).scalars().all()

    return templates.TemplateResponse("analysis.html", {
        "request": request,
        "filing": filing,
        "trust": trust,
        "has_text": True,
        "text_length": len(filing_text),
        "cost_estimate": estimate_cost(len(filing_text)),
        "analysis_types": ANALYSIS_TYPES,
        "existing_analyses": existing,
        "configured": is_configured(),
        "error": None,
        "just_ran": analysis_type,
    })


def _markdown_to_html(text: str) -> str:
    """Basic markdown-to-HTML conversion for analysis results."""
    import re
    lines = text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
            continue

        # Headers
        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h4>{stripped[4:]}</h4>")
            continue
        if stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{stripped[3:]}</h3>")
            continue
        if stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{stripped[2:]}</h2>")
            continue

        # Bold markers
        stripped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)

        # List items
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{stripped[2:]}</li>")
            continue

        # Numbered list
        m = re.match(r"^\d+\.\s+(.+)", stripped)
        if m:
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{m.group(1)}</li>")
            continue

        if in_list:
            html_lines.append("</ul>")
            in_list = False
        html_lines.append(f"<p>{stripped}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)
