"""DB-backed sessions. Cookie holds opaque session_id; everything else is server-side."""
import secrets
from datetime import datetime, timedelta
from src.config import DB_PATH
from src.database import get_connection

SESSION_LIFETIME = timedelta(days=30)


def _now() -> datetime:
    return datetime.utcnow()


def _new_id() -> str:
    return secrets.token_hex(32)  # 64-char hex


def create_session(user_id: str, active_workspace_id: str | None) -> str:
    sid = _new_id()
    now = _now()
    expires = now + SESSION_LIFETIME
    conn = get_connection(DB_PATH)
    conn.execute(
        """
        INSERT INTO sessions (session_id, user_id, active_workspace_id,
                              created_at, expires_at, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (sid, user_id, active_workspace_id, now.isoformat(),
         expires.isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()
    return sid


def get_session(session_id: str) -> dict | None:
    """Return session dict if it exists and hasn't expired."""
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT * FROM sessions WHERE session_id = ? AND expires_at > ?",
        (session_id, _now().isoformat()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def roll_session(session_id: str) -> None:
    """Update expires_at to now+30d and last_seen to now. Idempotent on missing row."""
    now = _now()
    expires = now + SESSION_LIFETIME
    conn = get_connection(DB_PATH)
    conn.execute(
        "UPDATE sessions SET expires_at = ?, last_seen = ? WHERE session_id = ?",
        (expires.isoformat(), now.isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def set_active_workspace(session_id: str, workspace_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute(
        "UPDATE sessions SET active_workspace_id = ? WHERE session_id = ?",
        (workspace_id, session_id),
    )
    conn.commit()
    conn.close()


def delete_session(session_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def delete_sessions_for_user(user_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
