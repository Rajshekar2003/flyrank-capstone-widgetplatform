"""Unit proof for app/security.py (no server needed)."""
import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "proof-only-secret")
from fastapi import HTTPException
from jose import jwt

from app import config, security

failures = []


def check(label, ok):
    print(("  PASS " if ok else "  FAIL ") + label)
    if not ok:
        failures.append(label)


def status_of(header):
    try:
        security.require_owner(header)
        return 200
    except HTTPException as e:
        return e.status_code


def b64(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


now = datetime.now(timezone.utc)
print("== tokens")
token = security.create_access_token("owner-123")
check("a fresh token resolves to its owner", security.require_owner("Bearer " + token) == "owner-123")
claims = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
check("the token expires in about 24 hours", abs(claims["exp"] - (time.time() + 86400)) < 120)
check("missing header is 401", status_of(None) == 401)
check("a non-Bearer scheme is 401", status_of("Basic abc") == 401)
check("garbage is 401", status_of("Bearer garbage") == 401)
expired = jwt.encode({"sub": "x", "exp": now - timedelta(minutes=1)}, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
check("an expired token is 401", status_of("Bearer " + expired) == 401)
forged = jwt.encode({"sub": "x", "exp": now + timedelta(hours=1)}, "some-other-secret", algorithm=config.JWT_ALGORITHM)
check("a token signed with another secret is 401", status_of("Bearer " + forged) == 401)
nosub = jwt.encode({"exp": now + timedelta(hours=1)}, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
check("a token without a subject is 401", status_of("Bearer " + nosub) == 401)
unsigned = b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": "x", "exp": int(time.time()) + 3600}) + "."
check("an unsigned (alg none) token is 401", status_of("Bearer " + unsigned) == 401)

print("== passwords")
h1 = security.hash_password("correct horse battery")
h2 = security.hash_password("correct horse battery")
check("the right password verifies", security.verify_password("correct horse battery", h1))
check("a wrong password is rejected", not security.verify_password("wrong horse battery", h1))
check("hashes are salted (same password, different hash)", h1 != h2)
check("the hash is not the plaintext", "correct horse" not in h1)

print("== result:", "ALL CHECKS PASSED" if not failures else "%d CHECK(S) FAILED" % len(failures))
sys.exit(1 if failures else 0)
