"""Dashboard numbers for one owner."""
from app.repositories import submissions as submissions_repo


def summary(conn, owner_id):
    widgets = [
        {
            "id": r["id"],
            "title": r["title"],
            "type": r["type"],
            "stored_count": r["stored_count"],
            "last_submission_at": r["last_submission_at"],
        }
        for r in submissions_repo.stored_counts_for_owner(conn, owner_id)
    ]
    return {"total_stored": sum(w["stored_count"] for w in widgets), "widgets": widgets}
