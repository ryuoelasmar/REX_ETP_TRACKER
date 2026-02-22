# File Ownership — Wave 1 (2026-02-20)

## Context
Site-wide improvements: home page, quick fixes, funds pagination, downloads restructure, market intelligence backend.

## Active Agents

### QuickFixes (TASK-001 — feature/quick-fixes)
- webapp/static/css/style.css (EDIT)
- webapp/routers/dashboard.py (EDIT)
- webapp/templates/dashboard.html (EDIT)
- webapp/routers/admin.py (EDIT)
- webapp/main.py (EDIT)
- webapp/templates/base.html (EDIT)
- webapp/templates/home.html (CREATE)

### FundsDownloads (TASK-002 — feature/funds-downloads)
- webapp/routers/funds.py (EDIT)
- webapp/templates/fund_list.html (EDIT)
- webapp/routers/downloads.py (EDIT)
- webapp/templates/downloads.html (EDIT)

### MarketBackend (TASK-003 — feature/market-backend)
- webapp/services/market_data.py (EDIT)
- webapp/routers/market.py (EDIT)
- webapp/templates/market/base.html (EDIT)

## Off-Limits (all agents)
- etp_tracker/ (pipeline — no changes)
- screener/ (separate module — no changes)
- webapp/static/js/app.js (shared JS — read-only)
- CLAUDE.md
- .agents/
- config/
