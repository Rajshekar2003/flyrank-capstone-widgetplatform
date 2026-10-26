"""HTTP layer for the owner's widget endpoints. Thin: parse, call the service, return."""
from fastapi import APIRouter, Depends

from app.db import connection
from app.schemas import WidgetCreate, WidgetUpdate
from app.security import require_owner
from app.services import widgets as service

router = APIRouter()


@router.post("/widgets", status_code=201)
def create_widget(body: WidgetCreate, owner_id: str = Depends(require_owner)):
    with connection() as conn:
        return service.create(conn, owner_id, body)


@router.get("/widgets")
def list_widgets(owner_id: str = Depends(require_owner)):
    with connection() as conn:
        return service.list_for_owner(conn, owner_id)


@router.get("/widgets/{widget_id}")
def get_widget(widget_id: str, owner_id: str = Depends(require_owner)):
    with connection() as conn:
        return service.get_owned(conn, widget_id, owner_id)


@router.put("/widgets/{widget_id}")
def update_widget(widget_id: str, body: WidgetUpdate, owner_id: str = Depends(require_owner)):
    with connection() as conn:
        return service.update(conn, widget_id, owner_id, body)


@router.delete("/widgets/{widget_id}", status_code=204)
def delete_widget(widget_id: str, owner_id: str = Depends(require_owner)):
    with connection() as conn:
        service.delete(conn, widget_id, owner_id)


@router.get("/widgets/{widget_id}/embed")
def get_embed_snippet(widget_id: str, owner_id: str = Depends(require_owner)):
    with connection() as conn:
        return service.embed_snippet(conn, widget_id, owner_id)
