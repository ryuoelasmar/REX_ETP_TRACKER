# Agent: ScreenerFix
# Branch: feature/screener-cache-fix
# Worktree: .worktrees/screenerfix
## Your Files (ONLY touch these)
- webapp/services/screener_3x_cache.py (EDIT)
- webapp/routers/screener.py (EDIT)

## Shared Files (append-only - never remove existing code)
- webapp/main.py (TASK-001 adds market router include, TASK-002 adds startup event. Append only, do not rewrite existing includes.)
- webapp/templates/base.html (TASK-001 adds Market nav link. Append to nav section only.)
- webapp/static/css/style.css (TASK-003 may add loading skeleton styles. Append only.)

## Task: TASK-002
### Screener Cache Persistence Fix

Fix 'No Bloomberg Data' on Render by adding disk-based cache persistence, startup pre-warming, and a 'Data is loading...' message when cache is warming up.

**Acceptance Criteria**:
- Analysis results persisted to data/SCREENER/cache.pkl after computation
- Disk cache loaded on startup before recomputing from scratch
- Template shows 'Data is loading...' instead of 'No Bloomberg Data' when cache is warming
- Startup event pre-warms the screener cache


## Status: DONE

## Log:
- Added disk persistence via pickle to data/SCREENER/cache.pkl
- Added is_warming() state flag and warm_cache() function
- Startup lifespan event pre-warms cache in background thread
- All screener routes pass cache_warming flag to templates
- Templates show "Data is loading..." instead of "No Bloomberg Data" during warm-up
- Commit: ac02048
