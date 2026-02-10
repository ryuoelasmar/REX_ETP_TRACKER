"""
Authentication routes: login, callback, logout.

When Azure AD SSO is not configured, all routes are accessible without auth.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from webapp.auth import (
    build_auth_url,
    complete_auth,
    is_auth_configured,
    REDIRECT_PATH,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request):
    """Redirect user to Azure AD login page."""
    if not is_auth_configured():
        return RedirectResponse("/", status_code=302)

    redirect_uri = str(request.base_url).rstrip("/") + REDIRECT_PATH
    auth_url = build_auth_url(redirect_uri)
    if not auth_url:
        return HTMLResponse("<p>Azure AD not configured properly.</p>", status_code=500)
    return RedirectResponse(auth_url, status_code=302)


@router.get("/callback")
def callback(request: Request):
    """Handle Azure AD callback with authorization code."""
    if not is_auth_configured():
        return RedirectResponse("/", status_code=302)

    redirect_uri = str(request.base_url).rstrip("/") + REDIRECT_PATH
    code_response = dict(request.query_params)
    user_info = complete_auth(code_response, redirect_uri)

    if not user_info:
        return HTMLResponse("<p>Authentication failed. <a href='/'>Go home</a></p>", status_code=401)

    # Store user info in session
    request.session["user"] = user_info
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
def logout(request: Request):
    """Clear session and redirect home."""
    request.session.clear()
    return RedirectResponse("/", status_code=302)


@router.get("/me")
def me(request: Request):
    """Return current user info (for debugging/display)."""
    user = request.session.get("user")
    if user:
        return user
    return {"authenticated": False}
