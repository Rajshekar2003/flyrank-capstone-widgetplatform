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

DB_PATH = "widgets.db"
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()

app = FastAPI(title="Embeddable Widget & Lead-Capture Platform")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def create_access_token(owner_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": owner_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_owner(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    owner_id = payload.get("sub")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return owner_id


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
    password_hash = pwd_context.hash(body.password)
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

    if row is None or not pwd_context.verify(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(row["id"])
    return {"access_token": token}


@app.get("/auth/me")
def me(owner_id: str = Depends(require_owner)):
    return {"owner_id": owner_id}

# --- Widgets (Phase 2b) ---
import json
from typing import Optional, List


def init_widgets_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS widgets (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            form_fields TEXT NOT NULL,
            button_text TEXT NOT NULL,
            display_options TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES owners(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_widgets_owner ON widgets(owner_id)")
    conn.commit()
    conn.close()


init_widgets_table()

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
