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
            previous_audit_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_audits_client_name ON audits(client_name)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_audits_created_at ON audits(created_at)')

    # Migration: add previous_audit_id column to existing databases
    try:
        db.execute('ALTER TABLE audits ADD COLUMN previous_audit_id INTEGER')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: add is_final and final_at columns
    try:
        db.execute('ALTER TABLE audits ADD COLUMN is_final INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    try:
        db.execute('ALTER TABLE audits ADD COLUMN final_at TEXT')
    except sqlite3.OperationalError:
        pass

    db.commit()
    db.close()


def save_audit(form_data, intake_data, audit_id=None, previous_audit_id=None):
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
                    form_data = ?, intake_data = ?, previous_audit_id = ?,
                    updated_at = datetime('now')
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
                previous_audit_id,
                audit_id
            ))
        else:
            db.execute('''
                INSERT INTO audits
                    (client_name, client_website, industry, audit_date,
                     visibility_percentage, package_type, form_data, intake_data,
                     previous_audit_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                client_name,
                client.get('website', ''),
                client.get('industry', ''),
                client.get('audit_date', ''),
                visibility_pct,
                client.get('package', ''),
                json.dumps(form_data),
                json.dumps(intake_data),
                previous_audit_id
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
                   visibility_percentage, package_type, previous_audit_id,
                   is_final, final_at, created_at, updated_at
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
            "previous_audit_id": row["previous_audit_id"],
            "is_final": bool(row["is_final"]),
            "final_at": row["final_at"],
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
            "previous_audit_id": row["previous_audit_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
    finally:
        db.close()


def get_comparison(current_id, previous_id):
    """Compare two audits and return the delta."""
    current = get_audit(current_id)
    previous = get_audit(previous_id)

    if not current or not previous:
        return None

    cur_fd = current["form_data"]
    prev_fd = previous["form_data"]

    # Overall percentage
    cur_queries = cur_fd.get("queries", [])
    prev_queries = prev_fd.get("queries", [])
    cur_total = sum(q.get("score", 0) for q in cur_queries)
    prev_total = sum(q.get("score", 0) for q in prev_queries)
    cur_max = len(cur_queries) * 12
    prev_max = len(prev_queries) * 12
    cur_pct = (cur_total / cur_max * 100) if cur_max > 0 else 0
    prev_pct = (prev_total / prev_max * 100) if prev_max > 0 else 0

    # Platform comparison
    cur_platforms = cur_fd.get("platforms", {})
    prev_platforms = prev_fd.get("platforms", {})
    platform_changes = {}
    for p in ["chatgpt", "claude", "gemini", "perplexity"]:
        cur_p = cur_platforms.get(p, {})
        prev_p = prev_platforms.get(p, {})
        cur_score = cur_p.get("score", 0)
        prev_score = prev_p.get("score", 0)
        cur_p_max = cur_p.get("max", 30)
        prev_p_max = prev_p.get("max", 30)
        cur_p_pct = (cur_score / cur_p_max * 100) if cur_p_max > 0 else 0
        prev_p_pct = (prev_score / prev_p_max * 100) if prev_p_max > 0 else 0
        platform_changes[p] = {
            "previous": round(prev_p_pct, 1),
            "current": round(cur_p_pct, 1),
            "change": round(cur_p_pct - prev_p_pct, 1)
        }

    # Query-level comparison (match by query text)
    prev_by_query = {q.get("query", ""): q for q in prev_queries}
    query_changes = []
    for q in cur_queries:
        query_text = q.get("query", "")
        prev_q = prev_by_query.get(query_text)
        if prev_q:
            change = q.get("score", 0) - prev_q.get("score", 0)
            query_changes.append({
                "query": query_text,
                "type": q.get("type", ""),
                "previous_score": prev_q.get("score", 0),
                "current_score": q.get("score", 0),
                "change": change
            })

    # Sort: biggest improvements first, then biggest declines
    query_changes.sort(key=lambda x: x["change"], reverse=True)

    return {
        "previous_audit_date": prev_fd.get("client", {}).get("audit_date", ""),
        "current_audit_date": cur_fd.get("client", {}).get("audit_date", ""),
        "previous_percentage": round(prev_pct, 1),
        "current_percentage": round(cur_pct, 1),
        "percentage_change": round(cur_pct - prev_pct, 1),
        "previous_total": prev_total,
        "current_total": cur_total,
        "platform_changes": platform_changes,
        "query_changes": query_changes,
        "queries_improved": len([q for q in query_changes if q["change"] > 0]),
        "queries_declined": len([q for q in query_changes if q["change"] < 0]),
        "queries_unchanged": len([q for q in query_changes if q["change"] == 0]),
    }


def mark_final(audit_id, is_final=True):
    """Mark or unmark an audit as final. Returns True if updated."""
    db = get_db()
    try:
        final_at = "datetime('now')" if is_final else "NULL"
        result = db.execute(
            f'UPDATE audits SET is_final = ?, final_at = {final_at} WHERE id = ?',
            (1 if is_final else 0, audit_id)
        )
        db.commit()
        return result.rowcount > 0
    finally:
        db.close()


def list_finals_due(days=30):
    """Return final audits where final_at is older than `days` days ago."""
    db = get_db()
    try:
        rows = db.execute('''
            SELECT id, client_name, client_website, industry, audit_date,
                   visibility_percentage, package_type, is_final, final_at,
                   created_at, updated_at
            FROM audits
            WHERE is_final = 1
              AND final_at <= datetime('now', ? || ' days')
        ''', (f'-{days}',)).fetchall()

        return [{
            "id": row["id"],
            "client_name": row["client_name"],
            "client_website": row["client_website"],
            "industry": row["industry"],
            "visibility_percentage": row["visibility_percentage"],
            "final_at": row["final_at"],
            "days_since_final": days
        } for row in rows]
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
