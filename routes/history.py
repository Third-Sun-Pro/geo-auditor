"""History routes — save, list, load, delete, and compare audits."""

from flask import Blueprint, request, jsonify

from database import save_audit, list_audits, get_audit, delete_audit, get_comparison

history_bp = Blueprint('history', __name__)


@history_bp.route('/save-audit', methods=['POST'])
def save_audit_route():
    """Save or update an audit in the database."""
    data = request.json
    form_data = data.get('form_data', {})
    intake_data = data.get('intake_data', {})
    audit_id = data.get('audit_id')
    previous_audit_id = data.get('previous_audit_id')

    try:
        result_id = save_audit(form_data, intake_data, audit_id, previous_audit_id)
        return jsonify({"success": True, "audit_id": result_id})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@history_bp.route('/audits', methods=['GET'])
def list_audits_route():
    """Return summary list of all saved audits."""
    return jsonify({"audits": list_audits()})


@history_bp.route('/audits/<int:audit_id>', methods=['GET'])
def get_audit_route(audit_id):
    """Return full audit data for loading into the form."""
    audit = get_audit(audit_id)
    if not audit:
        return jsonify({"error": "Audit not found"}), 404
    return jsonify(audit)


@history_bp.route('/audits/<int:audit_id>', methods=['DELETE'])
def delete_audit_route(audit_id):
    """Delete a saved audit."""
    if delete_audit(audit_id):
        return jsonify({"success": True})
    return jsonify({"error": "Audit not found"}), 404


@history_bp.route('/audits/<int:current_id>/compare/<int:previous_id>', methods=['GET'])
def compare_audits_route(current_id, previous_id):
    """Compare two audits and return the delta."""
    comparison = get_comparison(current_id, previous_id)
    if not comparison:
        return jsonify({"error": "One or both audits not found"}), 404
    return jsonify({"success": True, "comparison": comparison})
