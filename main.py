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
from app.errors import AppError
from app.routers import widgets as widgets_router
from fastapi.responses import JSONResponse

run_migrations()

app = FastAPI(title="Embeddable Widget & Lead-Capture Platform")


@app.exception_handler(AppError)
async def handle_app_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(widgets_router.router)


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

# --- imports shared with the remaining handlers (tidied in step 6) ---
import asyncio
import json

import geo
import notify
import widget_assets
from typing import Optional, List


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
