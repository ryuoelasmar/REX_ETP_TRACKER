"""
Holdings router - Institutional holdings from 13F-HR filings.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session

from webapp.dependencies import get_db
from webapp.models import Institution, Holding, CusipMapping, FundStatus

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")


def _fmt_value(val: float | None) -> str:
    """Format USD value for display (values in thousands as reported in 13F)."""
    if val is None:
        return "--"
    v = val * 1000  # 13F reports in thousands
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


@router.get("/holdings/")
def holdings_list(
    request: Request,
    q: str = "",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=10, le=200),
    sort: str = "aum",
    db: Session = Depends(get_db),
):
    """List institutions with their holdings summary."""
    # Subquery: holdings stats per institution
    holdings_sq = (
        select(
            Holding.institution_id,
            func.count(Holding.id).label("holding_count"),
            func.sum(Holding.value_usd).label("total_value"),
        )
        .group_by(Holding.institution_id)
        .subquery()
    )

    query = (
        select(
            Institution,
            func.coalesce(holdings_sq.c.holding_count, 0).label("holding_count"),
            func.coalesce(holdings_sq.c.total_value, 0).label("total_value"),
        )
        .outerjoin(holdings_sq, holdings_sq.c.institution_id == Institution.id)
    )

    if q.strip():
        query = query.where(Institution.name.ilike(f"%{q}%"))

    # Sort
    if sort == "name":
        query = query.order_by(Institution.name)
    elif sort == "filings":
        query = query.order_by(desc(Institution.filing_count))
    elif sort == "last_filed":
        query = query.order_by(desc(Institution.last_filed))
    else:  # aum (default)
        query = query.order_by(desc(func.coalesce(holdings_sq.c.total_value, 0)))

    # Count
    total_results = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar() or 0
    total_pages = max(1, math.ceil(total_results / per_page))
    page = min(page, total_pages)

    # Paginate
    results = db.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    ).all()

    # Total institutions
    total_institutions = db.execute(
        select(func.count(Institution.id))
    ).scalar() or 0

    # Total holdings value
    total_holdings_value = db.execute(
        select(func.sum(Holding.value_usd))
    ).scalar() or 0

    # Matched CUSIPs count
    matched_cusips = db.execute(
        select(func.count(CusipMapping.id)).where(CusipMapping.trust_id.isnot(None))
    ).scalar() or 0

    return templates.TemplateResponse("holdings.html", {
        "request": request,
        "institutions": results,
        "q": q,
        "sort": sort,
        "page": page,
        "per_page": per_page,
        "total_results": total_results,
        "total_pages": total_pages,
        "total_institutions": total_institutions,
        "total_holdings_value": _fmt_value(total_holdings_value),
        "matched_cusips": matched_cusips,
        "fmt_value": _fmt_value,
    })


@router.get("/holdings/{cik}")
def institution_detail(
    cik: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Institution detail page with all holdings."""
    institution = db.execute(
        select(Institution).where(Institution.cik == cik)
    ).scalar_one_or_none()

    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found")

    # Get most recent report date for this institution
    latest_date = db.execute(
        select(func.max(Holding.report_date))
        .where(Holding.institution_id == institution.id)
    ).scalar()

    # Get holdings for most recent report date
    holdings_query = (
        select(Holding)
        .where(Holding.institution_id == institution.id)
    )
    if latest_date:
        holdings_query = holdings_query.where(Holding.report_date == latest_date)
    holdings_query = holdings_query.order_by(desc(Holding.value_usd))

    holdings = db.execute(holdings_query).scalars().all()

    # Get CUSIP mappings for matching
    cusip_map = {}
    if holdings:
        cusips = [h.cusip for h in holdings if h.cusip]
        if cusips:
            mappings = db.execute(
                select(CusipMapping).where(CusipMapping.cusip.in_(cusips))
            ).scalars().all()
            cusip_map = {m.cusip: m for m in mappings}

    # Split into matched and unmatched
    matched_holdings = []
    unmatched_holdings = []
    for h in holdings:
        mapping = cusip_map.get(h.cusip)
        if mapping and mapping.trust_id:
            # Get the fund info for this CUSIP
            fund = db.execute(
                select(FundStatus)
                .where(FundStatus.trust_id == mapping.trust_id)
                .where(FundStatus.ticker == mapping.ticker)
            ).scalar_one_or_none()
            matched_holdings.append({"holding": h, "mapping": mapping, "fund": fund})
        else:
            unmatched_holdings.append(h)

    # Summary stats
    total_value = sum(h.value_usd or 0 for h in holdings)
    total_positions = len(holdings)

    return templates.TemplateResponse("institution.html", {
        "request": request,
        "institution": institution,
        "holdings": holdings,
        "matched_holdings": matched_holdings,
        "unmatched_holdings": unmatched_holdings,
        "latest_date": latest_date,
        "total_value": _fmt_value(total_value),
        "total_positions": total_positions,
        "matched_count": len(matched_holdings),
        "fmt_value": _fmt_value,
    })
