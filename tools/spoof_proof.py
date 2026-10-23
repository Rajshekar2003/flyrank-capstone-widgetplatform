"""Live proof: forged X-Forwarded-For values must not dodge the per-IP rate limit.
Usage: python tools/spoof_proof.py <label>   (writes proof_spoof_<label>.txt)"""
import json
import random
import secrets
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
LINES = []


def out(text):
    print(text)
    LINES.append(text)


def call(method, path, body=None, token=None, xff=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if xff:
        headers["X-Forwarded-For"] = xff
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


status, d = call("POST", "/auth/signup", {"email": "spoof-%s@example.com" % uuid.uuid4().hex[:8], "password": secrets.token_urlsafe(12)})
assert status == 201, "signup failed: %s" % status
token = d["access_token"]
fields = [{"name": "email", "label": "Email", "type": "email", "required": True}]
status, d = call("POST", "/widgets", {"type": "signup_form", "title": "Spoof proof", "form_fields": fields}, token)
assert status == 201, "widget failed: %s" % status
widget = d["id"]

real = "203.0.113.%d" % random.randint(1, 250)
codes = []
for i in range(8):
    forged = "198.18.0.%d" % (i + 1)
    status, _ = call("POST", "/submissions", {"widget_id": widget, "fields": {"email": "s%d@example.com" % i}},
                     xff="%s, %s" % (forged, real))
    codes.append(status)
out("one real client, a new forged first entry each time -> " + ",".join(str(c) for c in codes))
status, _ = call("POST", "/submissions", {"widget_id": widget, "fields": {"email": "other@example.com"}},
                 xff="198.18.0.99, 198.51.100.%d" % random.randint(1, 250))
out("a different real client is unaffected -> %s" % status)
protected = codes == [201] * 5 + [429] * 3
out("== " + ("PROTECTED: forged headers do not dodge the limit" if protected
            else "VULNERABLE: forged headers bypass the per-IP limit"))
with open("proof_spoof_%s.txt" % LABEL, "w", encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")
sys.exit(0 if protected else 1)
