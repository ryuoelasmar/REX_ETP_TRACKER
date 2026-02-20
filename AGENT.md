# AGENT: Screener-Admin
**Task**: TASK-C — Screener Data Path Fix + Admin Score Data Removal
**Branch**: feature/screener-admin
**Status**: DONE

## Progress Reporting
Write timestamped progress to: `.agents/progress/Screener-Admin.md`
Format: `## [HH:MM] Task description` then bullet details.

## Your Files
- `screener/config.py`
- `webapp/routers/admin.py`
- `webapp/templates/admin.html`

## CRITICAL: Read These First
Read ALL of these before touching anything:
- `screener/config.py`
- `screener/data_loader.py`
- `webapp/routers/admin.py`
- `webapp/templates/admin.html`
- `webapp/services/screener_3x_cache.py`

## Fix 1: screener/config.py — Auto-detect Data Path

The current DATA_FILE points to `data/SCREENER/data.xlsx` which is gitignored and not present on Render. Change it to auto-detect the new OneDrive master file.

Replace the DATA_FILE line with:
```python
_LOCAL_DATA = Path(r"C:\Users\RyuEl-Asmar\REX Financial LLC\REX Financial LLC - Rex Financial LLC\Product Development\MasterFiles\MASTER Data\The Dashboard.xlsx")
_LEGACY_DATA = PROJECT_ROOT / "data" / "SCREENER" / "data.xlsx"
DATA_FILE = _LOCAL_DATA if _LOCAL_DATA.exists() else _LEGACY_DATA
```

IMPORTANT: The new master file has sheets named `stock_data` and `etp_data` — check `screener/data_loader.py` to confirm what sheet names it reads. If data_loader.py reads `etp_data` and the new file has `etp_data`, no change needed to data_loader.py. If data_loader reads a different name, update data_loader.py to match.

After this fix, `screener_3x_cache.py`'s `warm_cache()` at startup will auto-load data from the OneDrive file and compute the cache automatically. The screener will never show "no data" when running locally.

## Fix 2: admin.py — Remove Screener Score Data Route

In `webapp/routers/admin.py`:

1. Find and REMOVE the `POST /admin/screener/rescore` route entirely (search for `@router.post` with "rescore" or "score" in the path)
2. Remove `screener_data_available` from the GET `/admin/` template context dict
3. Remove any imports that are ONLY used by the removed rescore route (check if `from screener.config import DATA_FILE as SCREENER_DATA_FILE` is used elsewhere — if only for rescore, remove it)

Be careful: keep ALL other admin routes intact:
- GET `/admin/` (dashboard)
- POST `/admin/trusts/approve`
- POST `/admin/trusts/reject`
- POST `/admin/subscribers/approve`
- POST `/admin/subscribers/reject`
- POST `/admin/digest/send`
- GET `/admin/ticker-qc` (if exists)

## Fix 3: admin.html — Remove Score Data UI Section

In `webapp/templates/admin.html`, find and remove the "Launch Screener" / "Score Data" section. This is approximately a block that contains:
- A heading like "Score Data" or "Launch Screener"
- A form with a submit button that posts to `/admin/screener/rescore`
- Any associated flash message blocks for `?screener=` parameter

Remove the entire section but keep all other admin sections:
- Trust Request Approvals
- Digest Subscriber Approvals
- Email Digest
- Ticker QC / AI Analysis Status

Also remove any `{% if screener_data_available %}` conditionals related to the removed section.

## Verification
After making changes, verify:
1. `python -c "from screener.config import DATA_FILE; print(DATA_FILE, DATA_FILE.exists())"` — should show the OneDrive path and True (if on the local machine)
2. `python -c "from webapp.routers.admin import router; print('admin ok')"` — should import without errors
3. No references to `screener/rescore` remain in admin.py or admin.html

## Commit Convention
```
git add screener/config.py webapp/routers/admin.py webapp/templates/admin.html
git commit -m "fix: Screener auto-loads from OneDrive master file; remove admin Score Data section"
```

## Done Criteria
- [x] screener/config.py auto-detects OneDrive path, falls back to legacy
- [x] `/admin/` loads without errors (no screener_data_available reference)
- [x] Score Data section completely gone from admin.html
- [x] No POST /admin/screener/rescore route in admin.py
- [x] Screener will auto-load on server startup (warm_cache in screener_3x_cache.py)

## Log
- All three fixes implemented in prior commits (5f93895, 1f10ae3, 7e71aed, 24afa32)
- Verification passed: DATA_FILE resolves to OneDrive path (exists=True), admin router imports clean, no rescore references remain
