"""Proof for the migration runner (no server needed). Uses throwaway database files."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "proof-only-secret")
from app import config, db

failures = []


def check(label, ok):
    print(("  PASS " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def use(path):
    if os.path.exists(path):
        os.remove(path)
    config.DB_PATH = path


def names(path):
    conn = sqlite3.connect(path)
    found = {r[0] for r in conn.execute("select name from sqlite_master where type in ('table', 'index')")}
    conn.close()
    return found


def versions(path):
    conn = sqlite3.connect(path)
    rows = conn.execute("select version, applied_at from schema_migrations order by version").fetchall()
    conn.close()
    return rows


print("== fresh database")
P1 = "proof_migrate_fresh.db"
use(P1)
db.run_migrations()
check("owners, widgets, submissions and schema_migrations exist",
      {"owners", "widgets", "submissions", "schema_migrations"} <= names(P1))
check("both indexes exist", {"idx_widgets_owner", "idx_submissions_widget"} <= names(P1))
first = versions(P1)
check("version 1 recorded", [v for v, _ in first] == [1])
db.run_migrations()
check("a second run changes nothing", versions(P1) == first)

print("== existing database with data (the situation of widgets.db today)")
P2 = "proof_migrate_existing.db"
use(P2)
old = sqlite3.connect(P2)
old.executescript("""
CREATE TABLE owners (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE widgets (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, type TEXT NOT NULL, title TEXT NOT NULL, description TEXT, form_fields TEXT NOT NULL, button_text TEXT NOT NULL, display_options TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY (owner_id) REFERENCES owners(id));
CREATE INDEX idx_widgets_owner ON widgets(owner_id);
CREATE TABLE submissions (id TEXT PRIMARY KEY, widget_id TEXT NOT NULL, field_values TEXT NOT NULL, ip_address TEXT, country TEXT, city TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY (widget_id) REFERENCES widgets(id) ON DELETE CASCADE);
CREATE INDEX idx_submissions_widget ON submissions(widget_id);
INSERT INTO owners VALUES ('o1', 'o1@example.com', 'hash', 't');
INSERT INTO widgets VALUES ('w1', 'o1', 'signup_form', 'Old widget', NULL, '[]', 'Submit', '{}', 't');
INSERT INTO submissions VALUES ('s1', 'w1', '{}', '1.2.3.4', NULL, NULL, 'stored', 't');
""")
old.commit()
old.close()
db.run_migrations()
conn = sqlite3.connect(P2)
counts = [conn.execute("select count(*) from " + t).fetchone()[0] for t in ("owners", "widgets", "submissions")]
conn.close()
check("existing rows are untouched (1 owner, 1 widget, 1 submission)", counts == [1, 1, 1])
check("version 1 recorded on the existing database", [v for v, _ in versions(P2)] == [1])

print("== a failing migration rolls back completely")
good = list(db.MIGRATIONS)
db.MIGRATIONS.append((2, "broken", ["CREATE TABLE half_done (x TEXT)", "THIS IS NOT SQL"]))
failed = False
try:
    db.run_migrations()
except Exception:
    failed = True
check("the runner raises on a broken migration", failed)
check("the table created before the error was rolled back", "half_done" not in names(P2))
check("version 2 was not recorded and version 1 is still there", [v for v, _ in versions(P2)] == [1])
db.MIGRATIONS[:] = good + [(2, "fixed", ["CREATE TABLE fixed_table (x TEXT)"])]
db.run_migrations()
check("after fixing it, version 2 applies", [v for v, _ in versions(P2)] == [1, 2] and "fixed_table" in names(P2))

for path in (P1, P2):
    os.remove(path)
print("== result:", "ALL CHECKS PASSED" if not failures else "%d CHECK(S) FAILED" % len(failures))
sys.exit(1 if failures else 0)
