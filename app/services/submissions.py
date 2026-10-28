"""Submission rules: body parsing, validation, spam and rate decisions, geo, storage and the webhook."""
import asyncio
import json
import re
import uuid
from datetime import datetime, timezone

from app.errors import NotFound, PayloadTooLarge, ValidationFailed
from app.integrations import geo, notify
from app.repositories import submissions as repo
from app.repositories import widgets as widgets_repo
from app.services.abuse import WIDGET_LIMITER, is_honeypot_filled, too_many_requests

MAX_BODY_BYTES = 10_000
MAX_FIELD_LENGTH = 500
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _too_large():
    return PayloadTooLarge(f"Payload too large (max {MAX_BODY_BYTES} bytes)")


def check_declared_size(content_length):
    if content_length is not None and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        raise _too_large()


def check_size(raw: bytes):
    if len(raw) > MAX_BODY_BYTES:
        raise _too_large()


def parse_body(raw: bytes) -> dict:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        raise ValidationFailed("Body must be valid JSON")
    if not isinstance(data, dict):
        raise ValidationFailed("Body must be a JSON object")
    return data


def validate_fields(definitions: dict, fields: dict) -> dict:
    unknown = sorted(set(fields) - set(definitions))
    if unknown:
        raise ValidationFailed(f"Unknown field(s): {', '.join(unknown)}")

    clean = {}
    for name, definition in definitions.items():
        value = fields.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if definition.get("required"):
                raise ValidationFailed(f"Field '{name}' is required")
            continue
        if not isinstance(value, str):
            raise ValidationFailed(f"Field '{name}' must be a string")
        value = value.strip()
        if len(value) > MAX_FIELD_LENGTH:
            raise ValidationFailed(f"Field '{name}' is too long (max {MAX_FIELD_LENGTH} characters)")
        if definition.get("type") == "email" and not EMAIL_RE.match(value):
            raise ValidationFailed(f"Field '{name}' must be a valid email address")
        clean[name] = value
    return clean


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create(conn, data: dict, client_ip: str, enqueue) -> dict:
    """Store one submission. `enqueue(fn, *args)` schedules work to run after the response is sent."""
    widget_id = data.get("widget_id")
    fields = data.get("fields")
    if not isinstance(widget_id, str) or not widget_id:
        raise ValidationFailed("Field 'widget_id' is required")
    if not isinstance(fields, dict):
        raise ValidationFailed("Field 'fields' must be an object")

    widget = widgets_repo.get_by_id(conn, widget_id)
    if widget is None:
        raise NotFound("Widget not found")

    retry = WIDGET_LIMITER.check(widget_id)
    if retry > 0:
        too_many_requests(retry, "per-widget")

    if is_honeypot_filled(data):
        spam_id = str(uuid.uuid4())
        repo.insert(conn, spam_id, widget_id, {}, client_ip, None, None, "flagged_spam", _now())
        return {"id": spam_id, "status": "stored"}

    definitions = {f["name"]: f for f in widget["form_fields"]}
    clean = validate_fields(definitions, fields)

    submission_id = str(uuid.uuid4())
    place = await asyncio.to_thread(geo.lookup_with_fallback, client_ip)
    country = place["country"] if place else None
    city = place["city"] if place else None
    repo.insert(conn, submission_id, widget_id, clean, client_ip, country, city, "stored", _now())

    enqueue(notify.notify_safely, notify.build_payload(submission_id, widget_id, clean))
    return {"id": submission_id, "status": "stored"}
