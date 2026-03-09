"""Shared fixtures for GEO auditor tests."""

import os
import sys
import tempfile
import pytest

# Ensure webapp modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def app():
    """Create a Flask test app with a temporary database."""
    # Use a temp database so tests don't touch real data
    tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp_db.close()

    import database
    original_db = database.DATABASE
    database.DATABASE = tmp_db.name
    database.init_db()

    from app import create_app
    flask_app = create_app()
    flask_app.config['TESTING'] = True

    yield flask_app

    # Restore original database path and clean up
    database.DATABASE = original_db
    os.unlink(tmp_db.name)


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def sample_form_data():
    """Realistic form data for saving/loading audits."""
    return {
        "client": {
            "name": "Test Coffee Shop",
            "website": "https://testcoffee.com",
            "industry": "Specialty Coffee",
            "location": "Salt Lake City, UT",
            "audit_date": "2026-02-28",
            "package": "Basic",
            "competitors": "Bean Bros, Java House",
        },
        "visibility_level": "moderate",
        "queries": [
            {"query": "best coffee Salt Lake City", "type": "Local", "score": 6, "finding": "Mentioned on ChatGPT, Claude"},
            {"query": "Test Coffee Shop reviews", "type": "Brand", "score": 9, "finding": "Strong presence"},
        ],
        "platforms": {
            "chatgpt": {"score": 4, "max": 6, "note": "GPT-4o-mini"},
            "claude": {"score": 3, "max": 6, "note": "Claude Haiku"},
            "gemini": {"score": 5, "max": 6, "note": "Gemini Flash"},
            "perplexity": {"score": 3, "max": 6, "note": "Perplexity Sonar"},
        },
        "key_findings": ["Strong brand recognition on Google platforms"],
        "recommendations": [
            {
                "title": "Improve Local Visibility",
                "priority": "high",
                "issue": "Not appearing in local searches",
                "actions": ["Add location keywords", "Claim Google Business Profile"],
            }
        ],
        "competitors": [
            {"name": "Bean Bros", "visibility": "45%", "strengths": "Large chain", "your_advantage": "Local roasting"},
        ],
    }


@pytest.fixture
def sample_intake_data():
    """Intake questionnaire data."""
    return {
        "how_found": "Word of mouth and Google",
        "services": "Specialty coffee, pastries, catering",
        "audience": "Young professionals, remote workers",
    }
