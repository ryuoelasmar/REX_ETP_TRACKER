"""
EDGAR Search router - Search for trusts/registrants on SEC EDGAR.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.dependencies import get_db
from webapp.models import Trust
from webapp.services.sec_search import search_trusts, verify_cik

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")


@router.get("/search/")
def search_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    """EDGAR search page. Shows results when ?q= is provided."""
    results = []
    existing_ciks = set()

    if q.strip():
        results = search_trusts(q)

        # Mark which CIKs we already monitor
        existing_ciks = set(
            row[0] for row in db.execute(select(Trust.cik)).all()
        )

    return templates.TemplateResponse("search.html", {
        "request": request,
        "q": q,
        "results": results,
        "existing_ciks": existing_ciks,
    })


@router.get("/search/verify/{cik}")
def verify_page(request: Request, cik: str, db: Session = Depends(get_db)):
    """Verify a CIK and show entity details before adding."""
    details = verify_cik(cik)
    if not details:
        return templates.TemplateResponse("search_verify.html", {
            "request": request,
            "error": f"CIK {cik} not found on SEC EDGAR.",
            "details": None,
        })

    # Check if already monitored
    existing = db.execute(
        select(Trust).where(Trust.cik == cik)
    ).scalar_one_or_none()

    return templates.TemplateResponse("search_verify.html", {
        "request": request,
        "details": details,
        "already_monitored": existing is not None,
        "error": None,
    })


@router.post("/search/add")
def add_trust(request: Request, cik: str = "", name: str = "", db: Session = Depends(get_db)):
    """Add a new trust to monitoring from search results."""
    import re

    if not cik or not name:
        return RedirectResponse("/search/", status_code=302)

    # Check if already exists
    existing = db.execute(
        select(Trust).where(Trust.cik == cik)
    ).scalar_one_or_none()

    if existing:
        return RedirectResponse(f"/trusts/{existing.slug}", status_code=302)

    # Create slug
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")

    db.add(Trust(
        cik=cik,
        name=name,
        slug=slug,
        is_rex=False,
        is_active=True,
        added_by="SEARCH",
    ))
    db.commit()

    from urllib.parse import quote
    return RedirectResponse(f"/?added={quote(name)}", status_code=302)
