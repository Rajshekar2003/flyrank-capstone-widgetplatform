"""HTTP layer for owner signup, login and identity."""
from fastapi import APIRouter, Depends

from app.db import connection
from app.schemas import LoginRequest, SignupRequest
from app.security import require_owner
from app.services import auth as service

router = APIRouter()


@router.post("/auth/signup", status_code=201)
def signup(body: SignupRequest):
    with connection() as conn:
        return service.signup(conn, body.email, body.password)


@router.post("/auth/login")
def login(body: LoginRequest):
    with connection() as conn:
        return service.login(conn, body.email, body.password)


@router.get("/auth/me")
def me(owner_id: str = Depends(require_owner)):
    return {"owner_id": owner_id}
