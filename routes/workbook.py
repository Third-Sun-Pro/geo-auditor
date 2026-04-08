"""Workbook routes — implementation tracker per audit.

Endpoints:
    GET    /audits/<id>/workbook                          Load workbook (creates lazily)
    POST   /audits/<id>/workbook                          Save workbook state
    POST   /audits/<id>/workbook/screenshot               Upload a screenshot to an item
    DELETE /audits/<id>/workbook/screenshot/<item>/<file> Remove a screenshot
    GET    /audits/<id>/workbook/screenshot/<item>/<file> Serve a screenshot file
    GET    /audits/<id>/workbook/report                   Render the client deliverable HTML
"""

import os

from flask import Blueprint, request, jsonify, send_file, abort

import workbook as wb
from database import get_audit, get_workbook, save_workbook
from report import generate_workbook_report_html

workbook_bp = Blueprint('workbook', __name__)


def _audit_or_404(audit_id):
    audit = get_audit(audit_id)
    if not audit:
        abort(404, description=f"Audit {audit_id} not found")
    return audit


def _load_or_create_state(audit_id):
    """Return the current workbook state for an audit, merged with the master."""
    stored = get_workbook(audit_id)
    if stored:
        return wb.merge_with_master(stored["state"])
    return wb.empty_workbook_state()


@workbook_bp.route('/audits/<int:audit_id>/workbook', methods=['GET'])
def get_workbook_route(audit_id):
    """Load the workbook for an audit. Creates a fresh one if none exists yet."""
    _audit_or_404(audit_id)
    state = _load_or_create_state(audit_id)
    return jsonify({
        "audit_id": audit_id,
        "state": state,
        "checklist": wb.MASTER_CHECKLIST,
        "phase_labels": wb.PHASE_LABELS,
    })


@workbook_bp.route('/audits/<int:audit_id>/workbook', methods=['POST'])
def save_workbook_route(audit_id):
    """Save workbook state. Body: {"state": {...}}."""
    _audit_or_404(audit_id)
    payload = request.json or {}
    incoming = payload.get("state")
    if not isinstance(incoming, dict):
        return jsonify({"error": "Body must include a 'state' object"}), 400

    # Merge with master to drop unknown items / add new ones, then persist.
    merged = wb.merge_with_master(incoming)
    try:
        save_workbook(audit_id, merged)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"success": True, "state": merged})


@workbook_bp.route('/audits/<int:audit_id>/workbook/screenshot', methods=['POST'])
def upload_screenshot_route(audit_id):
    """Upload a screenshot for a checklist item.

    Multipart form fields:
        item_id  — checklist item the screenshot belongs to
        file     — the image file
    """
    _audit_or_404(audit_id)

    item_id = request.form.get("item_id", "")
    if not wb.is_valid_item_id(item_id):
        return jsonify({"error": f"Unknown checklist item: {item_id}"}), 400

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "No file provided"}), 400

    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in wb.ALLOWED_SCREENSHOT_EXTS:
        return jsonify({
            "error": f"Unsupported file type: {ext or '(none)'}. Allowed: {sorted(wb.ALLOWED_SCREENSHOT_EXTS)}"
        }), 400

    safe_name = wb.safe_filename(upload.filename)
    target_dir = wb.ensure_screenshot_dir(audit_id, item_id)
    target_path = os.path.join(target_dir, safe_name)

    # If a file with the same name already exists, suffix with an index so we
    # don't silently overwrite a previous screenshot.
    if os.path.exists(target_path):
        base, dot, suffix = safe_name.rpartition(".")
        i = 2
        while True:
            candidate = f"{base}_{i}.{suffix}" if dot else f"{safe_name}_{i}"
            candidate_path = os.path.join(target_dir, candidate)
            if not os.path.exists(candidate_path):
                safe_name = candidate
                target_path = candidate_path
                break
            i += 1

    upload.save(target_path)

    # Update the workbook state to include this screenshot in the item.
    state = _load_or_create_state(audit_id)
    item_state = state["items"][item_id]
    if safe_name not in item_state["screenshots"]:
        item_state["screenshots"].append(safe_name)
    save_workbook(audit_id, state)

    return jsonify({
        "success": True,
        "filename": safe_name,
        "item_id": item_id,
        "url": f"/audits/{audit_id}/workbook/screenshot/{item_id}/{safe_name}",
    })


@workbook_bp.route(
    '/audits/<int:audit_id>/workbook/screenshot/<item_id>/<filename>',
    methods=['GET']
)
def serve_screenshot_route(audit_id, item_id, filename):
    """Serve a screenshot file. Validates item_id and filename."""
    _audit_or_404(audit_id)
    if not wb.is_valid_item_id(item_id):
        abort(404)

    safe_name = wb.safe_filename(filename)
    path = os.path.join(wb.screenshot_dir(audit_id, item_id), safe_name)
    if not os.path.exists(path):
        abort(404)
    return send_file(path)


@workbook_bp.route(
    '/audits/<int:audit_id>/workbook/screenshot/<item_id>/<filename>',
    methods=['DELETE']
)
def delete_screenshot_route(audit_id, item_id, filename):
    """Remove a screenshot file and drop it from the workbook state."""
    _audit_or_404(audit_id)
    if not wb.is_valid_item_id(item_id):
        return jsonify({"error": "Unknown checklist item"}), 400

    safe_name = wb.safe_filename(filename)
    path = os.path.join(wb.screenshot_dir(audit_id, item_id), safe_name)
    if os.path.exists(path):
        os.unlink(path)

    state = _load_or_create_state(audit_id)
    item_state = state["items"][item_id]
    if safe_name in item_state["screenshots"]:
        item_state["screenshots"].remove(safe_name)
    save_workbook(audit_id, state)

    return jsonify({"success": True})


@workbook_bp.route('/audits/<int:audit_id>/workbook/report', methods=['GET'])
def workbook_report_route(audit_id):
    """Render the client-facing workbook deliverable as HTML."""
    audit = _audit_or_404(audit_id)
    state = _load_or_create_state(audit_id)
    html = generate_workbook_report_html(audit, state)
    return html
