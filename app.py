#!/usr/bin/env python3
"""
GEO Audit Report Generator - Web Application
Automated AI visibility auditing with PDF generation
"""

from flask import Flask

from database import init_db
from routes import register_blueprints


def create_app():
    app = Flask(__name__)
    init_db()
    register_blueprints(app)
    return app


app = create_app()

if __name__ == '__main__':
    print("=" * 50)
    print("GEO Audit Report Generator")
    print("Open http://127.0.0.1:5001 in your browser")
    print("=" * 50)
    app.run(debug=True, host='127.0.0.1', port=5001, threaded=True)
