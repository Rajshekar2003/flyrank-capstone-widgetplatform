"""Unit proof for the submission layers (no server): parsing, validation, spam, geo, storage, side effect."""
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "proof-only-secret")
os.environ["GEO_MOCK_A"] = "ok"
os.environ["GEO_MOCK_B"] = ""
os.environ.pop("NOTIFY_MOCK", None)
from app import config, db
from app.errors import NotFound, PayloadTooLarge, TooManyRequests, ValidationFailed
from app.integrations import notify
from app.repositories import widgets as widgets_repo
from app.services import abuse
from app.services import submissions as service

failures = []
DEFS = {"email": {"name": "email", "label": "Email", "type": "email", "required": True},
        "company": {"name": "company", "label": "Company", "type": "text", "required": False}}


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


def attempt(coro):
    try:
        asyncio.run(coro)
    except Exception as e:
        return e
    return None


print("== body parsing and size")
check("a JSON object parses", service.parse_body(b'{"a": 1}') == {"a": 1})
e = raised(service.parse_body, b"not json")
check("invalid JSON is rejected", isinstance(e, ValidationFailed) and e.detail == "Body must be valid JSON")
e = raised(service.parse_body, b"\x80\x81")
check("bytes that are not UTF-8 are rejected the same way", e is not None and e.detail == "Body must be valid JSON")
e = raised(service.parse_body, b"[1, 2]")
check("a JSON array is rejected", e is not None and e.detail == "Body must be a JSON object")
e = raised(service.check_declared_size, "20000")
check("a declared length over the limit is 413 with the same message",
      isinstance(e, PayloadTooLarge) and e.status_code == 413 and e.detail == "Payload too large (max 10000 bytes)")
check("a missing or non-numeric Content-Length is not rejected here",
      raised(service.check_declared_size, None) is None and raised(service.check_declared_size, "abc") is None)
check("the real size is enforced too, and exactly at the limit is fine",
      raised(service.check_size, b"x" * 10_000) is None and isinstance(raised(service.check_size, b"x" * 10_001), PayloadTooLarge))

print("== field validation")
check("valid values are trimmed and returned",
      service.validate_fields(DEFS, {"email": "  a@b.co ", "company": " Acme "}) == {"email": "a@b.co", "company": "Acme"})
check("an empty optional field is left out",
      service.validate_fields(DEFS, {"email": "a@b.co", "company": "  "}) == {"email": "a@b.co"})
e = raised(service.validate_fields, DEFS, {"email": "a@b.co", "zeta": "1", "alpha": "2"})
check("unknown fields are listed alphabetically", e is not None and e.detail == "Unknown field(s): alpha, zeta")
e = raised(service.validate_fields, DEFS, {})
check("a missing required field is rejected", e is not None and e.detail == "Field 'email' is required")
e = raised(service.validate_fields, DEFS, {"email": 5})
check("a non-string value is rejected", e is not None and e.detail == "Field 'email' must be a string")
e = raised(service.validate_fields, DEFS, {"email": "a@b.co", "company": "x" * 501})
check("an over-long value is rejected", e is not None and e.detail == "Field 'company' is too long (max 500 characters)")
e = raised(service.validate_fields, DEFS, {"email": "not-an-email"})
check("a malformed email is rejected", e is not None and e.detail == "Field 'email' must be a valid email address")

tmp = tempfile.mkdtemp()
config.DB_PATH = os.path.join(tmp, "sub.db")
db.run_migrations()
queued = []


def enqueue(fn, *args):
    queued.append((fn, args))


with db.connection() as conn:
    conn.execute("INSERT INTO owners VALUES ('o1', 'o1@example.com', 'h', 't')")
    conn.commit()
    widgets_repo.insert(conn, "w1", "o1", "signup_form", "T", None, list(DEFS.values()), "Submit",
                        {"color": "#000000", "position": "bottom-right"}, "t")

    def stored(submission_id):
        return conn.execute("SELECT status, field_values, ip_address, country, city FROM submissions WHERE id = ?",
                            (submission_id,)).fetchone()

    def make(data, ip):
        return asyncio.run(service.create(conn, data, ip, enqueue))

    print("== create")
    e = attempt(service.create(conn, {"fields": {}}, "8.8.8.8", enqueue))
    check("a missing widget_id is rejected", isinstance(e, ValidationFailed) and e.detail == "Field 'widget_id' is required")
    e = attempt(service.create(conn, {"widget_id": "w1", "fields": []}, "8.8.8.8", enqueue))
    check("fields that are not an object are rejected", e is not None and e.detail == "Field 'fields' must be an object")
    e = attempt(service.create(conn, {"widget_id": "nope", "fields": {}}, "8.8.8.8", enqueue))
    check("an unknown widget is NotFound (404)", isinstance(e, NotFound) and e.status_code == 404 and e.detail == "Widget not found")
    out = make({"widget_id": "w1", "fields": {"email": "ok@example.com", "company": " Acme "}}, "8.8.8.8")
    row = stored(out["id"])
    check("a valid submission is stored with trimmed values and the geo result",
          out["status"] == "stored" and row["status"] == "stored"
          and json.loads(row["field_values"]) == {"email": "ok@example.com", "company": "Acme"}
          and row["country"] == "Mockland-A" and row["city"] == "Mockville-A" and row["ip_address"] == "8.8.8.8")
    check("exactly one webhook is queued, carrying the stored values",
          len(queued) == 1 and queued[0][0] is notify.notify_safely and queued[0][1][0]["submission_id"] == out["id"]
          and queued[0][1][0]["fields"] == {"email": "ok@example.com", "company": "Acme"})
    out = make({"widget_id": "w1", "fields": {"email": "p@example.com"}}, "10.1.2.3")
    row = stored(out["id"])
    check("a private address skips geo and stores an empty location", row["country"] is None and row["city"] is None)
    before = len(queued)
    out = make({"widget_id": "w1", "fields": {}, "website": "http://spam.example"}, "8.8.8.8")
    row = stored(out["id"])
    check("a filled honeypot says stored but is saved as flagged_spam with no values, no geo and no webhook",
          out["status"] == "stored" and row["status"] == "flagged_spam" and row["field_values"] == "{}"
          and row["country"] is None and len(queued) == before)
    e = attempt(service.create(conn, {"widget_id": "w1", "fields": {"email": "bad"}}, "10.1.2.3", enqueue))
    check("validation errors from the service keep the same message",
          e is not None and e.detail == "Field 'email' must be a valid email address")
    service.WIDGET_LIMITER = abuse.SlidingWindowLimiter(2, 60)
    results = [attempt(service.create(conn, {"widget_id": "w1", "fields": {"email": "l@example.com"}}, "10.1.2.3", enqueue))
               for _ in range(3)]
    check("the per-widget limit answers 429 with Retry-After on the third request",
          results[0] is None and results[1] is None and isinstance(results[2], TooManyRequests)
          and results[2].status_code == 429 and results[2].headers["Retry-After"].isdigit())

shutil.rmtree(tmp, ignore_errors=True)
print("== result:", "ALL CHECKS PASSED" if not failures else "%d CHECK(S) FAILED" % len(failures))
sys.exit(1 if failures else 0)
