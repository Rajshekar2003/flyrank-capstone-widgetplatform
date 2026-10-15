"""Webhook side effect. deliver() raises on failure; notify_safely() never does."""
import hashlib
import hmac
import json
import logging
import os
import urllib.request

log = logging.getLogger("notify")


def _cfg(name, default=""):
    return os.environ.get(name, default)


def sign(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_payload(submission_id, widget_id, fields):
    return {
        "event": "submission.created",
        "submission_id": submission_id,
        "widget_id": widget_id,
        "fields": fields,
    }


def deliver(payload):
    """Send the webhook. Returns 'sent' or 'skipped'. Raises on any failure."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    mock = _cfg("NOTIFY_MOCK")
    if mock == "fail":
        raise RuntimeError("mock webhook forced to fail")
    if mock == "ok":
        with open(_cfg("NOTIFY_MOCK_OUTBOX", "notify_outbox.txt"), "a", encoding="utf-8") as f:
            f.write(body.decode() + "\n")
        return "sent"
    url = _cfg("NOTIFY_WEBHOOK_URL")
    if not url:
        return "skipped"
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("webhook URL must start with http:// or https://")
    headers = {"Content-Type": "application/json", "User-Agent": "widget-platform/1.0"}
    secret = _cfg("NOTIFY_WEBHOOK_SECRET")
    if secret:
        headers["X-Signature-256"] = sign(secret, body)
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=float(_cfg("NOTIFY_TIMEOUT_SECONDS", "3"))):
        pass
    return "sent"


def notify_safely(payload):
    """Never raises. Returns 'sent', 'skipped' or 'failed'. Logs no URL and no payload."""
    try:
        return deliver(payload)
    except Exception as exc:
        log.warning("webhook delivery failed: %s: %s", type(exc).__name__, str(exc)[:200])
        return "failed"
