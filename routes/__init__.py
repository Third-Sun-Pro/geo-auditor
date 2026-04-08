"""Route blueprints — register all with the Flask app."""

from routes.audit import audit_bp
from routes.history import history_bp
from routes.ui import ui_bp
from routes.workbook import workbook_bp


def register_blueprints(app):
    app.register_blueprint(audit_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(ui_bp)
    app.register_blueprint(workbook_bp)
