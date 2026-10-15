import json
import sqlite3
import sys
import urllib.request

label, ip = sys.argv[1], sys.argv[2]
widget = "6243574c-3b9c-4df6-af03-ab8a67978566"
body = json.dumps({"widget_id": widget, "fields": {"email": "geo-" + label.replace(" ", "-") + "@example.com"}}).encode()
req = urllib.request.Request("http://127.0.0.1:8000/submissions", data=body, method="POST",
                             headers={"Content-Type": "application/json", "X-Forwarded-For": ip})
with urllib.request.urlopen(req) as resp:
    status, out = resp.status, json.loads(resp.read())
row = sqlite3.connect("widgets.db").execute(
    "select ip_address, country, city, status from submissions where id = ?", (out["id"],)).fetchone()
print(f"== {label} (ip={ip})")
print(f"  HTTP {status} {out}")
print(f"  stored row (ip, country, city, status): {row}")
