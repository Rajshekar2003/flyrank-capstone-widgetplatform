"""Burst test for the per-widget rate limit.
Sends COUNT submissions from COUNT different simulated visitor IPs to one widget.
Needs TRUST_PROXY=true on the server.
Usage: python tools/burst_test.py WIDGET_ID [COUNT]"""
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

BASE = "http://127.0.0.1:8000"
widget_id = sys.argv[1]
count = int(sys.argv[2]) if len(sys.argv) > 2 else 40
body = json.dumps({"widget_id": widget_id, "fields": {"email": "visitor@example.com"}}).encode()


def status_of(request):
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


start = time.perf_counter()
for _ in range(10):
    status_of(urllib.request.Request(BASE + "/health"))
health_ms = (time.perf_counter() - start) / 10 * 1000

codes = []
start = time.perf_counter()
for i in range(1, count + 1):
    request = urllib.request.Request(
        BASE + "/submissions",
        data=body,
        headers={"Content-Type": "application/json", "X-Forwarded-For": f"198.51.100.{i}"},
        method="POST",
    )
    codes.append(status_of(request))
elapsed = time.perf_counter() - start

print(" ".join(f"{i}:{c}" for i, c in enumerate(codes, start=1)))
print(dict(Counter(codes)))
print(f"GET /health average: {health_ms:.0f} ms")
print(f"{count} submissions took {elapsed:.1f} s ({elapsed / count * 1000:.0f} ms each)")
