"""LLM integration — unified query runner and response scoring."""

from config import (
    openai_client, anthropic_client, gemini_model, perplexity_client,
    CHATGPT_MODEL, CLAUDE_MODEL, PERPLEXITY_MODEL,
)


# ---------------------------------------------------------------------------
# Response analysis (scoring)
# ---------------------------------------------------------------------------

# Generic business suffixes — not distinctive enough for partial name matching
GENERIC_SUFFIXES = {
    'inc', 'llc', 'corp', 'corporation', 'company', 'co', 'ltd',
    'associates', 'group', 'services', 'solutions', 'consulting',
    'partners', 'agency', 'enterprises', 'firm', 'professionals',
    'advisors', 'specialists', 'international', 'national', 'global',
}


def _check_proximity(positions, min_unique_words=2, window_size=8):
    """Check if min_unique_words different words appear within window_size tokens.

    positions: list of (token_index, word) tuples
    Returns True if enough distinct words cluster together.
    """
    if len(set(w for _, w in positions)) < min_unique_words:
        return False
    positions_sorted = sorted(positions, key=lambda x: x[0])
    for i in range(len(positions_sorted)):
        window_words = set()
        for j in range(i, len(positions_sorted)):
            if positions_sorted[j][0] - positions_sorted[i][0] <= window_size:
                window_words.add(positions_sorted[j][1])
                if len(window_words) >= min_unique_words:
                    return True
            else:
                break
    return False


def analyze_response(answer, client_name, client_website):
    """Score an AI response for client mentions. Returns 0-3 points."""
    score = 0
    mentions = []

    name_lower = client_name.lower()
    name_words = [w for w in name_lower.split() if len(w) > 2]

    name_variations = [
        name_lower,
        name_lower.replace(" ", ""),
        name_lower.replace("-", ""),
        name_lower.replace("-", " "),
    ]

    domain = client_website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    domain_name = domain.split(".")[0].lower()

    answer_lower = answer.lower()


    name_found = False

    # Exact name match
    if any(name in answer_lower for name in name_variations):
        score += 2
        mentions.append("Named in response")
        name_found = True
    # Partial name match — capitalization + proximity check
    # When AI platforms reference a business, they capitalize the name.
    # Generic topic mentions ("retirement planning") stay lowercase.
    elif len(name_words) >= 2:
        distinctive_words = [w for w in name_words if w not in GENERIC_SUFFIXES]
        # Need at least 2 distinctive words, or all of them if fewer
        min_required = max(2, len(distinctive_words))

        # Tokenize original response (preserving case) for capitalization check
        # Only count mid-sentence capitalization (proper nouns), not sentence starters
        answer_tokens = answer.split()
        cap_positions = []
        for i, token in enumerate(answer_tokens):
            clean = token.strip('.,;:!?()[]"\'-\u2013\u2014/*').lower()
            if clean in name_words and len(token) > 0 and token[0].isupper():
                # Skip words capitalized only because they start a sentence
                is_sentence_start = (i == 0) or (
                    i > 0 and len(answer_tokens[i - 1]) > 0
                    and answer_tokens[i - 1][-1] in '.!?'
                )
                if not is_sentence_start:
                    cap_positions.append((i, clean))

        if _check_proximity(cap_positions, min_unique_words=min_required, window_size=8):
            score += 1
            mentions.append("Partial name match")
            name_found = True
        else:
            pass

    # Domain name mention
    if domain_name and len(domain_name) > 3 and domain_name in answer_lower:
        score += 1
        mentions.append("Domain name mentioned")

    # Full URL citation
    if domain.lower() in answer_lower:
        score += 1
        mentions.append("Website URL cited")

    # Prominent placement (first 500 chars)
    if name_found:
        first_para = answer_lower[:500]
        if any(name in first_para for name in name_variations):
            score += 1
            mentions.append("Featured prominently")

    score = min(score, 3)

    if score >= 3:
        finding = "Strong presence - named and cited"
    elif score >= 2:
        finding = "Mentioned in response"
    elif score >= 1:
        finding = "Briefly referenced"
    else:
        finding = "Not mentioned in response"


    return {
        "score": score,
        "finding": finding,
        "mentions": mentions,
        "response_preview": answer[:300] + "..." if len(answer) > 300 else answer
    }


# ---------------------------------------------------------------------------
# Platform query runners
# ---------------------------------------------------------------------------

def _error_result(message):
    return {"error": message, "score": 0, "finding": message}


def query_platform(platform, query_text, client_name, client_website):
    """Run a query on the specified platform and score the response.

    platform: one of "chatgpt", "claude", "gemini", "perplexity"
    Returns dict with score, finding, mentions, response_preview.
    """
    runners = {
        "chatgpt": _run_chatgpt,
        "claude": _run_claude,
        "gemini": _run_gemini,
        "perplexity": _run_perplexity,
    }
    runner = runners.get(platform)
    if not runner:
        return _error_result(f"Unknown platform: {platform}")
    return runner(query_text, client_name, client_website)


def _run_chatgpt(query, client_name, client_website):
    if not openai_client:
        return _error_result("OpenAI API key not configured")
    try:
        response = openai_client.chat.completions.create(
            model=CHATGPT_MODEL,
            messages=[{"role": "user", "content": query}],
            max_tokens=1000,
            temperature=0
        )
        answer = response.choices[0].message.content
        return analyze_response(answer, client_name, client_website)
    except Exception as e:
        return _error_result(f"Error: {e}")


def _run_claude(query, client_name, client_website):
    if not anthropic_client:
        return _error_result("Anthropic API key not configured")
    try:
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            temperature=0,
            messages=[{"role": "user", "content": query}]
        )
        answer = response.content[0].text
        return analyze_response(answer, client_name, client_website)
    except Exception as e:
        return _error_result(f"Error: {e}")


def _run_gemini(query, client_name, client_website):
    if not gemini_model:
        return _error_result("Google API key not configured")
    try:
        response = gemini_model.generate_content(
            query,
            generation_config={"temperature": 0}
        )
        answer = response.text
        return analyze_response(answer, client_name, client_website)
    except Exception as e:
        return _error_result(f"Error: {e}")


def _run_perplexity(query, client_name, client_website):
    if not perplexity_client:
        return _error_result("Perplexity API key not configured")
    try:
        response = perplexity_client.chat.completions.create(
            model=PERPLEXITY_MODEL,
            messages=[{"role": "user", "content": query}],
            max_tokens=1000,
            temperature=0
        )
        answer = response.choices[0].message.content
        return analyze_response(answer, client_name, client_website)
    except Exception as e:
        return _error_result(f"Error: {e}")
