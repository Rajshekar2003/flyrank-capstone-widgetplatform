import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt, JWTError

load_dotenv()

from app.config import DB_PATH, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
from app.db import get_db, run_migrations
from app.schemas import LoginRequest, SignupRequest
from app.security import create_access_token, hash_password, require_owner, verify_password
from app.services.abuse import IP_LIMITER, WIDGET_LIMITER, get_client_ip, is_honeypot_filled, too_many_requests

run_migrations()

app = FastAPI(title="Embeddable Widget & Lead-Capture Platform")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/signup", status_code=201)
def signup(body: SignupRequest):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    conn = get_db()
    existing = conn.execute("SELECT id FROM owners WHERE email = ?", (body.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    owner_id = str(uuid.uuid4())
    password_hash = hash_password(body.password)
    conn.execute(
        "INSERT INTO owners (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (owner_id, body.email, password_hash, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    token = create_access_token(owner_id)
    return {"id": owner_id, "email": body.email, "access_token": token}


@app.post("/auth/login")
def login(body: LoginRequest):
    conn = get_db()
    row = conn.execute("SELECT * FROM owners WHERE email = ?", (body.email,)).fetchone()
    conn.close()

    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(row["id"])
    return {"access_token": token}


@app.get("/auth/me")
def me(owner_id: str = Depends(require_owner)):
    return {"owner_id": owner_id}

# --- Widgets (Phase 2b) ---
import asyncio
import json

import geo
import notify
import widget_assets
from typing import Optional, List



VALID_WIDGET_TYPES = {"signup_form", "cta_popover"}


class FormField(BaseModel):
    name: str
    label: str
    type: str
    required: bool = False


class DisplayOptions(BaseModel):
    color: str = "#0f3d3a"
    position: str = "bottom-right"


class WidgetCreate(BaseModel):
    type: str
    title: str
    description: Optional[str] = None
    form_fields: List[FormField]
    button_text: str = "Submit"
    display_options: DisplayOptions = DisplayOptions()


class WidgetUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    form_fields: Optional[List[FormField]] = None
    button_text: Optional[str] = None
    display_options: Optional[DisplayOptions] = None


def widget_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "type": row["type"],
        "title": row["title"],
        "description": row["description"],
        "form_fields": json.loads(row["form_fields"]),
        "button_text": row["button_text"],
        "display_options": json.loads(row["display_options"]),
        "created_at": row["created_at"],
    }


@app.post("/widgets", status_code=201)
def create_widget(body: WidgetCreate, owner_id: str = Depends(require_owner)):
    if body.type not in VALID_WIDGET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Field 'type' must be one of {sorted(VALID_WIDGET_TYPES)}",
        )
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required")
    if not body.form_fields:
        raise HTTPException(status_code=400, detail="Field 'form_fields' must have at least one field")

    widget_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        """INSERT INTO widgets
           (id, owner_id, type, title, description, form_fields, button_text, display_options, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            widget_id, owner_id, body.type, body.title, body.description,
            json.dumps([f.model_dump() for f in body.form_fields]),
            body.button_text, json.dumps(body.display_options.model_dump()),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM widgets WHERE id = ?", (widget_id,)).fetchone()
    conn.close()
    return widget_row_to_dict(row)


@app.get("/widgets")
def list_widgets(owner_id: str = Depends(require_owner)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM widgets WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
    ).fetchall()
    conn.close()
    return [widget_row_to_dict(r) for r in rows]


def _get_owned_widget(conn, widget_id: str, owner_id: str):
    row = conn.execute(
        "SELECT * FROM widgets WHERE id = ? AND owner_id = ?", (widget_id, owner_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Widget {widget_id} not found")
    return row


@app.get("/widgets/{widget_id}")
def get_widget(widget_id: str, owner_id: str = Depends(require_owner)):
    conn = get_db()
    row = _get_owned_widget(conn, widget_id, owner_id)
    conn.close()
    return widget_row_to_dict(row)


@app.put("/widgets/{widget_id}")
def update_widget(widget_id: str, body: WidgetUpdate, owner_id: str = Depends(require_owner)):
    conn = get_db()
    row = _get_owned_widget(conn, widget_id, owner_id)

    new_title = row["title"]
    if body.title is not None:
        if not body.title.strip():
            conn.close()
            raise HTTPException(status_code=400, detail="Field 'title' cannot be empty")
        new_title = body.title

    new_description = body.description if body.description is not None else row["description"]
    new_form_fields = (
        json.dumps([f.model_dump() for f in body.form_fields])
        if body.form_fields is not None else row["form_fields"]
    )
    new_button_text = body.button_text if body.button_text is not None else row["button_text"]
    new_display_options = (
        json.dumps(body.display_options.model_dump())
        if body.display_options is not None else row["display_options"]
    )

    conn.execute(
        """UPDATE widgets SET title = ?, description = ?, form_fields = ?,
           button_text = ?, display_options = ? WHERE id = ?""",
        (new_title, new_description, new_form_fields, new_button_text, new_display_options, widget_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM widgets WHERE id = ?", (widget_id,)).fetchone()
    conn.close()
    return widget_row_to_dict(updated)


@app.delete("/widgets/{widget_id}", status_code=204)
def delete_widget(widget_id: str, owner_id: str = Depends(require_owner)):
    conn = get_db()
    _get_owned_widget(conn, widget_id, owner_id)
    conn.execute("DELETE FROM widgets WHERE id = ?", (widget_id,))
    conn.commit()
    conn.close()
# --- end widgets ---

# --- Embed snippet (Phase 2c) ---
@app.get("/widgets/{widget_id}/embed")
def get_embed_snippet(widget_id: str, owner_id: str = Depends(require_owner)):
    conn = get_db()
    _get_owned_widget(conn, widget_id, owner_id)
    conn.close()
    base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    version = widget_assets.load()[1]
    snippet = f'<script src="{base_url}/widget.js?id={widget_id}&v={version}"></script>'
    return {"widget_id": widget_id, "snippet": snippet}
# --- end embed snippet ---

# --- Public widget assets (Phase 3a) ---
import hashlib
from fastapi import Request, Response

IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
SHORT_CACHE = "public, max-age=300"


def _etag_matches(header, etag):
    if not header:
        return False
    candidates = [part.strip().removeprefix("W/") for part in header.split(",")]
    return etag in candidates or "*" in candidates


@app.get("/widget.js")
def serve_widget_js(request: Request, v: str = ""):
    body, version = widget_assets.load()
    etag = '"%s"' % version
    cache = IMMUTABLE_CACHE if v == version else SHORT_CACHE
    headers = {"ETag": etag, "Cache-Control": cache, "X-Content-Type-Options": "nosniff"}
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/javascript", headers=headers)


@app.get("/widgets/{widget_id}/config")
def get_widget_config(widget_id: str, request: Request):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM widgets WHERE id = ?", (widget_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    config = {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "description": row["description"],
        "form_fields": json.loads(row["form_fields"]),
        "button_text": row["button_text"],
        "display_options": json.loads(row["display_options"]),
    }
    body = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    etag = '"%s"' % hashlib.sha256(body).hexdigest()[:16]
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60"}
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
# --- end public widget assets ---

# --- Owner dashboard (Phase 3b) ---
@app.get("/dashboard")
def owner_dashboard(owner_id: str = Depends(require_owner)):
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT w.id, w.title, w.type,
                   COUNT(s.id) AS stored_count,
                   MAX(s.created_at) AS last_submission_at
            FROM widgets w
            LEFT JOIN submissions s ON s.widget_id = w.id AND s.status = 'stored'
            WHERE w.owner_id = ?
            GROUP BY w.id
            ORDER BY w.created_at
            """,
            (owner_id,),
        ).fetchall()
    finally:
        conn.close()
    widgets = [
        {
            "id": r["id"],
            "title": r["title"],
            "type": r["type"],
            "stored_count": r["stored_count"],
            "last_submission_at": r["last_submission_at"],
        }
        for r in rows
    ]
    return {"total_stored": sum(w["stored_count"] for w in widgets), "widgets": widgets}
# --- end owner dashboard ---

# --- Public submissions (Phase 2d) ---
import re
from fastapi import Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
    expose_headers=["Retry-After"],
)

MAX_BODY_BYTES = 10_000
MAX_FIELD_LENGTH = 500
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")




def validate_submission_fields(definitions: dict, fields: dict) -> dict:
    unknown = sorted(set(fields) - set(definitions))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown field(s): {', '.join(unknown)}")

    clean = {}
    for name, definition in definitions.items():
        value = fields.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if definition.get("required"):
                raise HTTPException(status_code=400, detail=f"Field '{name}' is required")
            continue
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"Field '{name}' must be a string")
        value = value.strip()
        if len(value) > MAX_FIELD_LENGTH:
            raise HTTPException(status_code=400, detail=f"Field '{name}' is too long (max {MAX_FIELD_LENGTH} characters)")
        if definition.get("type") == "email" and not EMAIL_RE.match(value):
            raise HTTPException(status_code=400, detail=f"Field '{name}' must be a valid email address")
        clean[name] = value
    return clean


@app.post("/submissions", status_code=201)
async def create_submission(request: Request, background_tasks: BackgroundTasks):
    client_ip = get_client_ip(request)
    retry = IP_LIMITER.check(client_ip)
    if retry > 0:
        too_many_requests(retry, "per-IP")

    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"Payload too large (max {MAX_BODY_BYTES} bytes)")

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"Payload too large (max {MAX_BODY_BYTES} bytes)")

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        raise HTTPException(status_code=400, detail="Body must be valid JSON")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    widget_id = data.get("widget_id")
    fields = data.get("fields")
    if not isinstance(widget_id, str) or not widget_id:
        raise HTTPException(status_code=400, detail="Field 'widget_id' is required")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="Field 'fields' must be an object")

    conn = get_db()
    try:
        widget = conn.execute("SELECT * FROM widgets WHERE id = ?", (widget_id,)).fetchone()
        if widget is None:
            raise HTTPException(status_code=404, detail="Widget not found")

        retry = WIDGET_LIMITER.check(widget_id)
        if retry > 0:
            too_many_requests(retry, "per-widget")

        if is_honeypot_filled(data):
            spam_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO submissions (id, widget_id, field_values, ip_address, country, city, status, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                (spam_id, widget_id, "{}", client_ip, "flagged_spam",
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return {"id": spam_id, "status": "stored"}

        definitions = {f["name"]: f for f in json.loads(widget["form_fields"])}
        clean = validate_submission_fields(definitions, fields)

        submission_id = str(uuid.uuid4())
        ip_address = client_ip
        place = await asyncio.to_thread(geo.lookup_with_fallback, client_ip)
        country = place["country"] if place else None
        city = place["city"] if place else None
        conn.execute(
            "INSERT INTO submissions (id, widget_id, field_values, ip_address, country, city, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (submission_id, widget_id, json.dumps(clean), ip_address, country, city, "stored",
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    background_tasks.add_task(
        notify.notify_safely, notify.build_payload(submission_id, widget_id, clean)
    )
    return {"id": submission_id, "status": "stored"}
# --- end public submissions ---
