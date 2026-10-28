"""HTTP layer for the owner dashboard."""
from fastapi import APIRouter, Depends

from app.db import connection
from app.security import require_owner
from app.services import dashboard as service

router = APIRouter()


@router.get("/dashboard")
def owner_dashboard(owner_id: str = Depends(require_owner)):
    with connection() as conn:
        return service.summary(conn, owner_id)
