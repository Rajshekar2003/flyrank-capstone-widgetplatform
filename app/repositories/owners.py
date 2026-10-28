"""SQL for the owners table."""


def get_by_email(conn, email):
    row = conn.execute("SELECT * FROM owners WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def insert(conn, owner_id, email, password_hash, created_at):
    conn.execute(
        "INSERT INTO owners (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (owner_id, email, password_hash, created_at),
    )
    conn.commit()
