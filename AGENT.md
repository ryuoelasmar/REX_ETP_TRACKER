# AGENT: Market-Frontend-Visual
**Task**: TASK-C — Treemap + Issuer + Market Share Frontend
**Branch**: feature/market-frontend-visual
**Status**: DONE

## Progress Reporting
Write timestamped progress to: `.agents/progress/Market-Frontend-Visual.md`

## Your Files (ONLY modify these)
- `webapp/templates/market/treemap.html`
- `webapp/templates/market/issuer.html`
- `webapp/templates/market/share_timeline.html`
- `webapp/templates/market/issuer_detail.html` (NEW — create this)
- `webapp/routers/market.py` (ONLY to add the issuer detail route — be surgical, don't break other routes)

## CRITICAL: Read First
Read all files listed above completely (except issuer_detail.html which doesn't exist yet).
Also read: `webapp/templates/market/base.html` and `webapp/static/css/market.css` to understand styles.
Also read `webapp/routers/market.py` to understand how to add a new route cleanly.

## Context
- Treemap crashes on some categories because "All" allows duplicate tickers + backend A.3 fixes the route
- Issuer errors on category switch fixed by backend A.4; your job is the template
- Market Share page currently shows useless 7-series 24-month spaghetti chart; redesign to issuer-within-category
- Issuer deep dive: new page/route shows one issuer's complete fund list + AUM trend

## TASK C.1 — Treemap: Remove "All Categories" + Add Legend

In `treemap.html`:
1. Update the category dropdown — remove "All" option:
```html
<select class="select-sm" onchange="location.href='/market/treemap?cat='+this.value">
  {% for c in all_categories %}
  <option value="{{ c }}" {% if c == cat %}selected{% endif %}>
    {{ c | replace('Leverage & Inverse - ', 'L&I ') | replace('Income - ', 'Inc ') }}
  </option>
  {% endfor %}
</select>
```
(Remove any option with value="" or "All")

2. Add empty state:
```html
{% if not products %}
<div style="text-align:center; padding:60px; color:#94A3B8;">
  <p style="font-size:1.1rem;">No products found for this category.</p>
  <p style="font-size:0.85rem;">Try selecting a different category.</p>
</div>
{% else %}
<!-- treemap canvas -->
{% endif %}
```

3. Add issuer color legend below treemap:
```html
{% if products %}
<div class="treemap-legend" style="margin-top:16px; display:flex; flex-wrap:wrap; gap:8px;">
  {% set seen_issuers = [] %}
  {% for p in products %}
    {% if p.issuer not in seen_issuers and seen_issuers|length < 8 %}
      {% set _ = seen_issuers.append(p.issuer) %}
    {% endif %}
  {% endfor %}
  <span style="font-size:0.72rem; color:#94A3B8; font-weight:600; text-transform:uppercase; margin-right:4px;">Issuers:</span>
  {% for issuer in seen_issuers %}
  <span class="treemap-legend-item" data-index="{{ loop.index0 }}">
    <span class="treemap-legend-dot"></span>{{ issuer }}
  </span>
  {% endfor %}
</div>
<script>
// Apply same colors as treemap chart
var LEGEND_COLORS = ['#1E40AF','#059669','#7C3AED','#D97706','#0891B2','#E11D48','#65A30D','#9333EA'];
document.querySelectorAll('.treemap-legend-item').forEach(function(el) {
  var idx = parseInt(el.getAttribute('data-index'));
  var dot = el.querySelector('.treemap-legend-dot');
  if (dot) { dot.style.background = LEGEND_COLORS[idx % LEGEND_COLORS.length]; dot.style.display='inline-block'; dot.style.width='10px'; dot.style.height='10px'; dot.style.borderRadius='50%'; dot.style.marginRight='4px'; }
});
</script>
{% endif %}
```

## TASK C.2 — Issuer: Deep Dive Button + Fix Category Display

In `issuer.html`:
1. Add "Deep Dive" button/link to each issuer row in the table:
```html
<td>
  <a href="/market/issuer/detail?issuer={{ issuer.issuer_name|urlencode }}"
     class="btn btn-sm" style="font-size:0.72rem; padding:3px 8px;">
    Deep Dive →
  </a>
</td>
```
Add `<th>Detail</th>` to the table header.

2. Add empty state for when issuers list is empty (backend error guard):
```html
{% if not issuers %}
<div style="padding:40px; text-align:center; color:#94A3B8;">
  No issuer data available for this category.
</div>
{% endif %}
```

## TASK C.2b — New Issuer Detail Page

Add route to `market.py` (be surgical — add only this one route, don't touch other routes):
```python
@router.get("/issuer/detail")
def issuer_detail_view(request: Request, issuer: str = Query(default="")):
    from webapp.services.market_data import get_master_data, data_available
    available = data_available()
    issuer_data = {}
    products = []
    categories = []
    aum_trend = {}

    if available and issuer:
        try:
            master = get_master_data()
            if not master.empty:
                ticker_col = next((c for c in master.columns if c.lower().strip() == "ticker"), "ticker")
                issuer_col = next((c for c in master.columns if c.lower().strip() == "issuer_display"), None)
                aum_col = next((c for c in master.columns if "t_w4.aum" == c.lower().strip()), None) or \
                           next((c for c in master.columns if c.endswith(".aum") and not any(c.endswith(f".aum_{i}") for i in range(1,37))), None)
                cat_col = next((c for c in master.columns if c.lower().strip() == "category_display"), None)
                name_col = next((c for c in master.columns if c.lower().strip() == "fund_name"), None)

                if issuer_col:
                    df = master[master[issuer_col].fillna("").str.strip() == issuer.strip()].copy()
                    if not df.empty:
                        total_aum = float(df[aum_col].fillna(0).sum()) if aum_col else 0

                        # Category breakdown
                        if cat_col and aum_col:
                            cat_grp = df.groupby(cat_col)[aum_col].sum().reset_index()
                            categories = [{"name": r[cat_col], "aum_fmt": _fmt_aum(float(r[aum_col]))}
                                         for _, r in cat_grp.sort_values(aum_col, ascending=False).iterrows()]

                        # Product list
                        products_df = df.sort_values(aum_col, ascending=False) if aum_col else df
                        for _, row in products_df.iterrows():
                            aum_val = float(row.get(aum_col, 0) or 0) if aum_col else 0
                            products.append({
                                "ticker": str(row.get("ticker_clean", row.get(ticker_col, ""))),
                                "fund_name": str(row.get(name_col, "")) if name_col else "",
                                "category": str(row.get(cat_col, "")) if cat_col else "",
                                "aum_fmt": _fmt_aum(aum_val),
                                "is_rex": bool(row.get("is_rex", False)),
                            })

                        is_rex = any(df.get("is_rex", pd.Series(dtype=bool)))

                        issuer_data = {
                            "name": issuer,
                            "total_aum": total_aum,
                            "total_aum_fmt": _fmt_aum(total_aum),
                            "num_products": len(df),
                            "num_categories": len(categories),
                            "is_rex": is_rex,
                        }

                        # 12-month AUM trend
                        months_labels = []
                        months_values = []
                        from datetime import datetime
                        now = datetime.now()
                        for i in range(12, -1, -1):
                            col_name = f"t_w4.aum_{i}" if i > 0 else aum_col
                            if col_name and col_name in df.columns:
                                val = float(df[col_name].fillna(0).sum())
                                from dateutil.relativedelta import relativedelta
                                dt = now - relativedelta(months=i)
                                months_labels.append(dt.strftime("%b %Y"))
                                months_values.append(round(val, 2))
                        aum_trend = {"labels": months_labels, "values": months_values}
        except Exception as e:
            log.error("Issuer detail error: %s", e)

    return templates.TemplateResponse("market/issuer_detail.html", {
        "request": request,
        "active_tab": "issuer",
        "available": available,
        "issuer": issuer,
        "issuer_data": issuer_data,
        "products": products,
        "categories": categories,
        "aum_trend": aum_trend,
        "data_as_of": "",
    })
```

Note: You'll need to import `_fmt_aum` from market_data or define a local helper. Check what's available in `market.py` imports. Also add `from webapp.services.market_data import svc` if needed.

Create `webapp/templates/market/issuer_detail.html`:
```html
{% set active_tab = 'issuer' %}
{% extends "market/base.html" %}

{% block title %}{{ issuer }} — Issuer Detail — REX Financial Intelligence Hub{% endblock %}

{% block market_content %}
{% if not available %}
<div class="alert alert-info">Market data not available. Upload The Dashboard.xlsx via Admin panel.</div>
{% elif not issuer_data %}
<div class="alert alert-warning">Issuer "{{ issuer }}" not found in current data.</div>
{% else %}

<!-- Header -->
<div style="display:flex; align-items:center; gap:16px; margin-bottom:24px; flex-wrap:wrap;">
  <div>
    <h2 class="section-title" style="margin-bottom:4px;">{{ issuer_data.name }}</h2>
    {% if issuer_data.is_rex %}<span style="color:#1E40AF; font-size:0.75rem; font-weight:700; background:#EFF6FF; padding:2px 10px; border-radius:20px;">REX ISSUER</span>{% endif %}
  </div>
  <div style="margin-left:auto; display:flex; gap:20px; flex-wrap:wrap;">
    <div style="text-align:center;">
      <div style="font-size:1.4rem; font-weight:800; color:#0F172A;">{{ issuer_data.total_aum_fmt }}</div>
      <div style="font-size:0.7rem; color:#94A3B8; text-transform:uppercase;">Total AUM</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:1.4rem; font-weight:800; color:#0F172A;">{{ issuer_data.num_products }}</div>
      <div style="font-size:0.7rem; color:#94A3B8; text-transform:uppercase;">Products</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:1.4rem; font-weight:800; color:#0F172A;">{{ issuer_data.num_categories }}</div>
      <div style="font-size:0.7rem; color:#94A3B8; text-transform:uppercase;">Categories</div>
    </div>
  </div>
</div>

<div class="charts-row" style="margin-bottom:24px;">
  <!-- AUM Trend -->
  {% if aum_trend.labels %}
  <div class="chart-box">
    <div class="chart-title">AUM Trend — Last 12 Months</div>
    <canvas id="issuerTrendChart" height="180"></canvas>
  </div>
  {% endif %}

  <!-- Categories breakdown -->
  {% if categories %}
  <div class="chart-box">
    <div class="chart-title">AUM by Category</div>
    <table class="data-table" style="font-size:0.82rem;">
      <thead><tr><th>Category</th><th>AUM</th></tr></thead>
      <tbody>
        {% for c in categories %}
        <tr>
          <td>{{ c.name | replace('Leverage & Inverse - ', 'L&I ') | replace('Income - ', 'Inc ') }}</td>
          <td class="text-mono">{{ c.aum_fmt }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}
</div>

<!-- Product List -->
<div class="chart-box">
  <div class="chart-title">All Products ({{ products|length }} funds)</div>
  {% if products %}
  <div class="table-scroll-wrap">
    <table class="data-table" id="issuerProductsTable">
      <thead>
        <tr>
          <th onclick="sortTable('issuerProductsTable',0)">Ticker</th>
          <th onclick="sortTable('issuerProductsTable',1)">Fund Name</th>
          <th onclick="sortTable('issuerProductsTable',2)">Category</th>
          <th onclick="sortTable('issuerProductsTable',3)">AUM</th>
          <th>REX</th>
        </tr>
      </thead>
      <tbody>
        {% for p in products %}
        <tr class="{{ 'rex-highlight' if p.is_rex else '' }}">
          <td class="text-mono">{{ p.ticker }}</td>
          <td style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{{ p.fund_name }}</td>
          <td style="font-size:0.78rem;">{{ p.category | replace('Leverage & Inverse - ','L&I ') | replace('Income - ','Inc ') }}</td>
          <td class="text-mono">{{ p.aum_fmt }}</td>
          <td>{% if p.is_rex %}<span style="color:#1E40AF;font-weight:700;font-size:0.75rem;">REX</span>{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div style="padding:20px; text-align:center; color:#94A3B8;">No products found.</div>
  {% endif %}
</div>

{% endif %}
{% endblock %}

{% block market_scripts %}
{% if aum_trend.labels %}
<script>
var trendData = {
  labels: {{ aum_trend.labels | tojson }},
  values: {{ aum_trend.values | tojson }}
};
if (trendData.labels.length > 0) {
  MarketCharts.renderLineChart('issuerTrendChart', {
    labels: trendData.labels,
    datasets: [{
      label: '{{ issuer }} AUM ($M)',
      data: trendData.values,
      borderColor: '#1E40AF',
      backgroundColor: 'rgba(30,64,175,0.1)',
      fill: true,
    }]
  });
}
</script>
{% endif %}
{% endblock %}
```

## TASK C.3 — Market Share: Issuer Within Category

Completely redesign `share_timeline.html`. The backend (Agent A) provides `share_data` dict with `issuers` and `trend`.

```html
{% set active_tab = 'share' %}
{% extends "market/base.html" %}

{% block title %}Issuer Market Share — REX Financial Intelligence Hub{% endblock %}

{% block market_content %}
<h2 class="section-title">Issuer Market Share</h2>

<!-- Category Selector -->
<div style="margin-bottom:20px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
  <label style="font-size:0.8rem; font-weight:600; color:#475569;">Category:</label>
  <select class="select-sm" onchange="location.href='/market/share?cat='+this.value" style="min-width:250px;">
    {% for c in all_categories %}
    <option value="{{ c }}" {% if c == cat %}selected{% endif %}>
      {{ c | replace('Leverage & Inverse - ','L&I ') | replace('Income - ','Inc ') }}
    </option>
    {% endfor %}
  </select>
  {% if data_as_of %}<span style="font-size:0.72rem; color:#94A3B8;">Data as of {{ data_as_of }}</span>{% endif %}
</div>

{% if not available %}
<div class="alert alert-info">Market data not available.</div>
{% elif not share_data or not share_data.get('issuers') %}
<div class="alert alert-warning">No issuer data for this category.</div>
{% else %}

<!-- KPI Bar -->
<div style="display:flex; gap:24px; margin-bottom:20px; flex-wrap:wrap;">
  <div>
    <span style="font-size:1.2rem; font-weight:800;">{{ share_data.total_aum_fmt }}</span>
    <span style="font-size:0.72rem; color:#94A3B8; text-transform:uppercase; margin-left:6px;">Total AUM</span>
  </div>
  <div>
    <span style="font-size:1.2rem; font-weight:800;">{{ share_data.issuers|length }}</span>
    <span style="font-size:0.72rem; color:#94A3B8; text-transform:uppercase; margin-left:6px;">Issuers</span>
  </div>
</div>

<div class="charts-row">
  <!-- Donut Chart -->
  <div class="chart-box">
    <div class="chart-title">Share by Issuer (Top 10 by AUM)</div>
    <canvas id="issuerShareDonut" height="240"></canvas>
  </div>

  <!-- 12-month Trend -->
  {% if share_data.trend and share_data.trend.months %}
  <div class="chart-box">
    <div class="chart-title">AUM Trend — Top 5 Issuers (12 Months)</div>
    <canvas id="issuerTrendChart" height="240"></canvas>
  </div>
  {% endif %}
</div>

<!-- Bar Chart -->
<div class="chart-box" style="margin-top:16px;">
  <div class="chart-title">AUM by Issuer</div>
  <canvas id="issuerBarChart" height="200"></canvas>
</div>

<!-- Issuer Table -->
<div class="chart-box" style="margin-top:16px;">
  <div class="chart-title">All Issuers in {{ cat | replace('Leverage & Inverse - ','L&I ') | replace('Income - ','Inc ') }}</div>
  <table class="data-table" id="issuerShareTable">
    <thead>
      <tr>
        <th onclick="sortTable('issuerShareTable',0)">#</th>
        <th onclick="sortTable('issuerShareTable',1)">Issuer</th>
        <th onclick="sortTable('issuerShareTable',2)">AUM</th>
        <th onclick="sortTable('issuerShareTable',3)">Share %</th>
        <th onclick="sortTable('issuerShareTable',4)">Products</th>
        <th>Detail</th>
      </tr>
    </thead>
    <tbody>
      {% for issuer in share_data.issuers %}
      <tr class="{{ 'rex-highlight' if issuer.is_rex else '' }}">
        <td style="color:#94A3B8; font-size:0.8rem;">{{ loop.index }}</td>
        <td>
          {{ issuer.name }}
          {% if issuer.is_rex %}<span style="color:#1E40AF;font-size:0.7rem;font-weight:700;margin-left:4px;">REX</span>{% endif %}
        </td>
        <td class="text-mono">{{ issuer.aum_fmt }}</td>
        <td class="text-mono">{{ "%.1f%%"|format(issuer.pct) }}</td>
        <td>{{ issuer.num_products }}</td>
        <td><a href="/market/issuer/detail?issuer={{ issuer.name|urlencode }}" class="btn btn-sm" style="font-size:0.7rem; padding:2px 6px;">→</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endif %}
{% endblock %}

{% block market_scripts %}
{% if share_data and share_data.issuers %}
<script>
var shareIssuers = {{ share_data.issuers | tojson }};
var top10 = shareIssuers.slice(0, 10);

// Donut chart
MarketCharts.renderPieChart('issuerShareDonut', {
  labels: top10.map(function(i){return i.name;}),
  values: top10.map(function(i){return i.aum;})
});

// Bar chart
MarketCharts.renderBarChart('issuerBarChart', {
  labels: top10.map(function(i){return i.name;}),
  values: top10.map(function(i){return i.aum;}),
  isRex: top10.map(function(i){return i.is_rex;})
});

{% if share_data.trend and share_data.trend.months %}
var trendData = {{ share_data.trend | tojson }};
MarketCharts.renderLineChart('issuerTrendChart', {
  labels: trendData.months,
  datasets: trendData.series.map(function(s, idx) {
    var colors = ['#1E40AF','#059669','#D97706','#7C3AED','#E11D48'];
    return {
      label: s.issuer,
      data: s.values,
      borderColor: colors[idx % colors.length],
      backgroundColor: 'transparent',
      fill: false,
      borderWidth: s.is_rex ? 3 : 1.5,
    };
  })
});
{% endif %}
</script>
{% endif %}
{% endblock %}
```

## Commit Convention
```
git add webapp/templates/market/treemap.html webapp/templates/market/issuer.html webapp/templates/market/issuer_detail.html webapp/templates/market/share_timeline.html webapp/routers/market.py
git commit -m "feat: Market frontend C - treemap fix, issuer deep dive, market share redesign as issuer-within-category"
```

## Done Criteria
- [ ] Treemap: no "All Categories" option. Empty state shown if no products.
- [ ] Treemap: color legend below chart shows issuer → color mapping.
- [ ] Issuer page: "Deep Dive →" link on each row.
- [ ] `/market/issuer/detail?issuer=X` loads with products + AUM trend chart.
- [ ] Market Share: shows "Issuer Market Share" title. Donut + bar + table. Category selector works.
- [ ] No JS errors on any of these 3 pages.
