"""Configuration — API clients, model constants, logo helper."""

import os
import base64
from dotenv import load_dotenv
from openai import OpenAI
import anthropic
import google.generativeai as genai

load_dotenv()

# ---------------------------------------------------------------------------
# Model constants (change these when upgrading models)
# ---------------------------------------------------------------------------
CHATGPT_MODEL = "gpt-4o-mini"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
GEMINI_MODEL = "gemini-2.0-flash"
PERPLEXITY_MODEL = "sonar"

# ---------------------------------------------------------------------------
# API clients (None if key not provided)
# ---------------------------------------------------------------------------
openai_client = None
anthropic_client = None
gemini_model = None
perplexity_client = None

if os.getenv('OPENAI_API_KEY'):
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

if os.getenv('ANTHROPIC_API_KEY'):
    anthropic_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

if os.getenv('GOOGLE_API_KEY'):
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    gemini_model = genai.GenerativeModel(GEMINI_MODEL)

if os.getenv('PERPLEXITY_API_KEY'):
    perplexity_client = OpenAI(
        api_key=os.getenv('PERPLEXITY_API_KEY'),
        base_url="https://api.perplexity.ai"
    )

# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------
DEFAULT_LOGO_PATH = "/Users/sabrielparker/Desktop/thirdsun things/logos/ThirdSun-logo_secondary-horizontal-color.png"


def get_logo_base64():
    """Get logo as base64 string for embedding in HTML reports."""
    if os.path.exists(DEFAULT_LOGO_PATH):
        with open(DEFAULT_LOGO_PATH, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(DEFAULT_LOGO_PATH)[1].lower()
        mime_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}
        mime = mime_types.get(ext, "image/png")
        return f'<img src="data:{mime};base64,{img_data}" style="max-height: 60px; max-width: 250px;">'
    return '<div class="logo-text">THIRD SUN</div>'


def any_api_configured():
    """Return True if at least one LLM API is available."""
    return bool(openai_client or anthropic_client or gemini_model or perplexity_client)
