"""Behaviour safety net for refactors (characterization test).
Usage: python tools/smoke_proof.py <label>   e.g. baseline, step1
Output is deterministic: no ids, timestamps or secrets are printed."""
import difflib
import json
import os
import random
import secrets
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
LINES = []
RUN = random.randint(1, 250)
COUNTER = [0]
FIELDS = [{"name": "email", "label": "Email", "type": "email", "required": True}]


def out(text):
    print(text)
    LINES.append(text)


def req(method, path, body=None, token=None, headers=None, raw=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    h.update(headers or {})
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            status, payload = resp.status, resp.read()
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read()
        hdrs = {k.lower(): v for k, v in e.headers.items()}
    except OSError:
        return "ERR", None, {}
    try:
        return status, json.loads(payload), hdrs
    except ValueError:
        return status, payload, hdrs


def probe(what, method, path, **kw):
    s, d, h = req(method, path, **kw)
    out("%s -> %s" % (what, s))
    return s, d, h


def fresh_ip():
    COUNTER[0] += 1
    return "10.%d.%d.%d" % (RUN, COUNTER[0] // 250, COUNTER[0] % 250 + 1)


def submit(widget, fields, extra=None, raw=None, ip=None):
    data = {"widget_id": widget, "fields": fields}
    data.update(extra or {})
    return req("POST", "/submissions", body=data, raw=raw, headers={"X-Forwarded-For": ip or fresh_ip()})


def must(status, wanted, what):
    assert status == wanted, "setup failed at %s: got %s" % (what, status)


def field(d, key):
    return d.get(key) if isinstance(d, dict) else None


pw_a = secrets.token_urlsafe(12)
email_a = "smoke-a-%s@example.com" % uuid.uuid4().hex[:8]
email_b = "smoke-b-%s@example.com" % uuid.uuid4().hex[:8]

out("== basics")
probe("health", "GET", "/health")
s, _, h = probe("preflight", "OPTIONS", "/submissions", headers={"Origin": "http://localhost:9000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
out("  allow-origin=%s" % h.get("access-control-allow-origin"))

out("== auth")
s, d, _ = probe("signup A", "POST", "/auth/signup", body={"email": email_a, "password": pw_a})
must(s, 201, "signup A")
tok_a = d["access_token"]
s, d, _ = probe("signup B", "POST", "/auth/signup", body={"email": email_b, "password": secrets.token_urlsafe(12)})
must(s, 201, "signup B")
tok_b = d["access_token"]
probe("signup duplicate email", "POST", "/auth/signup", body={"email": email_a, "password": pw_a})
probe("signup short password", "POST", "/auth/signup", body={"email": "short-%s@example.com" % uuid.uuid4().hex[:8], "password": "short"})
probe("signup bad email", "POST", "/auth/signup", body={"email": "not-an-email", "password": pw_a})
probe("login wrong password", "POST", "/auth/login", body={"email": email_a, "password": "wrong-password-1"})
s, d, _ = probe("login ok", "POST", "/auth/login", body={"email": email_a, "password": pw_a})
must(s, 200, "login A")
probe("me with token", "GET", "/auth/me", token=tok_a)
probe("me without token", "GET", "/auth/me")
probe("me bad token", "GET", "/auth/me", token="garbage")

out("== widgets")
ids = {}
for name in ("A1", "A2", "A3"):
    s, d, _ = probe("create widget " + name, "POST", "/widgets", body={"type": "signup_form", "title": "Smoke " + name, "form_fields": FIELDS}, token=tok_a)
    must(s, 201, "create " + name)
    ids[name] = d["id"]
a1, a2, a3 = ids["A1"], ids["A2"], ids["A3"]
probe("create popover widget", "POST", "/widgets", body={"type": "cta_popover", "title": "Smoke popover", "form_fields": FIELDS, "display_options": {"color": "#123456", "position": "top-left"}}, token=tok_a)
probe("create widget bad type", "POST", "/widgets", body={"type": "nope", "title": "x", "form_fields": FIELDS}, token=tok_a)
probe("create widget no fields", "POST", "/widgets", body={"type": "signup_form", "title": "x", "form_fields": []}, token=tok_a)
probe("create widget no token", "POST", "/widgets", body={"type": "signup_form", "title": "x", "form_fields": FIELDS})
probe("list widgets", "GET", "/widgets", token=tok_a)
probe("get own widget", "GET", "/widgets/" + a1, token=tok_a)
probe("get other owner's widget", "GET", "/widgets/" + a1, token=tok_b)
probe("get unknown widget", "GET", "/widgets/does-not-exist", token=tok_a)
probe("update widget", "PUT", "/widgets/" + a1, body={"title": "Smoke A1 renamed"}, token=tok_a)
s, d, _ = probe("get after update", "GET", "/widgets/" + a1, token=tok_a)
out("  title=%s" % field(d, "title"))
probe("update other owner's widget", "PUT", "/widgets/" + a1, body={"title": "hijack"}, token=tok_b)
s, d, _ = probe("embed snippet", "GET", "/widgets/%s/embed" % a1, token=tok_a)
snip = field(d, "snippet") or ""
out("  snippet has id=%s and version=%s" % (("widget.js?id=" + a1) in snip, "&v=" in snip))

out("== public endpoints")
s, d, h = probe("public config", "GET", "/widgets/%s/config" % a1)
out("  keys=%s owner_id_exposed=%s cache=%s etag=%s" % (sorted(d), "owner_id" in d, h.get("cache-control"), bool(h.get("etag"))))
probe("public config conditional", "GET", "/widgets/%s/config" % a1, headers={"If-None-Match": h.get("etag")})
probe("public config unknown widget", "GET", "/widgets/does-not-exist/config")
s, _, h = probe("widget.js", "GET", "/widget.js?id=" + a1)
out("  type=%s cache=%s" % (h.get("content-type"), h.get("cache-control")))
version = h["etag"].strip('"')
s, _, h = probe("widget.js with version", "GET", "/widget.js?id=%s&v=%s" % (a1, version))
out("  cache=%s" % h.get("cache-control"))
probe("widget.js conditional", "GET", "/widget.js?id=%s&v=%s" % (a1, version), headers={"If-None-Match": '"%s"' % version})

out("== submissions")
s, d, _ = submit(a1, {"email": "ok@example.com"})
out("valid -> %s status=%s" % (s, field(d, "status")))
for what, fields in (("unknown field", {"email": "ok@example.com", "extra": "x"}), ("missing required field", {}), ("invalid email", {"email": "not-an-email"})):
    s, d, _ = submit(a1, fields)
    out("%s -> %s" % (what, s))
s, _, _ = submit(a1, {}, raw=b"not json")
out("body not json -> %s" % s)
s, _, _ = submit(a1, {}, raw=b"[1, 2]")
out("body is a json array -> %s" % s)
s, _, _ = submit("does-not-exist", {"email": "ok@example.com"})
out("unknown widget -> %s" % s)
big = json.dumps({"widget_id": a1, "fields": {"email": "x" * 20000}}).encode()
s, _, _ = submit(a1, {}, raw=big)
out("oversized body -> %s" % s)
s, d, _ = submit(a1, {"email": "bot@example.com"}, extra={"website": "http://spam.example"})
out("honeypot filled -> %s status=%s" % (s, field(d, "status")))

out("== rate limits")
same_ip = fresh_ip()
codes = [submit(a2, {"email": "r%d@example.com" % i}, ip=same_ip)[0] for i in range(6)]
out("one ip x6 -> %s" % ",".join(str(c) for c in codes))
s, _, h = submit(a2, {"email": "r7@example.com"}, ip=same_ip)
out("one ip, 7th request -> %s retry-after=%s" % (s, h.get("retry-after") is not None))
codes = [submit(a3, {"email": "w%d@example.com" % i})[0] for i in range(31)]
out("one widget x31 from different ips -> 201 x %d, 429 x %d" % (codes.count(201), codes.count(429)))

out("== dashboard")
s, d, _ = probe("dashboard owner A", "GET", "/dashboard", token=tok_a)
for w in sorted(d["widgets"], key=lambda w: w["title"]):
    out("  %s stored=%d" % (w["title"], w["stored_count"]))
out("  total_stored=%d" % d["total_stored"])
s, d, _ = probe("dashboard owner B", "GET", "/dashboard", token=tok_b)
out("  owner B widgets=%d total_stored=%d" % (len(d["widgets"]), d["total_stored"]))
probe("dashboard no token", "GET", "/dashboard")

out("== delete")
probe("delete other owner's widget", "DELETE", "/widgets/" + a1, token=tok_b)
probe("delete own widget", "DELETE", "/widgets/" + a1, token=tok_a)
probe("get deleted widget", "GET", "/widgets/" + a1, token=tok_a)
probe("public config of deleted widget", "GET", "/widgets/%s/config" % a1)
s, _, _ = submit(a1, {"email": "late@example.com"})
out("submit to deleted widget -> %s" % s)

path = "proof_smoke_%s.txt" % LABEL
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")
baseline = "proof_smoke_baseline.txt"
if LABEL != "baseline" and os.path.exists(baseline):
    old = open(baseline, encoding="utf-8").read().splitlines()
    diff = list(difflib.unified_diff(old, LINES, "baseline", LABEL, lineterm=""))
    if diff:
        print("== DIFFERS FROM BASELINE")
        print("\n".join(diff))
        sys.exit(1)
    print("== IDENTICAL to baseline (%d lines)" % len(LINES))

