import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(stream=sys.stdout, level=logging.WARNING, format="  log: %(levelname)s %(message)s")
from app.integrations import notify

OUT = "proof_notify_outbox.txt"
if os.path.exists(OUT):
    os.remove(OUT)
payload = notify.build_payload("sub-1", "widget-1", {"email": "visitor@example.com"})


def case(title, **env):
    for k in ("NOTIFY_MOCK", "NOTIFY_WEBHOOK_URL", "NOTIFY_WEBHOOK_SECRET"):
        os.environ.pop(k, None)
    os.environ["NOTIFY_MOCK_OUTBOX"] = OUT
    os.environ["NOTIFY_TIMEOUT_SECONDS"] = "1"
    os.environ.update(env)
    print(f"\n== {title}")
    print("  result:", notify.notify_safely(payload))


case("not configured (disabled)")
case("mock ok", NOTIFY_MOCK="ok")
case("mock fail", NOTIFY_MOCK="fail")
case("real URL, nothing listening", NOTIFY_WEBHOOK_URL="http://127.0.0.1:9/hook")
case("bad URL scheme", NOTIFY_WEBHOOK_URL="file:///etc/passwd")
print("\n== outbox file after the run")
print(open(OUT, encoding="utf-8").read().strip())
body = b'{"a":1}'
sig = notify.sign("s3cret", body)
print("\n== signature:", sig[:20] + "...", "| deterministic:", sig == notify.sign("s3cret", body),
      "| differs by secret:", sig != notify.sign("other", body))
