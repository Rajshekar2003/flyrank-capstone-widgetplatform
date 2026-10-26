"""Characterization of the owner widget endpoints: response bodies and error messages.
Usage: python tools/detail_proof.py <label>   (writes proof_detail_<label>.txt and compares with the baseline)
Output is deterministic: ids and timestamps are replaced by placeholders."""
import difflib
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime

BASE = os.environ.get("PROOF_BASE", "http://127.0.0.1:8000")
LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
LINES = []
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+00:00|Z)")
VER_RE = re.compile(r"v=[0-9a-f]{12}")
EMAIL = {"name": "email", "label": "Email", "type": "email", "required": True}
COMPANY = {"name": "company", "label": "Company", "type": "text"}


def out(text):
    print(text)
    LINES.append(text)


def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None
    return status, parsed, raw


def probe(what, method, path, body=None, token=None):
    status, parsed, raw = req(method, path, body, token)
    if status == 422 and isinstance(parsed, dict) and isinstance(parsed.get("detail"), list):
        text = str([(e.get("loc"), e.get("type")) for e in parsed["detail"]])
    elif parsed is None:
        text = "<%d bytes>" % len(raw)
    else:
        text = json.dumps(parsed, sort_keys=True)
    text = VER_RE.sub("v=<ver>", TIME_RE.sub("<time>", UUID_RE.sub("<id>", text)))
    out("%s -> %s %s" % (what, status, text))
    return status, parsed


def signup(tag):
    status, parsed, _ = req("POST", "/auth/signup", {"email": "detail-%s-%s@example.com" % (tag, uuid.uuid4().hex[:8]), "password": secrets.token_urlsafe(12)})
    assert status == 201, "signup failed: %s" % status
    return parsed["access_token"], parsed["id"]


tok_a, owner_a = signup("a")
tok_b, _ = signup("b")

out("== create")
s, created = probe("create full", "POST", "/widgets", {"type": "cta_popover", "title": "Detail widget", "description": "Short text", "form_fields": [EMAIL, COMPANY], "button_text": "Send", "display_options": {"color": "#abcdef", "position": "top-left"}}, tok_a)
assert s == 201, "create failed: %s" % s
w1 = created["id"]
out("  owner is the caller=%s, created_at parses as a time=%s" % (created["owner_id"] == owner_a, bool(datetime.fromisoformat(created["created_at"]))))
s, d = probe("create with defaults", "POST", "/widgets", {"type": "signup_form", "title": "Defaults", "form_fields": [EMAIL]}, tok_a)
assert s == 201, "create failed: %s" % s
w2 = d["id"]
probe("create bad type", "POST", "/widgets", {"type": "nope", "title": "x", "form_fields": [EMAIL]}, tok_a)
probe("create blank title", "POST", "/widgets", {"type": "signup_form", "title": "   ", "form_fields": [EMAIL]}, tok_a)
probe("create no fields", "POST", "/widgets", {"type": "signup_form", "title": "x", "form_fields": []}, tok_a)
probe("create missing title", "POST", "/widgets", {"type": "signup_form", "form_fields": [EMAIL]}, tok_a)
probe("create missing type", "POST", "/widgets", {"title": "x", "form_fields": [EMAIL]}, tok_a)
probe("create field without label", "POST", "/widgets", {"type": "signup_form", "title": "x", "form_fields": [{"name": "email", "type": "email"}]}, tok_a)
probe("create empty body", "POST", "/widgets", {}, tok_a)
probe("create no token", "POST", "/widgets", {"type": "signup_form", "title": "x", "form_fields": [EMAIL]})
probe("create bad token", "POST", "/widgets", {"type": "signup_form", "title": "x", "form_fields": [EMAIL]}, "garbage")

out("== list")
probe("list as A", "GET", "/widgets", None, tok_a)
probe("list as B", "GET", "/widgets", None, tok_b)
probe("list no token", "GET", "/widgets")

out("== get")
s, d = probe("get own", "GET", "/widgets/" + w1, None, tok_a)
out("  same body as create=%s" % (d == created))
probe("get as other owner", "GET", "/widgets/" + w1, None, tok_b)
probe("get unknown", "GET", "/widgets/does-not-exist", None, tok_a)
probe("get no token", "GET", "/widgets/" + w1)

out("== update")
probe("update title", "PUT", "/widgets/" + w1, {"title": "Renamed"}, tok_a)
probe("update blank title", "PUT", "/widgets/" + w1, {"title": "   "}, tok_a)
probe("update title of the wrong type", "PUT", "/widgets/" + w1, {"title": 5}, tok_a)
probe("update description", "PUT", "/widgets/" + w1, {"description": "New text"}, tok_a)
probe("update description to null (means unchanged)", "PUT", "/widgets/" + w1, {"description": None}, tok_a)
probe("update button and display options", "PUT", "/widgets/" + w1, {"button_text": "Go", "display_options": {"color": "#000000"}}, tok_a)
probe("update form fields", "PUT", "/widgets/" + w1, {"form_fields": [EMAIL]}, tok_a)
probe("update form fields to an empty list", "PUT", "/widgets/" + w1, {"form_fields": []}, tok_a)
probe("update ignores unknown keys", "PUT", "/widgets/" + w1, {"type": "signup_form", "owner_id": "x"}, tok_a)
probe("update empty body", "PUT", "/widgets/" + w1, {}, tok_a)
probe("update as other owner", "PUT", "/widgets/" + w1, {"title": "hijack"}, tok_b)
probe("update unknown", "PUT", "/widgets/does-not-exist", {"title": "x"}, tok_a)
probe("update no token", "PUT", "/widgets/" + w1, {"title": "x"})
probe("get after the updates", "GET", "/widgets/" + w1, None, tok_a)

out("== embed")
probe("embed own", "GET", "/widgets/%s/embed" % w1, None, tok_a)
probe("embed as other owner", "GET", "/widgets/%s/embed" % w1, None, tok_b)
probe("embed unknown", "GET", "/widgets/does-not-exist/embed", None, tok_a)
probe("embed no token", "GET", "/widgets/%s/embed" % w1)

out("== delete")
probe("delete as other owner", "DELETE", "/widgets/" + w1, None, tok_b)
probe("delete own", "DELETE", "/widgets/" + w1, None, tok_a)
probe("delete again", "DELETE", "/widgets/" + w1, None, tok_a)
probe("get after delete", "GET", "/widgets/" + w1, None, tok_a)
probe("delete no token", "DELETE", "/widgets/" + w2)
probe("delete the second widget", "DELETE", "/widgets/" + w2, None, tok_a)
probe("list after deleting everything", "GET", "/widgets", None, tok_a)

with open("proof_detail_%s.txt" % LABEL, "w", encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")
baseline = "proof_detail_baseline.txt"
if LABEL != "baseline" and os.path.exists(baseline):
    old = open(baseline, encoding="utf-8").read().splitlines()
    diff = list(difflib.unified_diff(old, LINES, "baseline", LABEL, lineterm=""))
    if diff:
        print("== DIFFERS FROM BASELINE")
        print("\n".join(diff))
        sys.exit(1)
    print("== IDENTICAL to baseline (%d lines)" % len(LINES))
