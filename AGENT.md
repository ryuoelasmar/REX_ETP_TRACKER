# Agent: Funds-Downloads
# Branch: feature/funds-downloads
# Worktree: .worktrees/funds-downloads

## Your Files (ONLY touch these)
- webapp/routers/funds.py (EDIT)
- webapp/templates/fund_list.html (EDIT)
- webapp/routers/downloads.py (EDIT)
- webapp/templates/downloads.html (EDIT)

## Task: TASK-002
### Funds Pagination + Sortable Columns + Downloads Restructure

Improve the Funds and Downloads pages of the ETP tracker webapp.

**Context**: FastAPI + Jinja2 + SQLAlchemy. The `sortTable()` function already exists in `webapp/static/js/app.js:81–110` — do NOT modify app.js. Trust-level DB models: `Trust`, `FundStatus`, `Filing`, `FundExtraction`, `NameHistory`. Current exports: `GET /downloads/export/funds` (all funds) and `GET /downloads/export/trust/{trust_id}/filings`.

---

**Fix 1 — Funds: Sortable Column Headers (fund_list.html)**

Read `webapp/templates/fund_list.html` first to understand the current table structure.

Add `onclick="sortTable('fundTable', N)"` and `class="sortable"` to each `<th>` in the funds table. The table must have `id="fundTable"`. N = 0-indexed column number. Typical columns: #, Ticker, Fund Name, Trust, Status, Effective Date, Latest Form — read the template to confirm exact columns.

---

**Fix 2 — Funds: Pagination (funds.py + fund_list.html)**

In `webapp/routers/funds.py`:
1. Add query params: `page: int = 1`, `per_page: int = 100`
2. Before applying offset/limit, run a count query to get `total_results`
3. Apply `.offset((page - 1) * per_page).limit(per_page)` to the main query
4. Compute `total_pages = math.ceil(total_results / per_page)` (import math)
5. Pass to template: `page`, `per_page`, `total_results`, `total_pages`

In `webapp/templates/fund_list.html`:
1. Add a per-page selector near the filter bar: options 25, 50, 100, 250. On change, update URL with `per_page=N` param, preserve other params (q, status, trust_id).
2. Add a pagination bar below the table:
   - Show "Showing X-Y of Z funds"
   - Prev button (disabled if page=1)
   - Page number links (show up to 7 pages, with ellipsis for large ranges)
   - Next button (disabled if page=total_pages)
   - All links must preserve q, status, trust_id, per_page params

---

**Fix 3 — Funds: Investigate Missing 33 Act Trust Funds (funds.py)**

Read `webapp/fund_filters.py` to see the MUTUAL_FUND_EXCLUSIONS patterns.

In `funds.py`, add a diagnostic: after building the main query but before returning results, also run:
```python
# Count trusts with zero FundStatus records
from sqlalchemy import text
trusts_with_no_funds = db.execute(
    select(Trust.name).where(Trust.is_active == True)
    .where(~Trust.id.in_(select(FundStatus.trust_id).distinct()))
    .order_by(Trust.name)
).scalars().all()
```
Pass `trusts_with_no_funds` to the template. In `fund_list.html`, if this list is non-empty, show a dismissible info banner above the table:
```
Note: X trusts have no fund records (likely S-1/N-2 filers that don't submit 485 forms): [trust names]
```
This surfaces the problem without requiring pipeline changes.

---

**Fix 4 — Downloads: New All-Filings Export Endpoint (downloads.py)**

Add a new endpoint `GET /downloads/export/filings` that exports all filings across all trusts as CSV. Columns: Trust, Filing Date, Form, Accession Number, Series Name, Class Name, Ticker, Effective Date, Confidence, Primary Link. Join `Filing`, `FundExtraction`, and `Trust`. Order by `Trust.name, Filing.filing_date desc`. Return as StreamingResponse with filename `filings_export.csv`.

Pattern: mirror the existing `export/funds` endpoint in the same file.

---

**Fix 5 — Downloads: Restructure Page (downloads.py + downloads.html)**

Read `webapp/routers/downloads.py` and `webapp/templates/downloads.html` first.

In `downloads.py`, the template context needs these changes:
- Keep `summary_files`, `trust_files`, `digest_files`, `all_trusts` from the current logic
- Add `total_trust_count = len(all_trusts)` to context

In `downloads.html`, restructure into 3 sections:

**Section 1: Global Live Exports** (always available, DB-based)
```html
<h2>Live Data Exports</h2>
<div class="export-grid">
  <div class="export-card">
    <h3>All Funds</h3>
    <p>Current fund status for all ~7,000 ETF funds across all trusts.</p>
    <a href="/downloads/export/funds" class="btn">Download CSV</a>
  </div>
  <div class="export-card">
    <h3>All Filings</h3>
    <p>Complete filing history with fund extractions across all trusts.</p>
    <a href="/downloads/export/filings" class="btn">Download CSV</a>
  </div>
</div>
```

**Section 2: Per-Trust Data** (search + accordion)
- Search input: `<input id="trustSearch" placeholder="Search trust name..." oninput="filterTrusts(this.value)">`
- For each trust in `all_trusts`: render a collapsible `<details>` element showing:
  - DB export buttons: "Fund Status CSV" (`/downloads/export/trust/{trust.id}/filings`)
  - Pipeline files from `trust_files` matching this trust name
- Add JS function `filterTrusts(q)` that shows/hides `<details>` elements based on search text
- Show count: "{{ total_trust_count }} trusts"

**Section 3: Other Files**
- Summary Excel files from `summary_files`
- Digest files from `digest_files`

---

**Fix 6 — Page Titles**

In `fund_list.html`: `{% block title %}Fund Search — REX Financial Intelligence Hub{% endblock %}`
In `downloads.html`: `{% block title %}Downloads — REX Financial Intelligence Hub{% endblock %}`

---

**Acceptance Criteria**:
- [ ] Fund list table has sortable column headers using existing sortTable()
- [ ] Funds page shows 100 per page with Prev/Next pagination preserving filter params
- [ ] Trusts with zero fund records are surfaced in an info banner
- [ ] `GET /downloads/export/filings` endpoint works and returns a valid CSV
- [ ] Downloads page has 3 sections: Live Exports, Per-Trust Data (with search), Other Files
- [ ] Both page titles updated to include "REX Financial Intelligence Hub"

---

## Status: DONE

## Log:
- 0ed97f3: feat: add sortable columns, pagination, and missing trusts diagnostic to funds page
- 6088d32: feat: add all-filings export endpoint and restructure downloads page into 3 sections
