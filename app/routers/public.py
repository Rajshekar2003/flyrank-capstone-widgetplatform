"""Public, cacheable endpoints used by the embedded widget: the script and the widget's config."""
import hashlib
import json

from fastapi import APIRouter, Request, Response

from app import assets
from app.db import connection
from app.services import widgets as widgets_service

router = APIRouter()

IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
SHORT_CACHE = "public, max-age=300"


def _etag_matches(header, etag):
    if not header:
        return False
    candidates = [part.strip().removeprefix("W/") for part in header.split(",")]
    return etag in candidates or "*" in candidates


@router.get("/widget.js")
def serve_widget_js(request: Request, v: str = ""):
    body, version = assets.load()
    etag = '"%s"' % version
    cache = IMMUTABLE_CACHE if v == version else SHORT_CACHE
    headers = {"ETag": etag, "Cache-Control": cache, "X-Content-Type-Options": "nosniff"}
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/javascript", headers=headers)


@router.get("/widgets/{widget_id}/config")
def get_widget_config(widget_id: str, request: Request):
    with connection() as conn:
        config = widgets_service.public_config(conn, widget_id)
    body = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    etag = '"%s"' % hashlib.sha256(body).hexdigest()[:16]
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60"}
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
