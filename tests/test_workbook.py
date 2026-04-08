"""Tests for workbook.py and the workbooks table in database.py."""

import os
import tempfile
import shutil
import pytest

import database
import workbook


# ---------------------------------------------------------------------------
# Master checklist
# ---------------------------------------------------------------------------

def test_master_checklist_has_all_three_phases():
    phases = {item["phase"] for item in workbook.MASTER_CHECKLIST}
    assert phases == {"technical", "content", "client"}


def test_master_checklist_item_ids_are_unique():
    ids = [item["id"] for item in workbook.MASTER_CHECKLIST]
    assert len(ids) == len(set(ids)), "duplicate item id in master checklist"


def test_master_checklist_items_have_required_fields():
    for item in workbook.MASTER_CHECKLIST:
        assert item["id"]
        assert item["phase"] in workbook.VALID_PHASES
        assert item["title"]
        assert item["description"]


def test_items_for_phase_returns_only_matching_phase():
    technical = workbook.items_for_phase("technical")
    assert all(item["phase"] == "technical" for item in technical)
    assert len(technical) >= 1  # sanity check we have at least one item


def test_is_valid_item_id():
    assert workbook.is_valid_item_id("schema_markup")
    assert not workbook.is_valid_item_id("nonexistent_item")
    assert not workbook.is_valid_item_id("")


# ---------------------------------------------------------------------------
# Workbook state helpers
# ---------------------------------------------------------------------------

def test_empty_workbook_state_includes_every_master_item():
    state = workbook.empty_workbook_state()
    assert set(state["items"].keys()) == workbook.VALID_ITEM_IDS
    for item_state in state["items"].values():
        assert item_state["status"] == "todo"
        assert item_state["notes"] == ""
        assert item_state["screenshots"] == []


def test_merge_with_master_preserves_user_data():
    state = workbook.empty_workbook_state()
    state["items"]["schema_markup"]["status"] = "done"
    state["items"]["schema_markup"]["notes"] = "Added Organization + LocalBusiness"
    state["items"]["schema_markup"]["completed_by"] = "Sabriel"
    state["items"]["schema_markup"]["screenshots"] = ["before.png", "after.png"]

    merged = workbook.merge_with_master(state)
    assert merged["items"]["schema_markup"]["status"] == "done"
    assert merged["items"]["schema_markup"]["notes"] == "Added Organization + LocalBusiness"
    assert merged["items"]["schema_markup"]["completed_by"] == "Sabriel"
    assert merged["items"]["schema_markup"]["screenshots"] == ["before.png", "after.png"]


def test_merge_with_master_drops_unknown_items():
    state = {
        "items": {
            "schema_markup": {"status": "done", "notes": "x", "screenshots": []},
            "removed_old_item": {"status": "done", "notes": "should be dropped"},
        }
    }
    merged = workbook.merge_with_master(state)
    assert "removed_old_item" not in merged["items"]
    assert merged["items"]["schema_markup"]["status"] == "done"


def test_merge_with_master_adds_new_items():
    """If the master gets a new item, existing workbooks should pick it up as todo."""
    state = {"items": {"schema_markup": {"status": "done", "notes": "x", "screenshots": []}}}
    merged = workbook.merge_with_master(state)
    # nap_consistency is in the master but not in the stored state — should default to todo
    assert merged["items"]["nap_consistency"]["status"] == "todo"


def test_merge_with_master_handles_none():
    merged = workbook.merge_with_master(None)
    assert set(merged["items"].keys()) == workbook.VALID_ITEM_IDS


def test_merge_with_master_handles_empty_dict():
    merged = workbook.merge_with_master({})
    assert set(merged["items"].keys()) == workbook.VALID_ITEM_IDS


# ---------------------------------------------------------------------------
# Screenshot path helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_screenshots_dir(monkeypatch):
    """Override SCREENSHOTS_DIR for tests so we don't touch the real filesystem."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(workbook, "SCREENSHOTS_DIR", tmp)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_safe_filename_strips_path_components():
    # os.path.basename takes only the final segment, so the path traversal
    # attempts get reduced to the leaf name.
    assert workbook.safe_filename("../../etc/passwd") == "passwd"
    assert workbook.safe_filename("/tmp/screenshot.png") == "screenshot.png"
    assert workbook.safe_filename("../../../../../../evil.png") == "evil.png"


def test_safe_filename_preserves_safe_chars():
    assert workbook.safe_filename("schema-before.png") == "schema-before.png"
    assert workbook.safe_filename("screen_01.jpg") == "screen_01.jpg"


def test_safe_filename_replaces_unsafe_chars():
    assert workbook.safe_filename("my screenshot!.png") == "my_screenshot_.png"


def test_safe_filename_handles_empty():
    assert workbook.safe_filename("") == "screenshot"
    assert workbook.safe_filename(None) == "screenshot"


def test_safe_filename_strips_leading_dots():
    assert workbook.safe_filename(".hidden.png") == "hidden.png"


def test_screenshot_dir_includes_audit_and_item(tmp_screenshots_dir):
    path = workbook.screenshot_dir(42, "schema_markup")
    assert path == os.path.join(tmp_screenshots_dir, "42", "schema_markup")


def test_screenshot_dir_rejects_unknown_item():
    with pytest.raises(ValueError, match="Unknown checklist item"):
        workbook.screenshot_dir(42, "../../etc/passwd")
    with pytest.raises(ValueError, match="Unknown checklist item"):
        workbook.screenshot_dir(42, "nonexistent")


def test_screenshot_dir_coerces_audit_id_to_int(tmp_screenshots_dir):
    """Audit ID is forced through int() to prevent path injection via the URL."""
    with pytest.raises(ValueError):
        workbook.screenshot_dir("../../bad", "schema_markup")


def test_ensure_screenshot_dir_creates_path(tmp_screenshots_dir):
    path = workbook.ensure_screenshot_dir(7, "faq_page")
    assert os.path.isdir(path)


def test_screenshot_path_combines_dir_and_filename(tmp_screenshots_dir):
    path = workbook.screenshot_path(7, "schema_markup", "before.png")
    assert path.endswith(os.path.join("7", "schema_markup", "before.png"))


def test_screenshot_path_sanitizes_filename(tmp_screenshots_dir):
    path = workbook.screenshot_path(7, "schema_markup", "../evil.png")
    assert "evil.png" in path
    assert ".." not in os.path.basename(path)


# ---------------------------------------------------------------------------
# Database CRUD
# ---------------------------------------------------------------------------

def test_get_workbook_returns_none_for_missing(app):
    assert database.get_workbook(9999) is None


def test_save_and_get_workbook(app, sample_form_data, sample_intake_data):
    audit_id = database.save_audit(sample_form_data, sample_intake_data)
    state = workbook.empty_workbook_state()
    state["items"]["schema_markup"]["status"] = "done"
    state["items"]["schema_markup"]["notes"] = "Added schema"

    database.save_workbook(audit_id, state)
    loaded = database.get_workbook(audit_id)

    assert loaded is not None
    assert loaded["audit_id"] == audit_id
    assert loaded["state"]["items"]["schema_markup"]["status"] == "done"
    assert loaded["state"]["items"]["schema_markup"]["notes"] == "Added schema"
    assert loaded["created_at"] is not None
    assert loaded["updated_at"] is not None


def test_save_workbook_updates_existing(app, sample_form_data, sample_intake_data):
    audit_id = database.save_audit(sample_form_data, sample_intake_data)
    state = workbook.empty_workbook_state()
    database.save_workbook(audit_id, state)

    state["items"]["nap_consistency"]["status"] = "done"
    database.save_workbook(audit_id, state)

    loaded = database.get_workbook(audit_id)
    assert loaded["state"]["items"]["nap_consistency"]["status"] == "done"


def test_save_workbook_rejects_orphan_audit(app):
    state = workbook.empty_workbook_state()
    with pytest.raises(ValueError, match="does not exist"):
        database.save_workbook(99999, state)


def test_save_workbook_rejects_non_dict_state(app, sample_form_data, sample_intake_data):
    audit_id = database.save_audit(sample_form_data, sample_intake_data)
    with pytest.raises(ValueError, match="must be a dict"):
        database.save_workbook(audit_id, "not a dict")


def test_delete_workbook(app, sample_form_data, sample_intake_data):
    audit_id = database.save_audit(sample_form_data, sample_intake_data)
    database.save_workbook(audit_id, workbook.empty_workbook_state())

    assert database.delete_workbook(audit_id) is True
    assert database.get_workbook(audit_id) is None


def test_delete_workbook_returns_false_when_missing(app):
    assert database.delete_workbook(99999) is False


def test_deleting_audit_cascades_to_workbook(app, sample_form_data, sample_intake_data):
    """When an audit is deleted, its workbook should be cleaned up too."""
    audit_id = database.save_audit(sample_form_data, sample_intake_data)
    database.save_workbook(audit_id, workbook.empty_workbook_state())

    database.delete_audit(audit_id)

    assert database.get_workbook(audit_id) is None
