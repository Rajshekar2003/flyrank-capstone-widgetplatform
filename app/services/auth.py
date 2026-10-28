"""Owner account rules: signup and login."""
import uuid
from datetime import datetime, timezone

from app.errors import Unauthorized, ValidationFailed
from app.repositories import owners as repo
from app.security import create_access_token, hash_password, verify_password


def signup(conn, email, password):
    if len(password) < 8:
        raise ValidationFailed("Password must be at least 8 characters")
    if repo.get_by_email(conn, email) is not None:
        raise ValidationFailed("An account with this email already exists")
    owner_id = str(uuid.uuid4())
    repo.insert(conn, owner_id, email, hash_password(password), datetime.now(timezone.utc).isoformat())
    return {"id": owner_id, "email": email, "access_token": create_access_token(owner_id)}


def login(conn, email, password):
    owner = repo.get_by_email(conn, email)
    if owner is None or not verify_password(password, owner["password_hash"]):
        raise Unauthorized("Invalid email or password")
    return {"access_token": create_access_token(owner["id"])}
