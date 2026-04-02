"""Tests for llm.py — response scoring and retry logic (no API calls)."""

import pytest
from unittest.mock import patch, MagicMock
import httpx
import openai
import anthropic as anthropic_lib
from google.api_core import exceptions as google_exceptions

from llm import analyze_response, _with_retry


def _make_openai_rate_limit_error():
    """Create a realistic OpenAI RateLimitError for testing."""
    mock_response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com"))
    return openai.RateLimitError(message="Rate limited", response=mock_response, body=None)


def _make_openai_auth_error():
    """Create a realistic OpenAI AuthenticationError for testing."""
    mock_response = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com"))
    return openai.AuthenticationError(message="Bad key", response=mock_response, body=None)


def _make_anthropic_rate_limit_error():
    """Create a realistic Anthropic RateLimitError for testing."""
    mock_response = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic_lib.RateLimitError(message="Rate limited", response=mock_response, body=None)


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


# ---------------------------------------------------------------------------
# Position tracking tests
# ---------------------------------------------------------------------------


def test_position_first_in_list():
    """Business listed first should report position 1."""
    result = analyze_response(
        "Here are the best coffee shops:\n\n1. **Publik Coffee** - Great atmosphere\n2. Bean Bros\n3. Java House",
        "Publik Coffee", "https://publikcoffee.com"
    )
    assert result["position"] == 1
    assert result["list_size"] >= 2


def test_position_third_in_list():
    """Business listed third should report position 3."""
    result = analyze_response(
        "Top coffee shops in SLC:\n\n1. **Bean Bros** - Excellent\n2. **Java House** - Classic\n3. **Publik Coffee** - Cozy\n4. **Loki** - Hip",
        "Publik Coffee", "https://publikcoffee.com"
    )
    assert result["position"] == 3


def test_position_only_mention():
    """Business mentioned but not in a list should have position None."""
    result = analyze_response(
        "Publik Coffee Roasters is a well-known coffee roastery based in Salt Lake City.",
        "Publik Coffee Roasters", "https://publikcoffee.com"
    )
    assert result["position"] is None


def test_position_not_mentioned():
    """Business not mentioned should have position None."""
    result = analyze_response(
        "Here are some coffee shops:\n1. Bean Bros\n2. Java House",
        "Publik Coffee", "https://publikcoffee.com"
    )
    assert result["position"] is None


def test_position_markdown_headers():
    """Business listed under markdown headers should detect position."""
    result = analyze_response(
        "## Best Coffee in SLC\n\n**Bean Bros**\nGreat spot.\n\n**Publik Coffee**\nAwesome roasts.\n\n**Java House**\nClassic vibes.",
        "Publik Coffee", "https://publikcoffee.com"
    )
    assert result["position"] == 2


# ---------------------------------------------------------------------------
# Sentiment/framing tests
# ---------------------------------------------------------------------------


def test_sentiment_recommended():
    """Direct recommendation language should detect 'recommended' sentiment."""
    result = analyze_response(
        "I'd highly recommend Publik Coffee Roasters for their excellent small batch roasts.",
        "Publik Coffee Roasters", "https://publikcoffee.com"
    )
    assert result["sentiment"] == "recommended"


def test_sentiment_positive():
    """Positive descriptors without recommendation should detect 'positive'."""
    result = analyze_response(
        "Publik Coffee Roasters is known for their excellent quality and great atmosphere.",
        "Publik Coffee Roasters", "https://publikcoffee.com"
    )
    assert result["sentiment"] == "positive"


def test_sentiment_neutral():
    """Factual mention without positive/negative framing should be 'neutral'."""
    result = analyze_response(
        "Other coffee shops in the area include Publik Coffee Roasters, which is located on 9th and 9th.",
        "Publik Coffee Roasters", "https://publikcoffee.com"
    )
    assert result["sentiment"] == "neutral"


def test_sentiment_not_mentioned():
    """Business not mentioned should have sentiment None."""
    result = analyze_response(
        "Here are some coffee shops: Bean Bros and Java House.",
        "Publik Coffee", "https://publikcoffee.com"
    )
    assert result["sentiment"] is None


def test_sentiment_qualified():
    """Mention with caveats should detect 'qualified'."""
    result = analyze_response(
        "Publik Coffee Roasters has good coffee, however some customers find it overpriced and the service can be slow.",
        "Publik Coffee Roasters", "https://publikcoffee.com"
    )
    assert result["sentiment"] == "qualified"


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


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------

@patch("llm.time.sleep")  # Don't actually wait during tests
def test_retry_succeeds_after_rate_limit(mock_sleep):
    """Should retry and return result after a rate limit error."""
    call_count = {"n": 0}

    def flaky():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _make_openai_rate_limit_error()
        return "success"

    result = _with_retry(flaky)
    assert result == "success"
    assert call_count["n"] == 3
    assert mock_sleep.call_count == 2  # slept twice before 3rd attempt


@patch("llm.time.sleep")
def test_retry_exhausted_raises(mock_sleep):
    """Should raise after all retries are exhausted."""
    def always_limited():
        raise _make_openai_rate_limit_error()

    with pytest.raises(openai.RateLimitError):
        _with_retry(always_limited)
    assert mock_sleep.call_count == 3  # tried 3 retries


@patch("llm.time.sleep")
def test_retry_does_not_catch_other_errors(mock_sleep):
    """Non-rate-limit errors should raise immediately, no retry."""
    call_count = {"n": 0}

    def auth_error():
        call_count["n"] += 1
        raise _make_openai_auth_error()

    with pytest.raises(openai.AuthenticationError):
        _with_retry(auth_error)
    assert call_count["n"] == 1  # no retries
    assert mock_sleep.call_count == 0


@patch("llm.time.sleep")
def test_retry_works_for_gemini_rate_limit(mock_sleep):
    """Google ResourceExhausted (429) should trigger retry."""
    call_count = {"n": 0}

    def gemini_limited():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise google_exceptions.ResourceExhausted("429 Resource exhausted")
        return "gemini response"

    result = _with_retry(gemini_limited)
    assert result == "gemini response"
    assert call_count["n"] == 2


@patch("llm.time.sleep")
def test_retry_works_for_anthropic_rate_limit(mock_sleep):
    """Anthropic RateLimitError should trigger retry."""
    call_count = {"n": 0}

    def claude_limited():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise _make_anthropic_rate_limit_error()
        return "claude response"

    result = _with_retry(claude_limited)
    assert result == "claude response"
    assert call_count["n"] == 2


@patch("llm.time.sleep")
def test_retry_backoff_delays(mock_sleep):
    """Retry delays should follow exponential backoff pattern."""
    def always_limited():
        raise _make_openai_rate_limit_error()

    with pytest.raises(openai.RateLimitError):
        _with_retry(always_limited)

    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [2, 4, 8]
