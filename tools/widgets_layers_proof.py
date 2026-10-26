"""Unit proof for the widget layers: errors, repository, service and connection handling (no server)."""
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "proof-only-secret")
import widget_assets
from app import config, db
from app.errors import NotFound, ValidationFailed
from app.repositories import widgets as repo
from app.schemas import FormField, WidgetCreate, WidgetUpdate
from app.services import widgets as service

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
config.DB_PATH = os.path.join(tmp, "layers.db")
config.PUBLIC_BASE_URL = "http://example.test"
db.run_migrations()
FIELD = FormField(name="email", label="Email", type="email", required=True)

print("== connection handling")
try:
    with db.connection() as leaked:
        raise RuntimeError("boom")
except RuntimeError:
    pass
try:
    leaked.execute("SELECT 1")
    closed = False
except sqlite3.ProgrammingError:
    closed = True
check("the connection is closed even when the caller raises", closed)

with db.connection() as conn:
    conn.execute("INSERT INTO owners VALUES ('o1', 'o1@example.com', 'h', 't')")
    conn.execute("INSERT INTO owners VALUES ('o2', 'o2@example.com', 'h', 't')")
    conn.commit()

    print("== create and read")
    w = service.create(conn, "o1", WidgetCreate(type="signup_form", title="First", description="d", form_fields=[FIELD]))
    check("create returns the stored widget with its defaults",
          w["button_text"] == "Submit" and w["display_options"]["position"] == "bottom-right" and w["owner_id"] == "o1")
    check("the owner can read it back", service.get_owned(conn, w["id"], "o1") == w)
    e = raised(service.get_owned, conn, w["id"], "o2")
    check("another owner gets NotFound (404) with the same message as before",
          isinstance(e, NotFound) and e.status_code == 404 and e.detail == "Widget %s not found" % w["id"])
    e = raised(service.create, conn, "o1", WidgetCreate(type="nope", title="T", form_fields=[FIELD]))
    check("an unknown type is rejected with the same message",
          isinstance(e, ValidationFailed) and e.status_code == 400
          and e.detail == "Field 'type' must be one of ['cta_popover', 'signup_form']")
    e = raised(service.create, conn, "o1", WidgetCreate(type="signup_form", title="  ", form_fields=[FIELD]))
    check("a blank title is rejected", e is not None and e.detail == "Field 'title' is required")
    e = raised(service.create, conn, "o1", WidgetCreate(type="signup_form", title="T", form_fields=[]))
    check("empty form_fields is rejected on create",
          e is not None and e.detail == "Field 'form_fields' must have at least one field")

    print("== update")
    u = service.update(conn, w["id"], "o1", WidgetUpdate(title="Renamed"))
    check("update changes only what is given",
          u["title"] == "Renamed" and u["description"] == "d" and u["form_fields"] == w["form_fields"]
          and u["created_at"] == w["created_at"])
    u = service.update(conn, w["id"], "o1", WidgetUpdate(description=None))
    check("a null description means unchanged", u["description"] == "d")
    e = raised(service.update, conn, w["id"], "o1", WidgetUpdate(title="  "))
    check("a blank title is rejected on update", e is not None and e.detail == "Field 'title' cannot be empty")
    e = raised(service.update, conn, w["id"], "o2", WidgetUpdate(title="x"))
    check("another owner cannot update", isinstance(e, NotFound))
    u = service.update(conn, w["id"], "o1", WidgetUpdate(form_fields=[]))
    check("an empty form_fields list is still accepted on update (known gap, fixed in its own step)", u["form_fields"] == [])

    print("== list, embed, delete")
    service.create(conn, "o1", WidgetCreate(type="cta_popover", title="Second", form_fields=[FIELD]))
    check("list returns the newest first", [x["title"] for x in service.list_for_owner(conn, "o1")] == ["Second", "Renamed"])
    check("another owner's list is empty", service.list_for_owner(conn, "o2") == [])
    version = widget_assets.load()[1]
    expected = {"widget_id": w["id"],
                "snippet": '<script src="http://example.test/widget.js?id=%s&v=%s"></script>' % (w["id"], version)}
    check("the embed snippet is built from PUBLIC_BASE_URL and the script version",
          service.embed_snippet(conn, w["id"], "o1") == expected)
    check("another owner cannot get the embed snippet", isinstance(raised(service.embed_snippet, conn, w["id"], "o2"), NotFound))
    check("another owner cannot delete", isinstance(raised(service.delete, conn, w["id"], "o2"), NotFound))
    service.delete(conn, w["id"], "o1")
    check("the owner can delete, and the row is gone", repo.get_by_id(conn, w["id"]) is None)
    check("deleting twice is NotFound", isinstance(raised(service.delete, conn, w["id"], "o1"), NotFound))

shutil.rmtree(tmp, ignore_errors=True)
print("== result:", "ALL CHECKS PASSED" if not failures else "%d CHECK(S) FAILED" % len(failures))
sys.exit(1 if failures else 0)
