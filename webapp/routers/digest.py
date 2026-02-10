"""
Digest router - Preview and send email digest from the web interface.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/digest", tags=["digest"])
templates = Jinja2Templates(directory="webapp/templates")

OUTPUT_DIR = Path("outputs")


@router.get("/preview")
def preview_digest(request: Request):
    """Preview the current digest email HTML."""
    from etp_tracker.email_alerts import build_digest_html

    html = build_digest_html(OUTPUT_DIR, dashboard_url="")
    return HTMLResponse(content=html)


@router.post("/send")
def send_digest(request: Request):
    """Send the digest email now."""
    from etp_tracker.email_alerts import send_digest_email

    sent = send_digest_email(OUTPUT_DIR)
    if sent:
        return {"status": "sent", "message": "Digest email sent successfully"}
    return {"status": "failed", "message": "Failed to send digest. Check SMTP/Azure config."}
