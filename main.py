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
