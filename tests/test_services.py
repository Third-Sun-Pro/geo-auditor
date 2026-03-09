"""Tests for services.py — recommendations and key findings (no API calls)."""

import pytest
from services import generate_recommendations, _visibility_level, _generate_key_findings


# ---------------------------------------------------------------------------
# Visibility level
# ---------------------------------------------------------------------------

def test_visibility_excellent():
    assert _visibility_level(75) == "excellent"


def test_visibility_strong():
    assert _visibility_level(55) == "strong"


def test_visibility_moderate():
    assert _visibility_level(35) == "moderate"


def test_visibility_low():
    assert _visibility_level(20) == "low"


def test_visibility_very_low():
    assert _visibility_level(5) == "very low"


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _make_query(query, qtype, score):
    return {"query": query, "type": qtype, "score": score, "details": {}}


def test_local_recommendation_when_weak():
    """Weak local queries should produce a local visibility recommendation."""
    local = [_make_query("coffee near me", "Local", 2)]
    recs = generate_recommendations(
        "Test Shop", [], [], local, [], 30, "ChatGPT", "Gemini"
    )
    titles = [r["title"] for r in recs]
    assert "Improve Local Search Visibility" in titles


def test_no_local_rec_when_strong():
    """Strong local queries should NOT produce a local recommendation."""
    local = [_make_query("coffee near me", "Local", 10)]
    recs = generate_recommendations(
        "Test Shop", [], [], local, [], 80, "ChatGPT", "Gemini"
    )
    titles = [r["title"] for r in recs]
    assert "Improve Local Search Visibility" not in titles


def test_brand_recommendation_when_weak():
    """Weak brand queries should produce a brand recommendation."""
    brand = [_make_query("Test Shop reviews", "Brand", 3)]
    recs = generate_recommendations(
        "Test Shop", [], brand, [], [], 30, "ChatGPT", "Gemini"
    )
    titles = [r["title"] for r in recs]
    assert "Strengthen Brand Recognition" in titles


def test_info_recommendation_when_weak():
    """Weak info queries should produce a thought leadership recommendation."""
    info = [_make_query("how to brew coffee", "Info", 1), _make_query("latte art tips", "Info", 2)]
    recs = generate_recommendations(
        "Test Shop", [], [], [], info, 30, "ChatGPT", "Gemini"
    )
    titles = [r["title"] for r in recs]
    assert "Build Thought Leadership Content" in titles


def test_platform_recommendation_when_variance():
    """Different best/worst platforms should produce a platform recommendation."""
    recs = generate_recommendations(
        "Test Shop", [], [], [], [], 40, "ChatGPT", "Gemini"
    )
    titles = [r["title"] for r in recs]
    assert "Optimize for Gemini" in titles


def test_no_platform_rec_when_same():
    """Same best/worst platform means no platform-specific recommendation."""
    recs = generate_recommendations(
        "Test Shop", [], [], [], [], 40, "ChatGPT", "ChatGPT"
    )
    titles = [r["title"] for r in recs]
    assert not any("Optimize for" in t for t in titles)


def test_general_recommendation_below_70():
    """Score below 70% should include general discoverability recommendation."""
    recs = generate_recommendations(
        "Test Shop", [], [], [], [], 50, "ChatGPT", "Gemini"
    )
    titles = [r["title"] for r in recs]
    assert "Enhance Overall AI Discoverability" in titles


def test_no_general_rec_above_70():
    """Score at or above 70% should NOT include general recommendation."""
    recs = generate_recommendations(
        "Test Shop", [], [], [], [], 75, "ChatGPT", "Gemini"
    )
    titles = [r["title"] for r in recs]
    assert "Enhance Overall AI Discoverability" not in titles


def test_premium_gets_extra_recommendations():
    """Premium package should include additional recommendations."""
    basic_recs = generate_recommendations(
        "Test Shop", [], [], [], [], 40, "ChatGPT", "Gemini", "basic"
    )
    premium_recs = generate_recommendations(
        "Test Shop", [], [], [], [], 40, "ChatGPT", "Gemini", "premium"
    )
    assert len(premium_recs) > len(basic_recs)
    premium_titles = [r["title"] for r in premium_recs]
    assert "Technical Optimization for AI Crawlers" in premium_titles
    assert "Maintain Content Freshness" in premium_titles
    assert "Strengthen Competitive Positioning" in premium_titles


def test_premium_has_more_actions():
    """Premium local recommendation should have more action items than basic."""
    local = [_make_query("coffee near me", "Local", 2)]
    basic_recs = generate_recommendations(
        "Test Shop", [], [], local, [], 30, "ChatGPT", "Gemini", "basic"
    )
    premium_recs = generate_recommendations(
        "Test Shop", [], [], local, [], 30, "ChatGPT", "Gemini", "premium"
    )
    basic_local = [r for r in basic_recs if r["title"] == "Improve Local Search Visibility"][0]
    premium_local = [r for r in premium_recs if r["title"] == "Improve Local Search Visibility"][0]
    assert len(premium_local["actions"]) > len(basic_local["actions"])


# ---------------------------------------------------------------------------
# Key findings generation
# ---------------------------------------------------------------------------

def _make_detailed_query(query, qtype, score, platform_scores):
    """Create a query result with per-platform details."""
    details = {}
    for platform, pscore in platform_scores.items():
        details[platform] = {"score": pscore}
    return {"query": query, "type": qtype, "score": score, "details": details}


def test_strong_brand_finding():
    brand = [_make_detailed_query("Shop reviews", "Brand", 10, {
        "chatgpt": 3, "claude": 3, "gemini": 2, "perplexity": 2
    })]
    totals = {"chatgpt": 3, "claude": 3, "gemini": 2, "perplexity": 2}
    findings = _generate_key_findings(brand, totals, 3)
    assert any("Strong brand" in f for f in findings)


def test_weak_brand_finding():
    brand = [_make_detailed_query("Shop reviews", "Brand", 2, {
        "chatgpt": 1, "claude": 1, "gemini": 0, "perplexity": 0
    })]
    totals = {"chatgpt": 1, "claude": 1, "gemini": 0, "perplexity": 0}
    findings = _generate_key_findings(brand, totals, 3)
    assert any("Weak brand" in f or "critical" in f for f in findings)


def test_platform_variance_finding():
    results = [_make_detailed_query("test", "Brand", 6, {
        "chatgpt": 3, "claude": 0, "gemini": 3, "perplexity": 0
    })]
    totals = {"chatgpt": 3, "claude": 0, "gemini": 3, "perplexity": 0}
    findings = _generate_key_findings(results, totals, 3)
    assert any("Platform Variance" in f for f in findings)
