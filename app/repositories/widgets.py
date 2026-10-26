"""SQL for the widgets table. Knows rows and JSON columns; knows nothing about HTTP or rules."""
import json


def row_to_dict(row) -> dict:
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


def get_by_id(conn, widget_id):
    row = conn.execute("SELECT * FROM widgets WHERE id = ?", (widget_id,)).fetchone()
    return row_to_dict(row) if row else None


def get_owned(conn, widget_id, owner_id):
    row = conn.execute("SELECT * FROM widgets WHERE id = ? AND owner_id = ?", (widget_id, owner_id)).fetchone()
    return row_to_dict(row) if row else None


def list_for_owner(conn, owner_id):
    rows = conn.execute(
        "SELECT * FROM widgets WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def insert(conn, widget_id, owner_id, type_, title, description, form_fields, button_text, display_options, created_at):
    conn.execute(
        """INSERT INTO widgets
           (id, owner_id, type, title, description, form_fields, button_text, display_options, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (widget_id, owner_id, type_, title, description,
         json.dumps(form_fields), button_text, json.dumps(display_options), created_at),
    )
    conn.commit()
    return get_by_id(conn, widget_id)


def update(conn, widget_id, title, description, form_fields, button_text, display_options):
    conn.execute(
        """UPDATE widgets SET title = ?, description = ?, form_fields = ?,
           button_text = ?, display_options = ? WHERE id = ?""",
        (title, description, json.dumps(form_fields), button_text, json.dumps(display_options), widget_id),
    )
    conn.commit()
    return get_by_id(conn, widget_id)


def delete(conn, widget_id):
    conn.execute("DELETE FROM widgets WHERE id = ?", (widget_id,))
    conn.commit()
