"""SQL for the submissions table."""
import json


def insert(conn, submission_id, widget_id, field_values, ip_address, country, city, status, created_at):
    conn.execute(
        "INSERT INTO submissions (id, widget_id, field_values, ip_address, country, city, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (submission_id, widget_id, json.dumps(field_values), ip_address, country, city, status, created_at),
    )
    conn.commit()


def stored_counts_for_owner(conn, owner_id):
    """One row per widget of the owner, counting only stored (not flagged_spam) submissions."""
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
    return [dict(r) for r in rows]
