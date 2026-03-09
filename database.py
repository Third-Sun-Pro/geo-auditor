"""Database — SQLite connection, schema, and CRUD operations."""

import os
import re
import json
import sqlite3

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'audits.db')


def get_db():
    """Get a database connection."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    """Create tables if they don't exist."""
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            client_website TEXT,
            industry TEXT,
            audit_date TEXT,
            visibility_percentage REAL,
            package_type TEXT,
            form_data TEXT NOT NULL,
            intake_data TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_audits_client_name ON audits(client_name)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_audits_created_at ON audits(created_at)')
    db.commit()
    db.close()


def save_audit(form_data, intake_data, audit_id=None):
    """Save or update an audit. Returns the audit_id."""
    client = form_data.get('client', {})
    client_name = client.get('name', '').strip()

    if not client_name:
        raise ValueError("Client name is required to save")

    # Extract visibility percentage
    visibility_str = form_data.get('visibility_level', '')
    visibility_pct = None
    pct_match = re.search(r'(\d+\.?\d*)\s*%', visibility_str)
    if pct_match:
        visibility_pct = float(pct_match.group(1))
    if visibility_pct is None:
        queries = form_data.get('queries', [])
        total = sum(q.get('score', 0) for q in queries)
        max_s = len(queries) * 12
        if max_s > 0:
            visibility_pct = round((total / max_s) * 100, 1)

    db = get_db()
    try:
        if audit_id:
            db.execute('''
                UPDATE audits
                SET client_name = ?, client_website = ?, industry = ?,
                    audit_date = ?, visibility_percentage = ?, package_type = ?,
                    form_data = ?, intake_data = ?, updated_at = datetime('now')
                WHERE id = ?
            ''', (
                client_name,
                client.get('website', ''),
                client.get('industry', ''),
                client.get('audit_date', ''),
                visibility_pct,
                client.get('package', ''),
                json.dumps(form_data),
                json.dumps(intake_data),
                audit_id
            ))
        else:
            db.execute('''
                INSERT INTO audits
                    (client_name, client_website, industry, audit_date,
                     visibility_percentage, package_type, form_data, intake_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                client_name,
                client.get('website', ''),
                client.get('industry', ''),
                client.get('audit_date', ''),
                visibility_pct,
                client.get('package', ''),
                json.dumps(form_data),
                json.dumps(intake_data)
            ))
            audit_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

        db.commit()
        return audit_id
    finally:
        db.close()


def list_audits():
    """Return summary list of all saved audits."""
    db = get_db()
    try:
        rows = db.execute('''
            SELECT id, client_name, client_website, industry, audit_date,
                   visibility_percentage, package_type, created_at, updated_at
            FROM audits
            ORDER BY updated_at DESC
        ''').fetchall()

        return [{
            "id": row["id"],
            "client_name": row["client_name"],
            "client_website": row["client_website"],
            "industry": row["industry"],
            "audit_date": row["audit_date"],
            "visibility_percentage": row["visibility_percentage"],
            "package_type": row["package_type"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        } for row in rows]
    finally:
        db.close()


def get_audit(audit_id):
    """Return full audit data or None."""
    db = get_db()
    try:
        row = db.execute('SELECT * FROM audits WHERE id = ?', (audit_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "form_data": json.loads(row["form_data"]),
            "intake_data": json.loads(row["intake_data"]) if row["intake_data"] else {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
    finally:
        db.close()


def delete_audit(audit_id):
    """Delete an audit. Returns True if deleted, False if not found."""
    db = get_db()
    try:
        result = db.execute('DELETE FROM audits WHERE id = ?', (audit_id,))
        db.commit()
        return result.rowcount > 0
    finally:
        db.close()
