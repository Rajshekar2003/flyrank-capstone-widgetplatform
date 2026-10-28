"""Widget rules: validation, ownership and the embed snippet. No SQL and no HTTP in here."""
import uuid
from datetime import datetime, timezone

from app import assets, config
from app.errors import NotFound, ValidationFailed
from app.repositories import widgets as repo

VALID_WIDGET_TYPES = {"signup_form", "cta_popover"}


def _dump_fields(fields):
    return [f.model_dump() for f in fields]


def create(conn, owner_id, body):
    if body.type not in VALID_WIDGET_TYPES:
        raise ValidationFailed(f"Field 'type' must be one of {sorted(VALID_WIDGET_TYPES)}")
    if not body.title.strip():
        raise ValidationFailed("Field 'title' is required")
    if not body.form_fields:
        raise ValidationFailed("Field 'form_fields' must have at least one field")
    return repo.insert(
        conn, str(uuid.uuid4()), owner_id, body.type, body.title, body.description,
        _dump_fields(body.form_fields), body.button_text, body.display_options.model_dump(),
        datetime.now(timezone.utc).isoformat(),
    )


def list_for_owner(conn, owner_id):
    return repo.list_for_owner(conn, owner_id)


def get_owned(conn, widget_id, owner_id):
    widget = repo.get_owned(conn, widget_id, owner_id)
    if widget is None:
        raise NotFound(f"Widget {widget_id} not found")
    return widget


def update(conn, widget_id, owner_id, body):
    current = get_owned(conn, widget_id, owner_id)
    title = current["title"]
    if body.title is not None:
        if not body.title.strip():
            raise ValidationFailed("Field 'title' cannot be empty")
        title = body.title
    description = body.description if body.description is not None else current["description"]
    form_fields = _dump_fields(body.form_fields) if body.form_fields is not None else current["form_fields"]
    button_text = body.button_text if body.button_text is not None else current["button_text"]
    display_options = (
        body.display_options.model_dump() if body.display_options is not None else current["display_options"]
    )
    return repo.update(conn, widget_id, title, description, form_fields, button_text, display_options)


def delete(conn, widget_id, owner_id):
    get_owned(conn, widget_id, owner_id)
    repo.delete(conn, widget_id)


def embed_snippet(conn, widget_id, owner_id):
    get_owned(conn, widget_id, owner_id)
    version = assets.load()[1]
    snippet = f'<script src="{config.PUBLIC_BASE_URL}/widget.js?id={widget_id}&v={version}"></script>'
    return {"widget_id": widget_id, "snippet": snippet}


def public_config(conn, widget_id):
    """What a visitor's browser needs to render the widget. Never includes the owner."""
    widget = repo.get_by_id(conn, widget_id)
    if widget is None:
        raise NotFound("Widget not found")
    keys = ("id", "type", "title", "description", "form_fields", "button_text", "display_options")
    return {key: widget[key] for key in keys}
