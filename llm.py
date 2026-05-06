"""LLM integration — unified query runner and response scoring."""

import time
import logging

import openai
import anthropic as anthropic_lib
from google.api_core import exceptions as google_exceptions
from google.genai import errors as genai_errors

from config import (
    openai_client, anthropic_client, gemini_client, perplexity_client,
    CHATGPT_MODEL, CLAUDE_MODEL, GEMINI_MODEL, PERPLEXITY_MODEL,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit retry helper
# ---------------------------------------------------------------------------

# Exception types that indicate a rate limit (retry-worthy)
_RATE_LIMIT_ERRORS = (
    openai.RateLimitError,              # OpenAI + Perplexity (uses OpenAI SDK)
    anthropic_lib.RateLimitError,       # Anthropic
    google_exceptions.ResourceExhausted,  # Google Gemini (legacy SDK)
)

# Transient server errors (5xx) — also retry-worthy. Without this, a single 503
# from Gemini silently scores the query as "not mentioned" and tanks the audit.
_TRANSIENT_SERVER_ERRORS = (
    openai.InternalServerError,              # OpenAI + Perplexity 5xx
    anthropic_lib.InternalServerError,       # Anthropic 5xx
    google_exceptions.ServiceUnavailable,    # Google 503 (legacy SDK)
    google_exceptions.InternalServerError,   # Google 500 (legacy SDK)
)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds — exponential backoff


def _is_retryable_error(e):
    """Check if an exception is transient (rate limit or 5xx) and worth retrying."""
    if isinstance(e, _RATE_LIMIT_ERRORS) or isinstance(e, _TRANSIENT_SERVER_ERRORS):
        return True
    # New google.genai SDK: ClientError code 429, ServerError codes 5xx
    if isinstance(e, genai_errors.ClientError) and getattr(e, 'code', 0) == 429:
        return True
    if isinstance(e, genai_errors.ServerError) and 500 <= getattr(e, 'code', 0) < 600:
        return True
    return False


def _with_retry(fn):
    """Call fn(), retrying on transient errors (rate limits and 5xx) with exponential backoff.

    Non-retryable exceptions are raised immediately.
    """
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            if not _is_retryable_error(e):
                raise
            last_error = e
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    "Transient error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, MAX_RETRIES, delay, e,
                )
                time.sleep(delay)
            # else: fall through, raise after loop
    raise last_error


# ---------------------------------------------------------------------------
# Response analysis (scoring)
# ---------------------------------------------------------------------------

# Generic business suffixes — not distinctive enough for partial name matching
GENERIC_SUFFIXES = {
    'inc', 'llc', 'corp', 'corporation', 'company', 'co', 'ltd',
    'associates', 'association', 'group', 'services', 'solutions', 'consulting',
    'partners', 'agency', 'enterprises', 'firm', 'professionals',
    'advisors', 'specialists', 'international', 'national', 'global',
    'foundation', 'institute', 'center', 'centre', 'organization', 'society',
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


import re


# ---------------------------------------------------------------------------
# Position & sentiment analysis helpers
# ---------------------------------------------------------------------------

# Patterns that indicate a numbered or bulleted list item
_LIST_PATTERNS = [
    re.compile(r'^\s*(\d+)\.\s'),                    # "1. " numbered list
    re.compile(r'^\s*(\d+)\)\s'),                     # "1) " numbered list
    re.compile(r'^\s*[-*•]\s'),                        # "- " or "* " bullet list
    re.compile(r'^\s*\*\*(.+?)\*\*'),                  # "**Name**" bold entries (markdown lists)
]

# Markdown header pattern for structured responses
_HEADER_PATTERN = re.compile(r'^\s*#{1,4}\s+(.+)', re.MULTILINE)
_BOLD_PATTERN = re.compile(r'\*\*(.+?)\*\*')


def _analyze_position(answer, name_variations):
    """Determine the business's position in a list within the response.

    Returns (position, list_size) where position is 1-indexed,
    or (None, None) if not in a recognizable list.
    """
    lines = answer.split('\n')
    name_lower_set = set(name_variations)

    # Strategy 1: Look for numbered lists ("1. Name", "2. Name")
    numbered_entries = []
    for line in lines:
        m = re.match(r'^\s*(\d+)[.)]\s+(.+)', line)
        if m:
            numbered_entries.append((int(m.group(1)), m.group(2).lower()))

    if len(numbered_entries) >= 2:
        for pos, entry_text in numbered_entries:
            if any(name in entry_text for name in name_lower_set):
                return pos, len(numbered_entries)

    # Strategy 2: Look for bold entries acting as list items ("**Name** - description")
    bold_entries = []
    for line in lines:
        m = _BOLD_PATTERN.search(line)
        if m:
            bold_text = m.group(1).strip().lower()
            # Only count as a list entry if it starts the line or is the main content
            if line.strip().startswith('**') or line.strip().startswith('- **') or line.strip().startswith('* **'):
                bold_entries.append(bold_text)

    if len(bold_entries) >= 2:
        for i, entry_text in enumerate(bold_entries):
            if any(name in entry_text for name in name_lower_set):
                return i + 1, len(bold_entries)

    # Strategy 3: Look for markdown headers as list items ("## Name")
    header_entries = []
    for m in _HEADER_PATTERN.finditer(answer):
        header_entries.append(m.group(1).strip().lower())

    if len(header_entries) >= 2:
        for i, entry_text in enumerate(header_entries):
            if any(name in entry_text for name in name_lower_set):
                return i + 1, len(header_entries)

    return None, None


# Recommendation/positive/qualified signal words (checked near the business name)
_RECOMMEND_SIGNALS = re.compile(
    r'\b(recommend|top pick|highly recommend|must.visit|go.to|best choice|our favorite|standout|first choice)\b',
    re.I,
)
_POSITIVE_SIGNALS = re.compile(
    r'\b(excellent|outstanding|exceptional|great|amazing|fantastic|beloved|popular|well.known|renowned|top.rated|highly rated|award.winning|impressive|noteworthy)\b',
    re.I,
)
_QUALIFIED_SIGNALS = re.compile(
    r'\b(however|although|though|but|caveat|downside|drawback|overpriced|expensive|slow|limited|inconsistent|disappointing|mixed reviews|some find|note that|keep in mind|be aware)\b',
    re.I,
)


def _analyze_sentiment(answer, name_variations, name_found):
    """Determine how the business is framed in the response.

    Returns one of: 'recommended', 'positive', 'neutral', 'qualified', or None.
    """
    if not name_found:
        return None

    answer_lower = answer.lower()

    # Find the region around the name mention for context
    # Use a window of ~200 chars around the first mention
    name_pos = -1
    for name in name_variations:
        pos = answer_lower.find(name)
        if pos >= 0:
            name_pos = pos
            break

    if name_pos < 0:
        return "neutral"

    # Extract context window around the mention
    start = max(0, name_pos - 100)
    end = min(len(answer_lower), name_pos + 300)
    context = answer_lower[start:end]

    has_recommend = bool(_RECOMMEND_SIGNALS.search(context))
    has_positive = bool(_POSITIVE_SIGNALS.search(context))
    has_qualified = bool(_QUALIFIED_SIGNALS.search(context))

    if has_recommend:
        return "recommended"
    elif has_qualified and has_positive:
        return "qualified"
    elif has_qualified:
        return "qualified"
    elif has_positive:
        return "positive"
    else:
        return "neutral"


# ---------------------------------------------------------------------------
# Namesake collision detection
# ---------------------------------------------------------------------------
# Detects when an AI response mentions the client's company name but actually
# describes a *different* entity with the same name (e.g. Perplexity returning
# info about a Florida firm when the client is in California). Such responses
# should score 0, not 2-3, because the client isn't really surfaced.

_US_STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming',
}
_STATE_NAME_TO_CODE = {name.lower(): code for code, name in _US_STATES.items()}
_STATE_CODES = set(_US_STATES.keys())

# Full state names, sorted longest-first so "West Virginia" matches before "Virginia"
_STATE_NAME_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(n) for n in sorted(_US_STATES.values(), key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)
# Two-letter state code in an address-like position (after a comma): ", FL"
_STATE_CODE_PATTERN = re.compile(r',\s+([A-Z]{2})\b')


def _parse_client_state(client_location):
    """Extract a US state code from a client location string.

    "Westlake Village, CA" -> "CA"
    "San Francisco, California" -> "CA"
    "Salt Lake City" -> None (no state info)
    """
    if not client_location:
        return None
    # Try trailing ", XX" state code
    m = re.search(r',\s*([A-Za-z]{2})\s*$', client_location.strip())
    if m and m.group(1).upper() in _STATE_CODES:
        return m.group(1).upper()
    # Try full state name anywhere in string
    m = _STATE_NAME_PATTERN.search(client_location)
    if m:
        return _STATE_NAME_TO_CODE[m.group(1).lower()]
    return None


def _states_in_window(text):
    """Return the set of US state codes mentioned in the given text span."""
    states = set()
    for m in _STATE_NAME_PATTERN.finditer(text):
        states.add(_STATE_NAME_TO_CODE[m.group(1).lower()])
    for m in _STATE_CODE_PATTERN.finditer(text):
        if m.group(1) in _STATE_CODES:
            states.add(m.group(1))
    return states


def _find_name_positions(response, distinctive_words):
    """Find character ranges in `response` where the client name likely appears.

    Matches distinctive words in order with flexible punctuation between them
    (so "Retirement Planning Associates, Inc." still matches even though the
    source name has no comma). Case-insensitive.
    """
    if not distinctive_words:
        return []
    # Allow any punctuation/whitespace between words (e.g. "Name, Inc." → "Name Inc.")
    pattern = r'\b' + r'[\s,.\-\'"()]+'.join(re.escape(w) for w in distinctive_words) + r'\b'
    return [(m.start(), m.end()) for m in re.finditer(pattern, response, re.IGNORECASE)]


def _is_sentence_break(text, i):
    """True if text[i] ends a sentence (not just an abbreviation like 'Inc.')."""
    if text[i] == '\n':
        return True
    if text[i] not in '.!?':
        return False
    # Look past whitespace to the next character.
    j = i + 1
    while j < len(text) and text[j] in ' \t':
        j += 1
    if j >= len(text):
        return True  # end of text
    # A real sentence break is followed by an uppercase letter starting the next
    # sentence. If the next char is lowercase, a comma, a digit, etc., it's an
    # abbreviation like "Inc., based in ..." or "Mr. Smith".
    return text[j].isupper()


def _sentence_containing(text, start, end):
    """Return the sentence-ish span of text that contains the range [start, end)."""
    sent_start = 0
    for i in range(start - 1, -1, -1):
        if _is_sentence_break(text, i):
            sent_start = i + 1
            break
    sent_end = len(text)
    for i in range(end, len(text)):
        if _is_sentence_break(text, i):
            sent_end = i
            break
    return text[sent_start:sent_end]


def _detect_namesake_collision(response, client_name, client_location):
    """Return True if the response describes a different entity with the same name.

    Rule: look at every sentence that names the client. Collect the US states
    mentioned in those sentences. If the client's state appears, the response
    is (at least partly) about them — don't flag. If only foreign states
    appear, flag as a namesake collision.

    High-precision — requires ≥2 distinctive name words AND the name to be
    bound to a state within the same sentence. Mentions in other sentences
    (e.g. "In California, retirement planning costs...") don't cancel.
    """
    if not response or not client_name or not client_location:
        return False
    client_state = _parse_client_state(client_location)
    if not client_state:
        return False

    # Pull out distinctive name words (skip "Inc", "LLC", etc. — too generic to
    # indicate the response is about the same entity).
    name_tokens = re.sub(r'[^a-z0-9\s]', ' ', client_name.lower()).split()
    distinctive = [w for w in name_tokens if len(w) > 2 and w not in GENERIC_SUFFIXES]
    if len(distinctive) < 2:
        return False  # Name too short/generic to reliably detect namesake

    positions = _find_name_positions(response, distinctive)
    if not positions:
        return False  # Name isn't really in the response

    states_bound_to_name = set()
    for start, end in positions:
        sentence = _sentence_containing(response, start, end)
        states_bound_to_name |= _states_in_window(sentence)

    if not states_bound_to_name:
        return False  # No state bound to name — ambiguous
    if client_state in states_bound_to_name:
        return False  # Client's state bound to name — plausibly about them
    return True  # Only foreign states bound to name — collision


def analyze_response(answer, client_name, client_website, client_location=None):
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

    # Namesake collision check: if the response mentions the client name but
    # explicitly describes a different geographic entity, the client isn't
    # really surfaced. Override score to 0. Runs on its own looser name
    # detection (distinctive-word matching) so it still fires when punctuation
    # differences (e.g. "Acme Co, Inc.") cause the strict name_found check
    # above to miss.
    namesake_collision = False
    if client_location:
        namesake_collision = _detect_namesake_collision(answer, client_name, client_location)
        if namesake_collision:
            score = 0
            mentions.append("Namesake collision — response describes a different entity")

    if namesake_collision:
        finding = "Namesake collision — response describes a different firm with the same name"
    elif score >= 3:
        finding = "Strong presence - named and cited"
    elif score >= 2:
        finding = "Mentioned in response"
    elif score >= 1:
        finding = "Briefly referenced"
    else:
        finding = "Not mentioned in response"

    # Position and sentiment analysis
    position, list_size = _analyze_position(answer, name_variations)
    sentiment = _analyze_sentiment(answer, name_variations, name_found)

    return {
        "score": score,
        "namesake_collision": namesake_collision,
        "finding": finding,
        "mentions": mentions,
        "response_preview": answer[:300] + "..." if len(answer) > 300 else answer,
        "position": position,
        "list_size": list_size,
        "sentiment": sentiment,
    }


# ---------------------------------------------------------------------------
# Platform query runners
# ---------------------------------------------------------------------------

def _error_result(message):
    # `errored: True` lets downstream scoring distinguish a 0 from "not mentioned"
    # vs. a 0 from a rate limit / API failure. Without this flag, a quota-exhausted
    # platform tanks the visibility percentage as if the client were genuinely absent.
    return {
        "error": message,
        "errored": True,
        "score": 0,
        "finding": message,
        "mentions": [],
        "response_preview": "",
        "position": None,
        "list_size": None,
        "sentiment": None,
    }


def query_platform(platform, query_text, client_name, client_website, client_location=None):
    """Run a query on the specified platform and score the response.

    platform: one of "chatgpt", "claude", "gemini", "perplexity"
    client_location: optional string like "Westlake Village, CA" — enables namesake
    collision detection when the response describes a different entity.
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
    return runner(query_text, client_name, client_website, client_location)


def _run_chatgpt(query, client_name, client_website, client_location=None):
    if not openai_client:
        return _error_result("OpenAI API key not configured")
    try:
        def _call():
            response = openai_client.chat.completions.create(
                model=CHATGPT_MODEL,
                messages=[{"role": "user", "content": query}],
                max_tokens=1000,
                temperature=0
            )
            return response.choices[0].message.content

        answer = _with_retry(_call)
        return analyze_response(answer, client_name, client_website, client_location)
    except Exception as e:
        return _error_result(f"Error: {e}")


def _run_claude(query, client_name, client_website, client_location=None):
    if not anthropic_client:
        return _error_result("Anthropic API key not configured")
    try:
        def _call():
            response = anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": query}]
            )
            return response.content[0].text

        answer = _with_retry(_call)
        return analyze_response(answer, client_name, client_website, client_location)
    except Exception as e:
        return _error_result(f"Error: {e}")


def _run_gemini(query, client_name, client_website, client_location=None):
    if not gemini_client:
        return _error_result("Google API key not configured")
    try:
        def _call():
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=query,
                config={"temperature": 0},
            )
            return response.text

        answer = _with_retry(_call)
        return analyze_response(answer, client_name, client_website, client_location)
    except Exception as e:
        return _error_result(f"Error: {e}")


def _run_perplexity(query, client_name, client_website, client_location=None):
    if not perplexity_client:
        return _error_result("Perplexity API key not configured")
    try:
        def _call():
            response = perplexity_client.chat.completions.create(
                model=PERPLEXITY_MODEL,
                messages=[{"role": "user", "content": query}],
                max_tokens=1000,
                temperature=0
            )
            return response.choices[0].message.content

        answer = _with_retry(_call)
        return analyze_response(answer, client_name, client_website, client_location)
    except Exception as e:
        return _error_result(f"Error: {e}")
