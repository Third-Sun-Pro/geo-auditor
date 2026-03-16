"""Tests for llm.py — response scoring logic (no API calls)."""

import pytest
from llm import analyze_response


def test_exact_name_match_scores_2():
    """Exact business name match should score at least 2."""
    result = analyze_response(
        "I recommend visiting Third Sun Productions for web design.",
        "Third Sun Productions",
        "https://thirdsun.com"
    )
    assert result["score"] >= 2
    assert "Named in response" in result["mentions"]


def test_no_mention_scores_0():
    """Response with no mention should score 0."""
    result = analyze_response(
        "Here are some great coffee shops in Salt Lake City: Bean Bros, Java House.",
        "Zephyr Plumbing Services",
        "https://zephyrplumbing.com"
    )
    assert result["score"] == 0
    assert result["finding"] == "Not mentioned in response"


def test_domain_mention_scores_1():
    """Mentioning the domain name should add a point."""
    result = analyze_response(
        "You can find more info at thirdsun.com for web design services.",
        "Third Sun Productions",
        "https://thirdsun.com"
    )
    assert result["score"] >= 1
    assert any("URL" in m or "Domain" in m for m in result["mentions"])


def test_prominent_placement_bonus():
    """Name appearing in first 500 chars gets a bonus point."""
    early = "Third Sun Productions is a great choice. " + "x " * 500
    late = "x " * 500 + "Third Sun Productions is mentioned here."

    early_result = analyze_response(early, "Third Sun Productions", "https://thirdsun.com")
    late_result = analyze_response(late, "Third Sun Productions", "https://thirdsun.com")

    assert early_result["score"] >= late_result["score"]


def test_score_capped_at_3():
    """Score should never exceed 3."""
    # Name + domain + URL + prominent = would be 5 without cap
    result = analyze_response(
        "Third Sun Productions at thirdsun.com is amazing. Visit https://thirdsun.com today.",
        "Third Sun Productions",
        "https://thirdsun.com"
    )
    assert result["score"] <= 3


def test_partial_name_match():
    """Multi-word name with 2+ capitalized words mid-sentence should score 1."""
    result = analyze_response(
        "We recommend the Neighborhood House for great community services.",
        "Neighborhood House Association",
        "https://nhautah.org"
    )
    assert result["score"] >= 1
    assert any("Partial" in m for m in result["mentions"])


def test_finding_text_matches_score():
    """Finding text should correspond to the score level."""
    high = analyze_response(
        "Third Sun Productions at thirdsun.com is a top agency.",
        "Third Sun Productions", "https://thirdsun.com"
    )
    assert high["score"] == 3
    assert "Strong presence" in high["finding"]

    zero = analyze_response(
        "Nothing relevant here at all.",
        "Third Sun Productions", "https://thirdsun.com"
    )
    assert zero["score"] == 0
    assert "Not mentioned" in zero["finding"]


def test_response_preview_truncated():
    """Long responses should be truncated in the preview."""
    long_response = "A" * 500
    result = analyze_response(long_response, "Test", "https://test.com")
    assert len(result["response_preview"]) <= 303  # 300 + "..."


def test_case_insensitive_matching():
    """Name matching should be case-insensitive."""
    result = analyze_response(
        "THIRD SUN PRODUCTIONS is a well-known agency.",
        "Third Sun Productions",
        "https://thirdsun.com"
    )
    assert result["score"] >= 2


def test_name_with_hyphens():
    """Hyphenated names should match with/without hyphens."""
    result = analyze_response(
        "Check out eat drink distill for cocktail events.",
        "Eat-Drink-Distill",
        "https://eatdrinkdistill.com"
    )
    assert result["score"] >= 1
