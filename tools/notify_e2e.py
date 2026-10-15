import json
import os
import sys
import time
import urllib.request

label, ip, spam = sys.argv[1], sys.argv[2], sys.argv[3] == "spam"
widget = "6243574c-3b9c-4df6-af03-ab8a67978566"
outbox = "proof_notify_e2e_outbox.txt"
data = {"widget_id": widget, "fields": {"email": "notify-" + label.replace(" ", "-") + "@example.com"}}
if spam:
    data["website"] = "http://spam.example"
    data["fields"]["website"] = "http://spam.example"
req = urllib.request.Request("http://127.0.0.1:8000/submissions", data=json.dumps(data).encode(), method="POST",
                             headers={"Content-Type": "application/json", "X-Forwarded-For": ip})
t0 = time.perf_counter()
with urllib.request.urlopen(req) as resp:
    status, out = resp.status, json.loads(resp.read())
ms = round((time.perf_counter() - t0) * 1000)
time.sleep(0.7)
lines = open(outbox, encoding="utf-8").read().splitlines() if os.path.exists(outbox) else []
hits = sum(1 for line in lines if out["id"] in line)
print(f"== {label} (ip={ip})")
print(f"  HTTP {status} {out} in {ms} ms")
print(f"  webhook outbox lines for this submission: {hits}")
