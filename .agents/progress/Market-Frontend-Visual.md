# Market-Frontend-Visual Progress

## Status: DONE

## Commits
- 43d3fde feat: treemap - remove All Categories option, add empty state and issuer legend
- af3db2d feat: issuer page - add Deep Dive link and empty state guard
- fa398c1 feat: add issuer detail route /market/issuer/detail
- d0dede4 feat: create issuer detail template with products, AUM trend, categories
- 2592956 feat: redesign market share page as issuer-within-category with donut, bar, trend charts

## Changes Summary

### C.1 - Treemap (treemap.html)
- Removed All Categories option from dropdown
- Added empty state when no products found
- Added issuer color legend below treemap chart (up to 8 issuers)

### C.2 - Issuer (issuer.html)
- Added Deep Dive link column to issuer table
- Added empty state guard when summary exists but issuers list is empty

### C.2b - Issuer Detail (market.py + issuer_detail.html)
- New route: GET /market/issuer/detail?issuer=X
- New template showing: header with KPIs, AUM trend chart, category breakdown table, full product list
- Supports REX highlighting

### C.3 - Market Share (share_timeline.html)
- Complete redesign from spaghetti timeline to issuer-within-category view
- Category selector dropdown, KPI bar, donut chart, bar chart, trend chart, issuer table
