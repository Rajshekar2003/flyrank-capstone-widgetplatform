"""SQLite connection and a small schema-migration runner."""
import sqlite3
from datetime import datetime, timezone

from app import config

# (version, name, statements). Never edit an applied migration: add a new one.
MIGRATIONS = [
    (1, "baseline: owners, widgets, submissions", [
        """CREATE TABLE IF NOT EXISTS owners (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS widgets (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            form_fields TEXT NOT NULL,
            button_text TEXT NOT NULL,
            display_options TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES owners(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_widgets_owner ON widgets(owner_id)",
        """CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            widget_id TEXT NOT NULL,
            field_values TEXT NOT NULL,
            ip_address TEXT,
            country TEXT,
            city TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (widget_id) REFERENCES widgets(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_submissions_widget ON submissions(widget_id)",
    ]),
]


def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_migrations():
    """Apply every migration not yet recorded. Safe to call on every start."""
    conn = get_db()
    conn.isolation_level = None  # explicit transactions below
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        for version, name, statements in MIGRATIONS:
            conn.execute("BEGIN IMMEDIATE")
            try:
                done = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone()
                if done is None:
                    for statement in statements:
                        conn.execute(statement)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (version, name, datetime.now(timezone.utc).isoformat()),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
