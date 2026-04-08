"""Implementation Workbook — master checklist + screenshot path helpers.

The workbook is the post-audit "what we did" tracker. One workbook per audit
(see model #1 in the planning conversation). The master checklist is fixed
in v1; per-client editing can be added later if needed.

Phases:
    technical — Technical foundation work Third Sun executes (schema, llms.txt, etc.)
    content   — Content optimization work Third Sun executes (FAQ, About, etc.)
    client    — Off-site work handed to the client (GBP, reviews, directories, etc.)
"""

import os
import re


# ---------------------------------------------------------------------------
# Master checklist
# ---------------------------------------------------------------------------

MASTER_CHECKLIST = [
    # ---- Phase 1: Technical Foundation -------------------------------------
    {
        "id": "schema_markup",
        "phase": "technical",
        "title": "Add JSON-LD schema markup",
        "description": "Organization, LocalBusiness, Service, FAQPage, BreadcrumbList. Single biggest GEO lever.",
    },
    {
        "id": "ai_crawler_files",
        "phase": "technical",
        "title": "AI crawler files (llms.txt, robots.txt, sitemap.xml)",
        "description": "Add llms.txt at site root, allow AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot) in robots.txt, and verify sitemap.xml is current and submitted to GSC + Bing.",
    },
    {
        "id": "nap_consistency",
        "phase": "technical",
        "title": "NAP consistency sweep",
        "description": "Name/Address/Phone identical across header, footer, contact page, and schema markup.",
    },
    {
        "id": "semantic_html",
        "phase": "technical",
        "title": "Semantic HTML cleanup",
        "description": "One H1 per page with clean H2/H3 hierarchy, descriptive image alt text, and clear internal links to key service pages. Joomla templates often break these.",
    },

    # ---- Phase 2: Content Optimization -------------------------------------
    {
        "id": "faq_page",
        "phase": "content",
        "title": "Build the FAQ page",
        "description": "Use GEO Auditor's FAQ generator output, mark up with FAQPage schema. AI engines love Q&A format.",
    },
    {
        "id": "about_services_rewrite",
        "phase": "content",
        "title": "Rewrite About + service pages for clarity",
        "description": "Who, what, where, since when, who they serve. Short declarative sentences and H2 questions on service pages. LLMs parse these better than marketing prose.",
    },
    {
        "id": "content_gaps",
        "phase": "content",
        "title": "Fill content gaps from the audit",
        "description": "For every query the client *should* rank for but doesn't, draft a page or section that directly answers it.",
    },

    # ---- Phase 3: Client Handoff -------------------------------------------
    {
        "id": "gbp_audit",
        "phase": "client",
        "title": "Google Business Profile audit",
        "description": "Categories, services, photos, Q&A section, posts. AI answers pull heavily from GBP for local queries.",
    },
    {
        "id": "reviews",
        "phase": "client",
        "title": "Review acquisition push",
        "description": "Google, Yelp, industry-specific. AI engines weight third-party validation.",
    },
    {
        "id": "directory_presence",
        "phase": "client",
        "title": "Directory presence",
        "description": "Wikidata entry (if eligible — feeds AI knowledge graphs) plus relevant industry directory submissions. Avoid spammy directories.",
    },
    {
        "id": "outreach",
        "phase": "client",
        "title": "Outreach (backlinks + press)",
        "description": "Clean toxic links, identify backlink opportunities, and pursue press / news mentions. Fresh citations move the needle fast on Perplexity especially.",
    },
]


VALID_ITEM_IDS = {item["id"] for item in MASTER_CHECKLIST}
VALID_PHASES = ("technical", "content", "client")

PHASE_LABELS = {
    "technical": "Technical Foundation",
    "content": "Content Optimization",
    "client": "Client Handoff",
}


def items_for_phase(phase):
    """Return master checklist items for a given phase, in declaration order."""
    return [item for item in MASTER_CHECKLIST if item["phase"] == phase]


def is_valid_item_id(item_id):
    """Check whether an item ID exists in the master checklist."""
    return item_id in VALID_ITEM_IDS


def empty_workbook_state():
    """Return a fresh workbook state dict with all items unchecked.

    Shape:
        {
            "items": {
                "<item_id>": {
                    "status": "todo",       # "todo" or "done"
                    "notes": "",
                    "completed_by": "",
                    "completed_at": None,
                    "screenshots": [],      # list of filenames (not paths)
                },
                ...
            }
        }
    """
    return {
        "items": {
            item["id"]: {
                "status": "todo",
                "notes": "",
                "completed_by": "",
                "completed_at": None,
                "screenshots": [],
            }
            for item in MASTER_CHECKLIST
        }
    }


def merge_with_master(state):
    """Merge a stored workbook state with the current master checklist.

    Ensures any new master items get default entries (so adding a checklist
    item doesn't break existing workbooks) and drops items no longer in the
    master.
    """
    fresh = empty_workbook_state()
    if not state or "items" not in state:
        return fresh

    for item_id, fresh_item in fresh["items"].items():
        if item_id in state["items"]:
            stored = state["items"][item_id]
            fresh_item["status"] = stored.get("status", "todo")
            fresh_item["notes"] = stored.get("notes", "")
            fresh_item["completed_by"] = stored.get("completed_by", "")
            fresh_item["completed_at"] = stored.get("completed_at")
            fresh_item["screenshots"] = list(stored.get("screenshots", []))

    return fresh


# ---------------------------------------------------------------------------
# Screenshot storage
# ---------------------------------------------------------------------------

# Screenshots live on the persistent volume. Default to a sibling folder for
# local dev; Fly.io can override via SCREENSHOTS_DIR=/data/screenshots.
SCREENSHOTS_DIR = os.environ.get(
    "SCREENSHOTS_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots"),
)


# Whitelist for upload extensions — keep this tight to avoid serving anything weird.
ALLOWED_SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name):
    """Sanitize a filename for filesystem storage. Strips paths and odd chars."""
    # Drop any directory components
    name = os.path.basename(name or "")
    # Replace anything outside [A-Za-z0-9._-] with underscores
    name = _SAFE_FILENAME_RE.sub("_", name)
    # Strip leading dots so we never end up with hidden files
    name = name.lstrip(".")
    return name or "screenshot"


def screenshot_dir(audit_id, item_id):
    """Return the absolute screenshot directory for an audit/item pair.

    Validates item_id against the master checklist so a malicious request
    can't write outside known item buckets.
    """
    if not is_valid_item_id(item_id):
        raise ValueError(f"Unknown checklist item: {item_id}")
    return os.path.join(SCREENSHOTS_DIR, str(int(audit_id)), item_id)


def screenshot_path(audit_id, item_id, filename):
    """Return the absolute path for a single screenshot file."""
    return os.path.join(screenshot_dir(audit_id, item_id), safe_filename(filename))


def ensure_screenshot_dir(audit_id, item_id):
    """Create the screenshot directory if it doesn't exist. Returns the path."""
    path = screenshot_dir(audit_id, item_id)
    os.makedirs(path, exist_ok=True)
    return path
