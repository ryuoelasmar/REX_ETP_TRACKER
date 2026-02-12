"""Tests for the ETF Launch Screener module."""
import pytest


# ---------------------------------------------------------------------------
# Data Loading Tests
# ---------------------------------------------------------------------------

def test_data_loading():
    """Test that both sheets load with correct row counts."""
    from screener.data_loader import load_all
    data = load_all()

    assert "stock_data" in data
    assert "etp_data" in data
    assert len(data) == 2  # Only 2 sheets now

    assert len(data["stock_data"]) > 2400
    assert len(data["etp_data"]) > 5000


def test_stock_data_has_required_columns():
    """Test stock_data has the columns needed for scoring."""
    from screener.data_loader import load_stock_data
    df = load_stock_data()

    required = ["Ticker", "Mkt Cap", "Total OI", "Turnover / Traded Value",
                "Volatility 30D", "Short Interest Ratio",
                "GICS Sector", "ticker_clean"]
    for col in required:
        assert col in df.columns, f"Missing column: {col}"


def test_etp_data_has_category_attributes():
    """Test etp_data has all required category attribute columns."""
    from screener.data_loader import load_etp_data
    df = load_etp_data()

    required = [
        "q_category_attributes.map_li_category",
        "q_category_attributes.map_li_subcategory",
        "q_category_attributes.map_li_direction",
        "q_category_attributes.map_li_leverage_amount",
        "q_category_attributes.map_li_underlier",
        "underlier_clean",
        "t_w4.aum",
        "is_rex",
    ]
    for col in required:
        assert col in df.columns, f"Missing column: {col}"

    # REX funds should be derivable from is_rex
    rex = df[df["is_rex"] == True]
    assert len(rex) > 80


# ---------------------------------------------------------------------------
# Scoring Tests
# ---------------------------------------------------------------------------

def test_percentile_scoring():
    """Test that scoring produces valid composite scores (0-100)."""
    from screener.data_loader import load_stock_data
    from screener.scoring import compute_percentile_scores

    df = load_stock_data()
    scored = compute_percentile_scores(df)

    assert "composite_score" in scored.columns
    assert "rank" in scored.columns
    assert scored["composite_score"].min() >= 0
    assert scored["composite_score"].max() <= 100
    assert scored.iloc[0]["composite_score"] >= scored.iloc[-1]["composite_score"]  # sorted desc


def test_threshold_filters():
    """Test that threshold filters produce pass/fail column."""
    from screener.data_loader import load_stock_data, load_etp_data
    from screener.scoring import compute_percentile_scores, derive_rex_benchmarks, apply_threshold_filters

    stock = load_stock_data()
    etp = load_etp_data()

    benchmarks = derive_rex_benchmarks(etp, stock)
    scored = compute_percentile_scores(stock)
    filtered = apply_threshold_filters(scored, benchmarks)

    assert "passes_filters" in filtered.columns
    n_pass = filtered["passes_filters"].sum()
    assert 0 < n_pass < len(filtered)  # Some pass, some don't


def test_competitive_penalty():
    """Test that competitive penalty modifies scores and adds market_signal."""
    from screener.data_loader import load_stock_data, load_etp_data
    from screener.scoring import compute_percentile_scores, apply_competitive_penalty
    from screener.competitive import compute_competitive_density

    stock = load_stock_data()
    etp = load_etp_data()

    scored = compute_percentile_scores(stock)
    density = compute_competitive_density(etp)
    penalized = apply_competitive_penalty(scored, density)

    assert "market_signal" in penalized.columns
    # Some stocks should have penalties applied
    rejected = penalized[penalized["market_signal"] == "Market Rejected"]
    low_traction = penalized[penalized["market_signal"] == "Low Traction"]
    rex_active = penalized[penalized["market_signal"] == "REX Active"]

    # REX has products on many underliers, so at least some should be marked
    assert len(rex_active) > 0 or len(rejected) > 0 or len(low_traction) > 0


# ---------------------------------------------------------------------------
# Competitive Analysis Tests
# ---------------------------------------------------------------------------

def test_competitive_density():
    """Test density with REX vs competitor split."""
    from screener.data_loader import load_etp_data
    from screener.competitive import compute_competitive_density

    etp = load_etp_data()
    density = compute_competitive_density(etp)

    assert len(density) > 100  # At least 100 unique underliers

    # New columns for REX/competitor split
    assert "rex_product_count" in density.columns
    assert "competitor_product_count" in density.columns
    assert "rex_aum" in density.columns
    assert "competitor_aum" in density.columns
    assert "is_rex_active" in density.columns

    # TSLA should have REX products
    tsla = density[density["underlier"] == "TSLA US"]
    assert len(tsla) == 1
    assert tsla.iloc[0]["product_count"] >= 5
    assert tsla.iloc[0]["is_rex_active"] == True


def test_competitive_rex_split():
    """Test that REX products are correctly separated from competitors."""
    from screener.data_loader import load_etp_data
    from screener.competitive import compute_competitive_density

    etp = load_etp_data()
    density = compute_competitive_density(etp)

    # For any underlier, rex_count + competitor_count should equal product_count
    for _, row in density.iterrows():
        assert row["rex_product_count"] + row["competitor_product_count"] == row["product_count"]


def test_market_feedback():
    """Test market feedback assessment for known underliers."""
    from screener.data_loader import load_etp_data
    from screener.competitive import compute_market_feedback

    etp = load_etp_data()

    # TSLA has massive AUM products -> should be VALIDATED
    tsla = compute_market_feedback(etp, "TSLA US")
    assert tsla["verdict"] in ("VALIDATED", "MIXED")
    assert tsla["product_count"] > 0
    assert tsla["total_aum"] > 0

    # An underlier with no products
    fake = compute_market_feedback(etp, "ZZZZZ US")
    assert fake["verdict"] == "NO_PRODUCTS"
    assert fake["product_count"] == 0


def test_fund_flows():
    """Test fund flow aggregation."""
    from screener.data_loader import load_etp_data
    from screener.competitive import compute_fund_flows

    etp = load_etp_data()
    flows = compute_fund_flows(etp)

    assert len(flows) > 0
    assert "underlier" in flows.columns
    assert "flow_1m" in flows.columns
    assert "flow_direction" in flows.columns


# ---------------------------------------------------------------------------
# Candidate Evaluation Tests
# ---------------------------------------------------------------------------

def test_candidate_evaluation():
    """Test candidate evaluator with known tickers."""
    from screener.candidate_evaluator import evaluate_candidates

    # SCCO is in stock_data, ZZFAKE is not
    results = evaluate_candidates(["SCCO", "ZZFAKE"])

    assert len(results) == 2

    scco = results[0]
    assert scco["ticker_clean"] == "SCCO"
    assert scco["data_coverage"] == "full"
    assert scco["demand"]["verdict"] in ("HIGH", "MEDIUM", "LOW")
    assert scco["competition"]["verdict"] in ("FIRST_MOVER", "EARLY_STAGE", "COMPETITIVE", "CROWDED")
    assert scco["market_feedback"]["verdict"] in ("VALIDATED", "MIXED", "REJECTED", "NO_PRODUCTS")
    assert scco["filing"]["verdict"] in ("ALREADY_TRADING", "FILED", "NOT_FILED")
    assert scco["verdict"] in ("RECOMMEND", "NEUTRAL", "CAUTION")

    fake = results[1]
    assert fake["ticker_clean"] == "ZZFAKE"
    assert fake["data_coverage"] == "none"
    assert fake["demand"]["verdict"] == "DATA_UNAVAILABLE"


def test_candidate_evaluation_rex_underlier():
    """Test that evaluation correctly identifies REX-filed underliers."""
    from screener.candidate_evaluator import evaluate_candidates

    # TSLA and NVDA have REX products
    results = evaluate_candidates(["TSLA", "NVDA"])

    for r in results:
        assert r["filing"]["verdict"] in ("ALREADY_TRADING", "FILED")
        assert r["competition"]["rex_count"] > 0


# ---------------------------------------------------------------------------
# Filing Match Tests
# ---------------------------------------------------------------------------

def test_filing_match():
    """Test that filing match uses etp_data and pipeline DB."""
    from screener.data_loader import load_stock_data, load_etp_data
    from screener.scoring import compute_percentile_scores
    from screener.filing_match import match_filings, get_rex_underlier_map

    stock = load_stock_data()
    etp = load_etp_data()
    scored = compute_percentile_scores(stock)

    # Verify underlier map works
    und_map = get_rex_underlier_map(etp)
    assert len(und_map) > 20  # REX has 30+ single-stock underliers

    matched = match_filings(scored, etp)
    assert "filing_status" in matched.columns

    # At least some should have REX filings
    rex_filed = matched[matched["filing_status"].str.startswith("REX Filed")]
    assert len(rex_filed) > 0


# ---------------------------------------------------------------------------
# PDF Report Tests
# ---------------------------------------------------------------------------

def test_candidate_pdf_generation():
    """Test that candidate evaluation PDF generates valid bytes."""
    from screener.report_generator import generate_candidate_report

    candidates = [
        {
            "ticker": "SCCO US", "ticker_clean": "SCCO",
            "company_name": "Materials", "data_coverage": "full",
            "demand": {"verdict": "HIGH", "weighted_pctl": 85.0, "metrics": {
                "Mkt Cap": {"value": 170598}, "Total OI": {"value": 245000, "percentile": 92},
                "Turnover / Traded Value": {"value": 1200000000, "percentile": 85},
                "Volatility 30D": {"value": 38.0}, "Short Interest Ratio": {"value": 2.1},
            }},
            "competition": {"verdict": "FIRST_MOVER", "product_count": 0, "competitor_count": 0,
                           "rex_count": 0, "total_aum": 0, "competitor_aum": 0, "rex_aum": 0,
                           "leader": None, "leader_share": 0, "leader_is_rex": False},
            "market_feedback": {"verdict": "NO_PRODUCTS", "product_count": 0, "total_aum": 0,
                               "flow_direction": None, "aum_trend": None, "details": []},
            "filing": {"verdict": "NOT_FILED", "rex_ticker": None, "status": None,
                      "effective_date": None, "latest_form": None},
            "verdict": "RECOMMEND",
            "reason": "Strong demand signal, no competitors. First-mover opportunity.",
        },
    ]

    pdf = generate_candidate_report(candidates)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000
    assert pdf[:5] == b"%PDF-"


def test_rankings_pdf_generation():
    """Test that rankings PDF generates valid bytes."""
    from screener.report_generator import generate_rankings_report

    results = [
        {"ticker": "NVDA US", "sector": "Technology", "composite_score": 89.8,
         "mkt_cap": 4491612, "total_oi_pctl": 99.5, "market_signal": "REX Active",
         "passes_filters": True, "filing_status": "REX Filed - Effective",
         "competitive_density": "Crowded"},
        {"ticker": "AMD US", "sector": "Technology", "composite_score": 89.9,
         "mkt_cap": 413083, "total_oi_pctl": 98.2, "market_signal": None,
         "passes_filters": True, "filing_status": "Not Filed",
         "competitive_density": "Crowded"},
    ]

    pdf = generate_rankings_report(results)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000
    assert pdf[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Web Route Tests (using TestClient)
# ---------------------------------------------------------------------------

def test_screener_page(client):
    """Test that /screener/ returns 200."""
    r = client.get("/screener/")
    assert r.status_code == 200
    assert "Launch Screener" in r.text


def test_screener_rex_funds(client):
    """Test that /screener/rex-funds returns 200."""
    r = client.get("/screener/rex-funds")
    assert r.status_code == 200
    assert "REX Fund Portfolio" in r.text


def test_screener_stock_detail(client):
    """Test that /screener/stock/{ticker} returns 200."""
    r = client.get("/screener/stock/NVDA US")
    assert r.status_code == 200
    assert "NVDA" in r.text
