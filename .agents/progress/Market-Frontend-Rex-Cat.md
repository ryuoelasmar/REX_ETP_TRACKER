# Market-Frontend-Rex-Cat Progress

## 2026-02-21 - COMPLETED

### Commits
1. `3c8c1da` - feat: rex.html - suite drill-down, pie chart labels, REX names, ETF/ETN filter
2. `d646877` - feat: market.js - pie chart datalabels, fix applyFilters, add toggleCategory multi-select
3. `0623f79` - feat: category.html - multi-select pills, ETF/ETN filter, fix slicer data-field attrs

### Changes Made

**B.1 - Suite Drill-Down (rex.html)**
- Removed suite visibility checkbox section
- Added clickable suite rows with expand icons
- Added hidden product sub-table rows below each suite row
- Added `toggleSuiteProducts()` JS function for expand/collapse

**B.2 - Pie Chart % Labels (rex.html + market.js)**
- Added ChartDataLabels CDN script in rex.html market_scripts block
- Registered `Chart.register(ChartDataLabels)` before chart creation
- Updated `renderPieChart()` options with datalabels plugin config
- Shows label + % for slices >3%, just % for smaller slices
- Hides labels for slices <2% of total
- Added summary table below pie chart (Suite, AUM, % Share, Products)

**B.3 - REX Suite Names (rex.html)**
- All suite labels now use `suite.rex_name if suite.rex_name else suite.short_name`
- Original name preserved as `title` tooltip attribute

**B.4 - ETF/ETN Filter Buttons (rex.html + category.html)**
- Added `fund_structure` filter bar when backend provides the variable
- Falls back to existing `product_type` filter in rex.html if `fund_structure` not defined
- Category.html preserves `cats` param in filter links

**B.5 - Fix Category View Filters (market.js + category.html)**
- Completely rewrote `applyFilters()` - no longer references nonexistent `categorySelect` DOM element
- Now reads category from `data-category` attribute on `#market-category-page` div
- Reads slicer values from `.slicer-select` elements with `data-field` attributes
- Builds URLSearchParams and reloads page (simple, reliable approach)
- Added `data-field` and `slicer-select` class to select elements in category.html
- Wrapped category.html content in `#market-category-page` div with `data-category` attribute

**B.6 - Category Multi-Select Pills (category.html + market.js)**
- Category pills converted from `<a>` links to `<button>` elements with `onclick="MarketFilters.toggleCategory()"`
- `toggleCategory()` function reads/writes `cats` URL param as comma-separated list
- Falls back to single-select `<a>` pills if `all_categories` template var not provided
- JS-based active state marking from URL when `active_cats` not in template context
