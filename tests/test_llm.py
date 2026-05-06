"""Tests for llm.py — response scoring and retry logic (no API calls)."""

import pytest
from unittest.mock import patch, MagicMock
import httpx
import openai
import anthropic as anthropic_lib
from google.api_core import exceptions as google_exceptions

from llm import analyze_response, _with_retry, _detect_namesake_collision, _error_result


def test_error_result_flagged_as_errored():
    """_error_result must set errored=True so scoring can distinguish from 'not mentioned'."""
    r = _error_result("429 quota exhausted")
    assert r["errored"] is True
    assert r["score"] == 0
    assert "429" in r["finding"]


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
# Namesake collision detection
# ---------------------------------------------------------------------------

def test_namesake_collision_detects_different_state_by_name():
    """Response explicitly says the company is based in a different state."""
    response = (
        "Retirement Planning Associates, Inc., based in Winter Springs, Florida, "
        "specializes in retirement planning for Florida educational employees."
    )
    assert _detect_namesake_collision(
        response, "Retirement Planning Associates Inc.", "Westlake Village, CA"
    ) is True


def test_namesake_collision_detects_different_state_by_code():
    """Response uses a 2-letter state code after a comma in an address."""
    response = "Sunrise Property Advisors, based in Miami, FL, provides excellent service."
    assert _detect_namesake_collision(
        response, "Sunrise Property Advisors", "Seattle, WA"
    ) is True


def test_namesake_collision_ignores_matching_state():
    """Response mentions the client's state — not a collision."""
    response = (
        "Retirement Planning Associates Inc. is located in Westlake Village, California, "
        "and has helped local clients for years."
    )
    assert _detect_namesake_collision(
        response, "Retirement Planning Associates Inc.", "Westlake Village, CA"
    ) is False


def test_namesake_collision_returns_false_when_no_location_in_response():
    """No location signal in the response — can't determine, don't flag."""
    response = "Retirement Planning Associates Inc. is a financial planning firm."
    assert _detect_namesake_collision(
        response, "Retirement Planning Associates Inc.", "Westlake Village, CA"
    ) is False


def test_namesake_collision_returns_false_when_name_not_mentioned():
    """If the name isn't in the response, there's nothing to collide with."""
    response = "Some firm in Florida helps retirees."
    assert _detect_namesake_collision(
        response, "Retirement Planning Associates Inc.", "Westlake Village, CA"
    ) is False


def test_namesake_collision_returns_false_when_client_location_missing():
    """No client location — we can't compare, so don't flag."""
    response = "Acme Co, based in Miami, FL, provides excellent service."
    assert _detect_namesake_collision(response, "Acme Co", "") is False
    assert _detect_namesake_collision(response, "Acme Co", None) is False


def test_namesake_collision_returns_false_when_both_states_mentioned():
    """Response mentions the client's state alongside another — plausibly still the client."""
    response = (
        "Acme Co has offices in Seattle, Washington, and also a satellite branch in Miami, Florida."
    )
    assert _detect_namesake_collision(
        response, "Acme Co", "Seattle, WA"
    ) is False


def test_namesake_collision_scoring_forces_zero():
    """When analyze_response detects a collision, score drops to 0."""
    response = (
        "Retirement Planning Associates, Inc., based in Winter Springs, Florida, "
        "specializes in retirement planning for Florida educational employees. "
        "Retirement Planning Associates Inc. has been serving clients since 2001."
    )
    result = analyze_response(
        response,
        "Retirement Planning Associates Inc.",
        "https://rpa2000.com",
        client_location="Westlake Village, CA",
    )
    assert result["score"] == 0
    assert result.get("namesake_collision") is True
    assert "namesake" in result["finding"].lower()


def test_namesake_collision_absent_when_location_matches():
    """When the response mentions the client's state, score is unaffected by namesake logic."""
    response = "Retirement Planning Associates Inc. is based in Westlake Village, California."
    result = analyze_response(
        response,
        "Retirement Planning Associates Inc.",
        "https://rpa2000.com",
        client_location="Westlake Village, CA",
    )
    assert result["score"] >= 2
    assert result.get("namesake_collision") is False


def test_namesake_collision_backwards_compatible_without_location():
    """Existing callers that don't pass client_location still work."""
    result = analyze_response(
        "Third Sun Productions is a web design agency.",
        "Third Sun Productions",
        "https://thirdsun.com",
    )
    assert result["score"] >= 2
    # Should not flag collision without location context
    assert result.get("namesake_collision") in (False, None)


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


@patch("llm.time.sleep")
def test_retry_works_for_gemini_503_unavailable(mock_sleep):
    """Google ServiceUnavailable (503) should trigger retry — API can briefly fail under load."""
    call_count = {"n": 0}

    def gemini_unavailable():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise google_exceptions.ServiceUnavailable("503 Service unavailable")
        return "gemini response"

    result = _with_retry(gemini_unavailable)
    assert result == "gemini response"
    assert call_count["n"] == 2


@patch("llm.time.sleep")
def test_retry_works_for_openai_500(mock_sleep):
    """OpenAI InternalServerError (5xx) should trigger retry."""
    call_count = {"n": 0}

    def openai_500():
        call_count["n"] += 1
        if call_count["n"] < 2:
            mock_response = httpx.Response(500, request=httpx.Request("POST", "https://api.openai.com"))
            raise openai.InternalServerError(message="Server error", response=mock_response, body=None)
        return "openai response"

    result = _with_retry(openai_500)
    assert result == "openai response"
    assert call_count["n"] == 2
