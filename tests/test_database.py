"""Tests for database.py — SQLite CRUD operations."""

import importlib
import os

import pytest
import database


def test_database_path_respects_env_var(monkeypatch):
    """DATABASE_PATH env var should override the default path (Fly.io persistence fix)."""
    monkeypatch.setenv("DATABASE_PATH", "/tmp/some-fly-volume/audits.db")
    reloaded = importlib.reload(database)
    try:
        assert reloaded.DATABASE == "/tmp/some-fly-volume/audits.db"
    finally:
        # Reload without the env var so other tests get the default again.
        monkeypatch.delenv("DATABASE_PATH", raising=False)
        importlib.reload(database)


def test_database_path_default_when_unset(monkeypatch):
    """Without DATABASE_PATH, DATABASE should resolve to audits.db next to the source."""
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    reloaded = importlib.reload(database)
    assert reloaded.DATABASE.endswith("audits.db")
    assert os.path.isabs(reloaded.DATABASE)


def test_save_and_load_audit(app, sample_form_data, sample_intake_data):
    """Save an audit and load it back."""
    audit_id = database.save_audit(sample_form_data, sample_intake_data)
    assert audit_id is not None

    loaded = database.get_audit(audit_id)
    assert loaded is not None
    assert loaded["form_data"]["client"]["name"] == "Test Coffee Shop"
    assert loaded["intake_data"]["services"] == "Specialty coffee, pastries, catering"


def test_save_audit_requires_client_name(app):
    """Save should fail without a client name."""
    with pytest.raises(ValueError, match="Client name is required"):
        database.save_audit({"client": {"name": ""}}, {})


def test_update_existing_audit(app, sample_form_data, sample_intake_data):
    """Update an existing audit by passing audit_id."""
    audit_id = database.save_audit(sample_form_data, sample_intake_data)

    updated_data = sample_form_data.copy()
    updated_data["client"] = {**sample_form_data["client"], "name": "Updated Coffee Shop"}
    database.save_audit(updated_data, sample_intake_data, audit_id=audit_id)

    loaded = database.get_audit(audit_id)
    assert loaded["form_data"]["client"]["name"] == "Updated Coffee Shop"


def test_list_audits(app, sample_form_data, sample_intake_data):
    """List should return all saved audits."""
    database.save_audit(sample_form_data, sample_intake_data)

    second = sample_form_data.copy()
    second["client"] = {**sample_form_data["client"], "name": "Another Client"}
    database.save_audit(second, {})

    audits = database.list_audits()
    assert len(audits) == 2
    names = [a["client_name"] for a in audits]
    assert "Test Coffee Shop" in names
    assert "Another Client" in names


def test_delete_audit(app, sample_form_data, sample_intake_data):
    """Delete should remove the audit and return True."""
    audit_id = database.save_audit(sample_form_data, sample_intake_data)
    assert database.delete_audit(audit_id) is True
    assert database.get_audit(audit_id) is None


def test_delete_nonexistent_audit(app):
    """Delete on a missing ID should return False."""
    assert database.delete_audit(9999) is False


def test_get_nonexistent_audit(app):
    """Getting a missing ID should return None."""
    assert database.get_audit(9999) is None


def test_visibility_percentage_extracted_from_queries(app):
    """When visibility_level has no %, calculate from query scores."""
    form_data = {
        "client": {"name": "Calc Test"},
        "visibility_level": "moderate",
        "queries": [
            {"score": 6},
            {"score": 6},
        ],
    }
    audit_id = database.save_audit(form_data, {})
    audits = database.list_audits()
    audit = [a for a in audits if a["client_name"] == "Calc Test"][0]
    # 12 / 24 = 50.0%
    assert audit["visibility_percentage"] == 50.0


# ---------------------------------------------------------------------------
# Recommendation tracking tests
# ---------------------------------------------------------------------------

from database import _track_recommendations


def test_track_recommendations_improved():
    """Recommendation with improved related queries should show 'improved'."""
    prev_recs = [{
        "title": "Boost Local Visibility",
        "priority": "high",
        "issue": 'Not appearing for "best coffee shops for remote work in Salt Lake City"',
        "actions": ["Create a page about remote work"],
    }]
    query_changes = [{
        "query": "best coffee shops for remote work in Salt Lake City",
        "type": "Local",
        "previous_score": 4,
        "current_score": 8,
        "change": 4,
    }]
    current_queries = [{"query": "best coffee shops for remote work in Salt Lake City", "score": 8}]

    tracking = _track_recommendations(prev_recs, query_changes, current_queries)
    assert len(tracking) == 1
    assert tracking[0]["status"] == "improved"
    assert len(tracking[0]["matched_queries"]) == 1


def test_track_recommendations_declined():
    """Recommendation with declined related queries should show 'declined'."""
    prev_recs = [{
        "title": "Improve Breakfast Presence",
        "priority": "medium",
        "issue": 'Not appearing for "breakfast and lunch spots near Downtown Salt Lake City"',
        "actions": ["Add menu pages"],
    }]
    query_changes = [{
        "query": "breakfast and lunch spots near Downtown Salt Lake City",
        "type": "Local",
        "previous_score": 4,
        "current_score": 0,
        "change": -4,
    }]
    current_queries = [{"query": "breakfast and lunch spots near Downtown Salt Lake City", "score": 0}]

    tracking = _track_recommendations(prev_recs, query_changes, current_queries)
    assert len(tracking) == 1
    assert tracking[0]["status"] == "declined"


def test_track_recommendations_no_change():
    """Recommendation with unchanged low-scoring queries should show 'no_change'."""
    prev_recs = [{
        "title": "Create Educational Content",
        "priority": "high",
        "issue": 'Not appearing for "what is small batch coffee roasting?"',
        "actions": ["Write a blog post"],
    }]
    query_changes = [{
        "query": "what is small batch coffee roasting?",
        "type": "Local",
        "previous_score": 0,
        "current_score": 0,
        "change": 0,
    }]
    current_queries = [{"query": "what is small batch coffee roasting?", "score": 0}]

    tracking = _track_recommendations(prev_recs, query_changes, current_queries)
    assert len(tracking) == 1
    assert tracking[0]["status"] == "no_change"


def test_track_recommendations_unmatched():
    """Recommendation not referencing specific queries should be 'unmatched'."""
    prev_recs = [{
        "title": "Build Social Media Presence",
        "priority": "low",
        "issue": "General brand awareness is low across all platforms",
        "actions": ["Post weekly on Instagram"],
    }]
    query_changes = [{
        "query": "best coffee Salt Lake City",
        "type": "Local",
        "previous_score": 4,
        "current_score": 6,
        "change": 2,
    }]
    current_queries = [{"query": "best coffee Salt Lake City", "score": 6}]

    tracking = _track_recommendations(prev_recs, query_changes, current_queries)
    assert len(tracking) == 1
    assert tracking[0]["status"] == "unmatched"


def test_track_recommendations_empty():
    """No previous recommendations should return empty list."""
    assert _track_recommendations([], [], []) == []
    assert _track_recommendations(None, [], []) == []


# ---------------------------------------------------------------------------
# Comparison collision-adjustment tests
# ---------------------------------------------------------------------------

def _comparison_fixture_pair(app, cur_query_score=9, cur_perp_score=0, cur_perp_collision=True,
                              prev_query_score=12, prev_perp_score=3):
    """Save a pair of audits that share a brand query, return (previous_id, current_id)."""
    prev_fd = {
        "client": {"name": "RPA Test", "audit_date": "March 1, 2026", "location": "Westlake Village, CA"},
        "queries": [
            {"query": "What do people say about RPA Test?", "type": "Brand", "score": prev_query_score,
             "details": {
                 "chatgpt": {"score": 3, "namesake_collision": False},
                 "claude": {"score": 3, "namesake_collision": False},
                 "gemini": {"score": 3, "namesake_collision": False},
                 "perplexity": {"score": prev_perp_score, "namesake_collision": False},
             }},
        ],
        "platforms": {
            "chatgpt": {"score": 3, "max": 3},
            "claude": {"score": 3, "max": 3},
            "gemini": {"score": 3, "max": 3},
            "perplexity": {"score": prev_perp_score, "max": 3},
        },
    }
    cur_fd = {
        "client": {"name": "RPA Test", "audit_date": "April 1, 2026", "location": "Westlake Village, CA"},
        "queries": [
            {"query": "What do people say about RPA Test?", "type": "Brand", "score": cur_query_score,
             "details": {
                 "chatgpt": {"score": 3, "namesake_collision": False},
                 "claude": {"score": 3, "namesake_collision": False},
                 "gemini": {"score": 3, "namesake_collision": False},
                 "perplexity": {"score": cur_perp_score, "namesake_collision": cur_perp_collision},
             }},
        ],
        "platforms": {
            "chatgpt": {"score": 3, "max": 3},
            "claude": {"score": 3, "max": 3},
            "gemini": {"score": 3, "max": 3},
            "perplexity": {"score": cur_perp_score, "max": 3},
        },
    }
    prev_id = database.save_audit(prev_fd, {})
    cur_id = database.save_audit(cur_fd, {})
    return prev_id, cur_id


def test_comparison_reports_newly_detected_collisions(app):
    """When a platform dropped due to newly-detected namesake collision, the comparison
    surfaces the delta separately so re-audit reports don't frame it as a regression."""
    prev_id, cur_id = _comparison_fixture_pair(app)
    comp = database.get_comparison(cur_id, prev_id)

    # Raw delta is negative — 3 points lost on Perplexity
    assert comp["percentage_change"] < 0

    # Collision-adjusted output should attribute those 3 points to newly-detected collision
    adj = comp.get("collision_adjusted")
    assert adj is not None
    assert adj["points_lost_to_collision"] == 3
    # Excluding the collision, the score is unchanged
    assert adj["adjusted_percentage_change"] == 0.0
    # And the specific query/platform is named
    assert len(adj["collision_queries"]) == 1
    assert adj["collision_queries"][0]["platform"] == "Perplexity"
    assert "RPA Test" in adj["collision_queries"][0]["query"]


def test_comparison_no_collision_adjustment_when_none_detected(app):
    """Without any namesake collisions, collision_adjusted is None."""
    prev_id, cur_id = _comparison_fixture_pair(
        app, cur_perp_score=3, cur_perp_collision=False, cur_query_score=12, prev_query_score=12,
    )
    comp = database.get_comparison(cur_id, prev_id)
    assert comp.get("collision_adjusted") is None


def test_comparison_does_not_credit_collision_flagged_in_both(app):
    """If the previous audit *also* flagged the collision, current is not a newly-detected
    collision — the drop (if any) is a real change in platform behavior."""
    prev_id, cur_id = _comparison_fixture_pair(app)
    # Mutate the previous to already have the collision flag
    from database import get_db
    import json as _json
    prev = database.get_audit(prev_id)
    prev_fd = prev["form_data"]
    prev_fd["queries"][0]["details"]["perplexity"]["namesake_collision"] = True
    database.save_audit(prev_fd, {}, audit_id=prev_id)

    comp = database.get_comparison(cur_id, prev_id)
    # Collision wasn't newly-detected, so no adjustment
    assert comp.get("collision_adjusted") is None


def test_track_recommendations_strong():
    """Recommendation with unchanged high-scoring queries should show 'strong'."""
    prev_recs = [{
        "title": "Maintain Brand Presence",
        "priority": "low",
        "issue": 'Keep strong presence for "Publik Coffee Roasters organic small batch coffee Salt Lake City"',
        "actions": ["Keep content updated"],
    }]
    query_changes = [{
        "query": "Publik Coffee Roasters organic small batch coffee Salt Lake City",
        "type": "Brand",
        "previous_score": 10,
        "current_score": 10,
        "change": 0,
    }]
    current_queries = [{"query": "Publik Coffee Roasters organic small batch coffee Salt Lake City", "score": 10}]

    tracking = _track_recommendations(prev_recs, query_changes, current_queries)
    assert len(tracking) == 1
    assert tracking[0]["status"] == "strong"
