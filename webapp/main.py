"""
FastAPI application factory for the ETP Filing Tracker web platform.

Run locally:
    uvicorn webapp.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from webapp.auth import SESSION_SECRET
from webapp.database import init_db

WEBAPP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize database. Shutdown: cleanup."""
    init_db()
    print("Database initialized.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ETP Filing Tracker",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Session middleware (required for Azure AD SSO)
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

    # Static files (CSS, JS)
    static_dir = WEBAPP_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routers
    from webapp.routers import auth_routes, dashboard, trusts, funds, filings
    app.include_router(auth_routes.router)
    app.include_router(dashboard.router)
    app.include_router(trusts.router, prefix="/trusts")
    app.include_router(funds.router, prefix="/funds")
    app.include_router(filings.router, prefix="/filings")

    # Health check
    @app.get("/health")
    def health():
        return {"status": "ok", "version": "2.0.0"}

    return app


app = create_app()
