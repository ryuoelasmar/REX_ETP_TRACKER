"""
Digest router - Subscribe page and send endpoint.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from webapp.dependencies import get_db
from webapp.models import DigestSubscriber

router = APIRouter(prefix="/digest", tags=["digest"])
templates = Jinja2Templates(directory="webapp/templates")

OUTPUT_DIR = Path("outputs")

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


@router.get("/")
def digest_index():
    return RedirectResponse("/digest/subscribe", status_code=302)


@router.get("/subscribe")
def subscribe_page(request: Request):
    """Show the digest subscription form."""
    return templates.TemplateResponse("digest_subscribe.html", {
        "request": request,
        "submitted": False,
        "error": None,
    })


@router.post("/subscribe")
def subscribe_submit(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    """Handle subscription request."""
    email = email.strip().lower()

    if not _EMAIL_RE.match(email):
        return templates.TemplateResponse("digest_subscribe.html", {
            "request": request,
            "submitted": False,
            "error": "Please enter a valid email address.",
        })

    # Check if already submitted (any status)
    existing = db.query(DigestSubscriber).filter(
        func.lower(DigestSubscriber.email) == email
    ).first()
    if existing:
        return templates.TemplateResponse("digest_subscribe.html", {
            "request": request,
            "submitted": False,
            "error": "This email has already been submitted.",
        })

    db.add(DigestSubscriber(email=email))
    db.commit()

    return templates.TemplateResponse("digest_subscribe.html", {
        "request": request,
        "submitted": True,
        "error": None,
    })


@router.post("/send")
def send_digest(request: Request):
    """Send the digest email now (admin action)."""
    try:
        from etp_tracker.email_alerts import send_digest_email

        dashboard_url = str(request.base_url).rstrip("/")
        sent = send_digest_email(OUTPUT_DIR, dashboard_url=dashboard_url)

        if sent:
            return RedirectResponse("/digest/subscribe?sent=ok", status_code=303)
        return RedirectResponse("/digest/subscribe?sent=fail", status_code=303)
    except Exception:
        return RedirectResponse("/digest/subscribe?sent=fail", status_code=303)
