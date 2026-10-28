"""Unit proof for the auth, dashboard and public-config layers (no server)."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "proof-only-secret")
from app import config, db
from app.errors import NotFound, Unauthorized, ValidationFailed
from app.repositories import submissions as submissions_repo
from app.repositories import widgets as widgets_repo
from app.security import require_owner, verify_password
from app.services import auth, dashboard
from app.services import widgets as widgets_service

failures = []


def check(label, ok):
    print(("  PASS " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def raised(fn, *args):
    try:
        fn(*args)
    except Exception as e:
        return e
    return None


tmp = tempfile.mkdtemp()
config.DB_PATH = os.path.join(tmp, "final.db")
db.run_migrations()

with db.connection() as conn:
    print("== auth")
    out = auth.signup(conn, "a@example.com", "correct horse")
    check("signup returns the owner id, the email and a token",
          set(out) == {"id", "email", "access_token"} and out["email"] == "a@example.com")
    check("the token resolves to the new owner", require_owner("Bearer " + out["access_token"]) == out["id"])
    row = conn.execute("SELECT password_hash FROM owners WHERE id = ?", (out["id"],)).fetchone()
    check("the password is stored hashed",
          "correct horse" not in row["password_hash"] and verify_password("correct horse", row["password_hash"]))
    e = raised(auth.signup, conn, "b@example.com", "short")
    check("a short password is rejected",
          isinstance(e, ValidationFailed) and e.detail == "Password must be at least 8 characters")
    e = raised(auth.signup, conn, "a@example.com", "another password")
    check("a duplicate email is rejected",
          isinstance(e, ValidationFailed) and e.detail == "An account with this email already exists")
    login = auth.login(conn, "a@example.com", "correct horse")
    check("login returns a token for the same owner",
          set(login) == {"access_token"} and require_owner("Bearer " + login["access_token"]) == out["id"])
    wrong = raised(auth.login, conn, "a@example.com", "wrong password")
    unknown = raised(auth.login, conn, "nobody@example.com", "whatever password")
    check("a wrong password is Unauthorized (401) with the same message as before",
          isinstance(wrong, Unauthorized) and wrong.status_code == 401 and wrong.detail == "Invalid email or password")
    check("an unknown email gets the identical error, so accounts cannot be enumerated by message",
          isinstance(unknown, Unauthorized) and unknown.detail == wrong.detail)

    print("== dashboard")
    owner_a = out["id"]
    owner_b = auth.signup(conn, "c@example.com", "another long one")["id"]
    form = [{"name": "email", "label": "Email", "type": "email", "required": True}]
    for wid, title, created in (("w1", "One", "t1"), ("w2", "Two", "t2"), ("w3", "Three", "t3")):
        widgets_repo.insert(conn, wid, owner_a, "signup_form", title, None, form, "Submit",
                            {"color": "#000000", "position": "bottom-right"}, created)
    rows = (("w1", "stored"), ("w1", "stored"), ("w1", "stored"), ("w1", "flagged_spam"), ("w1", "flagged_spam"), ("w2", "stored"))
    for i, (wid, status) in enumerate(rows):
        submissions_repo.insert(conn, "s%d" % i, wid, {}, "1.2.3.4", None, None, status, "2026-01-0%d" % (i + 1))
    summary = dashboard.summary(conn, owner_a)
    counts = {w["title"]: w["stored_count"] for w in summary["widgets"]}
    check("only stored submissions are counted, and an empty widget shows 0",
          counts == {"One": 3, "Two": 1, "Three": 0} and summary["total_stored"] == 4)
    check("widgets come back oldest first", [w["title"] for w in summary["widgets"]] == ["One", "Two", "Three"])
    check("last_submission_at is the newest stored submission, and None when there is none",
          [w["last_submission_at"] for w in summary["widgets"]] == ["2026-01-03", "2026-01-06", None])
    check("another owner sees nothing of these widgets", dashboard.summary(conn, owner_b) == {"total_stored": 0, "widgets": []})

    print("== public config")
    cfg = widgets_service.public_config(conn, "w1")
    check("the public config exposes exactly what a visitor needs",
          set(cfg) == {"id", "type", "title", "description", "form_fields", "button_text", "display_options"})
    e = raised(widgets_service.public_config, conn, "nope")
    check("an unknown widget is NotFound with the public message",
          isinstance(e, NotFound) and e.status_code == 404 and e.detail == "Widget not found")

shutil.rmtree(tmp, ignore_errors=True)
print("== result:", "ALL CHECKS PASSED" if not failures else "%d CHECK(S) FAILED" % len(failures))
sys.exit(1 if failures else 0)
