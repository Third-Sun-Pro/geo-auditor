"""Tests for database.py — SQLite CRUD operations."""

import pytest
import database


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
