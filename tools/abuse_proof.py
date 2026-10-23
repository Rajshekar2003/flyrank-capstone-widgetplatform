"""Unit proof for app/services/abuse.py (no server needed)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "proof-only-secret")
from fastapi import HTTPException
from starlette.requests import Request

from app import config
from app.services import abuse

failures = []


def check(label, ok):
    print(("  PASS " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def req(xff=None, client=("198.51.100.9", 1234)):
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": client})


print("== sliding window limiter")
lim = abuse.SlidingWindowLimiter(3, 0.5)
check("the first 3 requests are allowed", [lim.check("a") for _ in range(3)] == [0.0, 0.0, 0.0])
wait = lim.check("a")
check("the 4th is blocked with a wait of at most the window", 0 < wait <= 0.5)
check("another key is not affected", lim.check("b") == 0.0)
time.sleep(0.55)
check("after the window passes, the key is allowed again", lim.check("a") == 0.0)
lim = abuse.SlidingWindowLimiter(1, 0.4)
lim.check("x")
for _ in range(5):
    lim.check("x")
time.sleep(0.45)
check("blocked attempts do not extend the block", lim.check("x") == 0.0)
lim = abuse.SlidingWindowLimiter(1, 0.05)
for i in range(10_005):
    lim.check("k%d" % i)
time.sleep(0.07)
lim.check("fresh")
check("stale keys are purged once the table passes 10,000", len(lim.hits) < 100)

print("== 429 helper")


def raised(seconds):
    try:
        abuse.too_many_requests(seconds, "per-IP")
    except HTTPException as e:
        return e


e = raised(0.2)
check("status is 429", e.status_code == 429)
check("Retry-After is a whole number of seconds, at least 1", e.headers["Retry-After"] == "1")
check("7.2 seconds is reported as 8", raised(7.2).headers["Retry-After"] == "8")
check("the message names the limit that was hit", "per-IP" in e.detail)

print("== honeypot")
for label, data, expected in (("absent", {}, False), ("empty string", {"website": ""}, False),
                              ("whitespace only", {"website": "   "}, False),
                              ("text", {"website": "http://spam.example"}, True),
                              ("null", {"website": None}, False),
                              ("a non-string value (a browser cannot send one)", {"website": 0}, True)):
    check("%s -> filled=%s" % (label, expected), abuse.is_honeypot_filled(data) is expected)

print("== client ip")
config.TRUST_PROXY = False
check("proxy not trusted: X-Forwarded-For is ignored", abuse.get_client_ip(req("203.0.113.7")) == "198.51.100.9")
check("no client at all gives 'unknown'", abuse.get_client_ip(req(client=None)) == "unknown")
config.TRUST_PROXY = True
config.TRUSTED_PROXY_HOPS = 1
check("one proxy: a single entry is the client", abuse.get_client_ip(req("203.0.113.7")) == "203.0.113.7")
check("one proxy: a forged first entry is ignored, the entry the proxy appended wins",
      abuse.get_client_ip(req("1.2.3.4, 203.0.113.7")) == "203.0.113.7")
check("one proxy: blank entries are ignored", abuse.get_client_ip(req("203.0.113.7, ")) == "203.0.113.7")
config.TRUSTED_PROXY_HOPS = 2
check("two proxies: the client is the second entry from the right",
      abuse.get_client_ip(req("1.2.3.4, 203.0.113.7, 10.0.0.1")) == "203.0.113.7")
check("two proxies but a single entry: the chain is too short, use the socket address",
      abuse.get_client_ip(req("203.0.113.7")) == "198.51.100.9")
config.TRUSTED_PROXY_HOPS = 1
check("proxy trusted: an invalid value falls back to the socket address", abuse.get_client_ip(req("not-an-ip")) == "198.51.100.9")
check("proxy trusted: no header falls back to the socket address", abuse.get_client_ip(req()) == "198.51.100.9")
check("proxy trusted: IPv6 is normalised", abuse.get_client_ip(req("2001:0db8:0000:0000:0000:0000:0000:0001")) == "2001:db8::1")

print("== result:", "ALL CHECKS PASSED" if not failures else "%d CHECK(S) FAILED" % len(failures))
sys.exit(1 if failures else 0)
