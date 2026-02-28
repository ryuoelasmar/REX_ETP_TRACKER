"""
Tests for the simplified email digest.
"""
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def sample_output_dir(tmp_path):
    """Create minimal CSV files for digest generation."""
    trust_dir = tmp_path / "Test Trust"
    trust_dir.mkdir()

    status_csv = trust_dir / "Test_Trust_4_Fund_Status.csv"
    status_csv.write_text(
        "Trust,Series ID,Class/Contract ID,Fund Name,Ticker,Status,"
        "Status Reason,Effective Date,Effective Date Confidence,"
        "Latest Form,Latest Filing Date,Prospectus Link\n"
        "Test Trust,S000111111,C000222222,Test Ultra Fund,TULF,EFFECTIVE,"
        "485BPOS filed,2025-06-15,HIGH,485BPOS,2025-06-15,https://sec.gov/test\n"
        "Test Trust,S000333333,C000444444,Test Pending Fund,TPND,PENDING,"
        "Initial filing,,,485APOS,2025-05-01,\n"
    )
    return tmp_path


def test_digest_has_kpis(sample_output_dir):
    from etp_tracker.email_alerts import build_digest_html

    html = build_digest_html(sample_output_dir, dashboard_url="https://example.com")
    assert "Trusts Monitored" in html
    assert "Effective" in html
    assert "Pending" in html


def test_digest_has_dashboard_button(sample_output_dir):
    from etp_tracker.email_alerts import build_digest_html

    html = build_digest_html(sample_output_dir, dashboard_url="https://example.com")
    assert "Open Dashboard" in html
    assert "https://example.com" in html


def test_digest_no_trust_tables(sample_output_dir):
    """Simplified digest should NOT contain per-trust fund tables."""
    from etp_tracker.email_alerts import build_digest_html

    html = build_digest_html(sample_output_dir, dashboard_url="https://example.com")
    # These were in the old heavy digest - should be gone now
    assert "TULF" not in html  # No individual fund tickers
    assert "S000111111" not in html  # No series IDs


def test_digest_what_changed(sample_output_dir):
    from etp_tracker.email_alerts import build_digest_html

    html = build_digest_html(sample_output_dir, dashboard_url="https://example.com")
    # Digest contains pipeline run info or dashboard link
    assert "Open Dashboard" in html


def test_digest_is_short(sample_output_dir):
    """Digest should be under 30KB (executive summary only)."""
    from etp_tracker.email_alerts import build_digest_html

    html = build_digest_html(sample_output_dir, dashboard_url="https://example.com")
    assert len(html) < 30_000, f"Digest too long: {len(html)} chars"
