"""DB ops for users and their encrypted OAuth tokens."""
from datetime import datetime
from src.config import DB_PATH
from src.database import get_connection
from src.auth.encryption import encrypt_token, decrypt_token


def _now() -> str:
    return datetime.utcnow().isoformat()


def upsert_user(id: str, email: str, username: str | None,
                color: str | None, profile_picture: str | None) -> None:
    conn = get_connection(DB_PATH)
    now = _now()
    conn.execute(
        """
        INSERT INTO users (id, email, username, color, profile_picture, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            email = excluded.email,
            username = excluded.username,
            color = excluded.color,
            profile_picture = excluded.profile_picture,
            updated_at = excluded.updated_at
        """,
        (id, email, username, color, profile_picture, now, now),
    )
    conn.commit()
    conn.close()


def get_user(user_id: str) -> dict | None:
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_user_token(user_id: str, access_token: str, scopes: str | None) -> None:
    conn = get_connection(DB_PATH)
    conn.execute(
        """
        INSERT INTO user_tokens (user_id, encrypted_access_token, scopes, granted_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            encrypted_access_token = excluded.encrypted_access_token,
            scopes = excluded.scopes,
            granted_at = excluded.granted_at
        """,
        (user_id, encrypt_token(access_token), scopes, _now()),
    )
    conn.commit()
    conn.close()


def get_user_token(user_id: str) -> str | None:
    """Return decrypted access token, or None if not found."""
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT encrypted_access_token FROM user_tokens WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return decrypt_token(row["encrypted_access_token"])


def delete_user_token(user_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
