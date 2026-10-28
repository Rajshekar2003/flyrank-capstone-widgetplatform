"""SQL for the submissions table."""
import json


def insert(conn, submission_id, widget_id, field_values, ip_address, country, city, status, created_at):
    conn.execute(
        "INSERT INTO submissions (id, widget_id, field_values, ip_address, country, city, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (submission_id, widget_id, json.dumps(field_values), ip_address, country, city, status, created_at),
    )
    conn.commit()
