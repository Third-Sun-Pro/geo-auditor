"""Tests for report.py — score helpers and HTML report generation."""

import pytest
from report import get_score_class, get_score_icon, generate_report_html, _build_rec_tracking_html, _build_context_badges


# ---------------------------------------------------------------------------
# Score helper tests
# ---------------------------------------------------------------------------

def test_score_class_excellent():
    assert get_score_class(9) == "score-3"
    assert get_score_class(12) == "score-3"


def test_score_class_moderate():
    assert get_score_class(5) == "score-2"
    assert get_score_class(8) == "score-2"


def test_score_class_weak():
    assert get_score_class(2) == "score-1"
    assert get_score_class(4) == "score-1"


def test_score_class_zero():
    assert get_score_class(0) == "score-0"
    assert get_score_class(1) == "score-0"


def test_score_icon_check():
    assert "10003" in get_score_icon(9)  # checkmark


def test_score_icon_warning():
    assert "9888" in get_score_icon(5)  # warning


def test_score_icon_x():
    assert "10007" in get_score_icon(1)  # X mark


# ---------------------------------------------------------------------------
# Report HTML generation tests
# ---------------------------------------------------------------------------

def test_report_contains_client_name(sample_form_data):
    html = generate_report_html(sample_form_data)
    assert "Test Coffee Shop" in html


def test_report_contains_visibility_score(sample_form_data):
    html = generate_report_html(sample_form_data)
    # 6 + 9 = 15 total, 2 queries * 12 = 24 max
    assert "15" in html and "24" in html


def test_report_contains_query_rows(sample_form_data):
    html = generate_report_html(sample_form_data)
    assert "best coffee Salt Lake City" in html
    assert "Test Coffee Shop reviews" in html


def test_report_contains_platform_cards(sample_form_data):
    html = generate_report_html(sample_form_data)
    assert "ChatGPT (OpenAI)" in html
    assert "Perplexity AI" in html


def test_report_contains_recommendations(sample_form_data):
    html = generate_report_html(sample_form_data)
    assert "Improve Local Visibility" in html
    assert "HIGH PRIORITY" in html


def test_report_contains_competitors(sample_form_data):
    html = generate_report_html(sample_form_data)
    assert "Bean Bros" in html
    assert "Local roasting" in html


def test_report_empty_queries():
    """Report should handle empty queries gracefully."""
    html = generate_report_html({
        "client": {"name": "Empty Test"},
        "queries": [],
        "platforms": {},
    })
    assert "Empty Test" in html
    assert "0" in html  # Score should show zero


def test_report_has_css_and_structure(sample_form_data):
    """Report should have proper HTML structure for PDF."""
    html = generate_report_html(sample_form_data)
    assert "<!DOCTYPE html>" in html
    assert "Poppins" in html  # Google Font
    assert "gradient-footer" in html
    assert "@media print" in html


# ---------------------------------------------------------------------------
# Recommendation tracking HTML tests
# ---------------------------------------------------------------------------


def test_rec_tracking_html_renders_statuses():
    """Tracking HTML should render each status with correct label."""
    comparison = {
        "recommendation_tracking": [
            {"title": "Fix Local SEO", "status": "improved", "detail": "Improved by 4 points", "matched_queries": ["best coffee SLC"], "priority": "high", "actions": []},
            {"title": "Add FAQ", "status": "no_change", "detail": "Unchanged", "matched_queries": ["what is small batch"], "priority": "medium", "actions": []},
            {"title": "Social Media", "status": "unmatched", "detail": "General", "matched_queries": [], "priority": "low", "actions": []},
        ]
    }
    html = _build_rec_tracking_html(comparison)
    assert "Fix Local SEO" in html
    assert "Improved" in html
    assert "No Change" in html
    assert "General" in html
    assert "Previous Recommendation Status" in html


def test_rec_tracking_html_empty():
    """No tracking data should return empty string."""
    assert _build_rec_tracking_html({}) == ""
    assert _build_rec_tracking_html({"recommendation_tracking": []}) == ""


# ---------------------------------------------------------------------------
# Context badges (position + sentiment) tests
# ---------------------------------------------------------------------------


def test_context_badges_first_pick():
    """Position 1 should show '#1 pick' badge."""
    details = {
        "chatgpt": {"score": 3, "position": 1, "list_size": 5, "sentiment": "recommended"},
        "claude": {"score": 2, "position": 3, "list_size": 5, "sentiment": "positive"},
    }
    html = _build_context_badges(details)
    assert "#1 pick" in html
    assert "Recommended" in html


def test_context_badges_mid_position():
    """Mid-list position should show position number."""
    details = {
        "chatgpt": {"score": 2, "position": 4, "list_size": 8, "sentiment": "neutral"},
    }
    html = _build_context_badges(details)
    assert "#4/8" in html
    assert "Neutral" in html


def test_context_badges_no_data():
    """Empty details should return empty string."""
    assert _build_context_badges({}) == ""
    assert _build_context_badges(None) == ""


def test_context_badges_sentiment_only():
    """Sentiment without position should still show sentiment badge."""
    details = {
        "chatgpt": {"score": 3, "sentiment": "positive"},
        "claude": {"score": 2, "sentiment": "positive"},
    }
    html = _build_context_badges(details)
    assert "Positive" in html


def test_context_badges_qualified_sentiment():
    """Qualified/mixed sentiment should show 'Mixed' badge."""
    details = {
        "chatgpt": {"score": 2, "sentiment": "qualified"},
    }
    html = _build_context_badges(details)
    assert "Mixed" in html
