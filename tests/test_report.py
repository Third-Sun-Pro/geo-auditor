"""Tests for report.py — score helpers and HTML report generation."""

import pytest
from report import get_score_class, get_score_icon, generate_report_html


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
    assert "15/24" in html


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
    assert "0/0" in html


def test_report_has_css_and_structure(sample_form_data):
    """Report should have proper HTML structure for PDF."""
    html = generate_report_html(sample_form_data)
    assert "<!DOCTYPE html>" in html
    assert "Poppins" in html  # Google Font
    assert "gradient-footer" in html
    assert "@media print" in html
