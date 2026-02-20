# Agent: Quick-Fixes
# Branch: feature/quick-fixes
# Worktree: .worktrees/quick-fixes

## Your Files (ONLY touch these)
- webapp/static/css/style.css (EDIT)
- webapp/routers/dashboard.py (EDIT)
- webapp/templates/dashboard.html (EDIT)
- webapp/routers/admin.py (EDIT)
- webapp/main.py (EDIT)
- webapp/templates/base.html (EDIT)
- webapp/templates/home.html (CREATE)

## Task: TASK-001
### Quick Fixes + Home Page + Branding

Implement site-wide quick fixes and branding improvements across the ETP tracker webapp.

**Context**: This is a FastAPI + Jinja2 webapp running on Python 3.13. All routes use SQLAlchemy sessions. The `sortTable()` function already exists in `webapp/static/js/app.js:81–110` — do NOT modify app.js. The dashboard router is currently mounted at `/` with no prefix. The base.html default title is "ETP Filing Tracker".

---

**Fix 1 — CSS First-Row Bug (style.css)**

Delete the following line from `webapp/static/css/style.css` (search for it exactly):
```css
tbody tr:first-child td { padding-top: var(--sp-3); }
```
This single line causes the first row of every data-table to appear visually blocked. Removing it fixes all pages (screener, funds, dashboard, market).

---

**Fix 2 — Dashboard: Dynamic Filing Limit (dashboard.py)**

Find `.limit(50)` in `webapp/routers/dashboard.py` and replace it with:
```python
filing_limit = min(500, max(50, days * 4))
```
Then chain `.limit(filing_limit)` instead of `.limit(50)`.

Also pass `"filing_limit": filing_limit` to the template context in the `TemplateResponse` call.

---

**Fix 3 — Dashboard: Sortable Filings Table (dashboard.html)**

In `webapp/templates/dashboard.html`, find the filings table `<thead>` row and add `onclick="sortTable('recentFilings', N)"` and `class="sortable"` to each `<th>`. The table must have `id="recentFilings"`. Column index N starts at 0. Columns are: Date, Form, Trust, Fund/Series, Effective Date, Filing Link (or whatever columns exist — read the file first to find exact columns).

Also update the filing count display to show the dynamic limit: e.g., `Showing up to {{ filing_limit }} filings`.

---

**Fix 4 — Admin: Trust Approval Feedback (admin.py)**

In `webapp/routers/admin.py`, find the trust approval handler (the POST endpoint that calls `add_trust()`). It has a try/except block — the try writes to trusts.py, the except falls through to DB-only. Update the success message to include:
- If the file write succeeded: "Trust added to database and registered in trusts.py"
- If the file write failed (caught by except): "Trust added to database (trusts.py update skipped — read-only filesystem on Render)"

Pass a `detail` string that distinguishes these cases.

---

**Fix 5 — Home Page (main.py + home.html)**

Step 5a: In `webapp/routers/dashboard.py`, find `@router.get("/")` and change it to `@router.get("/dashboard")`. Keep all other code identical.

Step 5b: In `webapp/main.py`, after the router imports but before the health check route, add:
```python
@app.get("/")
def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})
```

Step 5c: In `webapp/templates/base.html`:
- Change `<a href="/" ...>Dashboard</a>` to `<a href="/dashboard" ...>Dashboard</a>`
- Update the active class check: `{% if '/dashboard' in request.url.path %}class="active"{% endif %}`
- Also add a "Home" link to the nav: `<a href="/" {% if request.url.path == '/' %}class="active"{% endif %}>Home</a>` — insert it BEFORE the Dashboard link

Step 5d: Create `webapp/templates/home.html`:
```html
{% extends "base.html" %}
{% block title %}REX Financial Intelligence Hub{% endblock %}
{% block content %}
<div class="home-hero">
  <h1 class="home-title">REX Financial Intelligence Hub</h1>
  <p class="home-tagline">
    A unified intelligence platform for tracking, analyzing, and monitoring the
    leveraged and structured ETP market. Built for REX Financial product teams to
    monitor SEC filing activity across 122 trusts, benchmark market positioning
    against competitors, evaluate launch candidates, and track inflow/outflow trends
    in real time.
  </p>
</div>

<div class="home-grid">
  <a href="/dashboard" class="home-card">
    <div class="home-card-icon">📋</div>
    <div class="home-card-title">Filing Tracker</div>
    <div class="home-card-desc">Monitor SEC filings across 122 trusts. Track 485BPOS, 485BXT, and 497 forms in real time.</div>
  </a>
  <a href="/market/rex" class="home-card">
    <div class="home-card-icon">📊</div>
    <div class="home-card-title">Market Intelligence</div>
    <div class="home-card-desc">Competitive AUM analysis, market share tracking, and category-level benchmarking.</div>
  </a>
  <a href="/screener/" class="home-card">
    <div class="home-card-icon">🔍</div>
    <div class="home-card-title">Launch Screener</div>
    <div class="home-card-desc">Evaluate ETP launch candidates across 4 scoring pillars: AUM, flows, options, spread.</div>
  </a>
  <a href="/funds/" class="home-card">
    <div class="home-card-icon">🗃️</div>
    <div class="home-card-title">Fund Search</div>
    <div class="home-card-desc">Search 7,000+ ETF funds by ticker, name, or trust. Filter by status and form type.</div>
  </a>
  <a href="/downloads/" class="home-card">
    <div class="home-card-icon">⬇️</div>
    <div class="home-card-title">Downloads</div>
    <div class="home-card-desc">Export fund status, filing history, and pipeline CSVs for any trust.</div>
  </a>
</div>

<div class="home-contact">
  <p>Questions or feedback about this platform? Contact <a href="mailto:relasmar@rexfin.com">relasmar@rexfin.com</a></p>
</div>
{% endblock %}
```

NOTE: Avoid using emoji in the icon divs if they cause encoding issues — use text labels instead (e.g., "FILINGS", "MARKET", etc.).

---

**Fix 6 — Page Title + Base Title**

In `webapp/templates/base.html` line 6, change the default `<title>` fallback from `ETP Filing Tracker` to `REX Financial Intelligence Hub`.

In `webapp/templates/dashboard.html`, find the `{% block title %}` and update it to:
```
{% block title %}Filing Dashboard — REX Financial Intelligence Hub{% endblock %}
```

---

**Acceptance Criteria**:
- [ ] `tbody tr:first-child td { padding-top: ... }` line is gone from style.css
- [ ] Dashboard filing limit scales with days (7 days → 28 rows min 50, 90 days → 360 rows capped 500)
- [ ] Filings table `<th>` elements have onclick sortTable attributes
- [ ] Admin trust approval shows "and trusts.py" vs "skipped on Render" in response
- [ ] `GET /` serves home.html with "REX Financial Intelligence Hub" heading and contact email
- [ ] `GET /dashboard` serves the dashboard (old `/` route)
- [ ] base.html default title is "REX Financial Intelligence Hub"

---

## Status: DONE

## Log:
- ccfecf8 fix: remove CSS first-row padding bug from style.css
- 3310b17 feat: dynamic filing limit and move dashboard route to /dashboard
- 314e90d feat: sortable filings table, dynamic limit display, updated title and routes
- fb2e7e3 feat: trust approval feedback distinguishes trusts.py write vs Render skip
- d1cccff feat: add home page at /, update nav links and base title
