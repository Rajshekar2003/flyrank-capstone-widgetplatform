import json
import secrets
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
failures = []
counter = [0]


def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    return _send(method, path, data, headers)


def _send(method, path, data, headers):
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


def check(label, ok):
    print(("  PASS " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def new_owner(tag):
    email = "dash-%s-%s@example.com" % (tag, uuid.uuid4().hex[:8])
    status, out = call("POST", "/auth/signup", {"email": email, "password": secrets.token_urlsafe(12)})
    assert status == 201, "signup failed: %s %s" % (status, out)
    return out["access_token"]


def new_widget(token, title):
    fields = [{"name": "email", "label": "Email", "type": "email", "required": True}]
    status, out = call("POST", "/widgets", {"type": "signup_form", "title": title, "form_fields": fields}, token)
    assert status == 201, "widget failed: %s %s" % (status, out)
    return out["id"]


def submit(widget, spam=False):
    counter[0] += 1
    ip = "10.77.%d.%d" % (counter[0] // 250, counter[0] % 250 + 1)
    data = {"widget_id": widget, "fields": {"email": "p%d@example.com" % counter[0]}}
    if spam:
        data["website"] = "http://spam.example"
        data["fields"]["website"] = "http://spam.example"
    body = json.dumps(data).encode()
    status, _ = _send("POST", "/submissions", body, {"Content-Type": "application/json", "X-Forwarded-For": ip})
    assert status == 201, "submit failed: %s" % status


print("== setup")
tok_a, tok_b = new_owner("a"), new_owner("b")
a1, a2 = new_widget(tok_a, "Proof A1"), new_widget(tok_a, "Proof A2")
a3 = new_widget(tok_a, "Proof A3 empty")
b1 = new_widget(tok_b, "Proof B1")
for _ in range(3):
    submit(a1)
for _ in range(2):
    submit(a1, spam=True)
submit(a2)
for _ in range(2):
    submit(b1)
submit(b1, spam=True)
print("== raw rows in the database (this run only)")
db = sqlite3.connect("widgets.db")
for r in db.execute("select w.title, s.status, count(*) from submissions s join widgets w on w.id = s.widget_id "
                    "where s.widget_id in (?, ?, ?, ?) group by w.title, s.status order by w.title, s.status",
                    (a1, a2, a3, b1)):
    print("  %s | %s | %d" % r)

print("== dashboard for owner A")
status, dash = call("GET", "/dashboard", token=tok_a)
by_title = {w["title"]: w for w in dash["widgets"]} if status == 200 else {}
for w in (dash["widgets"] if status == 200 else []):
    print("  %s (%s): stored_count=%d" % (w["title"], w["type"], w["stored_count"]))
print("  total_stored:", dash.get("total_stored") if dash else None)
check("owner A gets 200", status == 200)
check("A1 counts 3 stored and ignores the 2 flagged_spam rows", by_title.get("Proof A1", {}).get("stored_count") == 3)
check("A2 counts 1", by_title.get("Proof A2", {}).get("stored_count") == 1)
check("empty widget A3 is listed with 0", by_title.get("Proof A3 empty", {}).get("stored_count") == 0)
check("total_stored is 4", dash.get("total_stored") == 4)
check("owner A does not see owner B's widget", b1 not in [w["id"] for w in dash["widgets"]])

print("== dashboard for owner B")
status, dash_b = call("GET", "/dashboard", token=tok_b)
print("  widgets:", [(w["title"], w["stored_count"]) for w in dash_b["widgets"]], "| total_stored:", dash_b["total_stored"])
check("owner B sees only their own widget", [w["title"] for w in dash_b["widgets"]] == ["Proof B1"])
check("owner B counts 2 stored and ignores 1 flagged_spam", dash_b["total_stored"] == 2)
check("owner B does not see owner A's widgets", not {a1, a2, a3} & {w["id"] for w in dash_b["widgets"]})

print("== authentication")
status, _ = call("GET", "/dashboard")
print("  no token ->", status)
check("no token is rejected (401 or 403)", status in (401, 403))
status, _ = call("GET", "/dashboard", token="garbage")
print("  bad token ->", status)
check("bad token is rejected (401 or 403)", status in (401, 403))

print("== result:", "ALL CHECKS PASSED" if not failures else "%d CHECK(S) FAILED" % len(failures))
sys.exit(1 if failures else 0)
