"""Short-lived `state` parameters for OAuth CSRF protection.

A row exists for ~10 minutes between /auth/login (create) and /auth/callback
(consume). Stale rows are cleaned on every create."""
import secrets
from datetime import datetime, timedelta
from src.config import DB_PATH
from src.database import get_connection

STATE_TTL = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.utcnow()


def create_state() -> str:
    """Generate a random state, store with timestamp, return it.
    Also opportunistically cleans up old states."""
    cleanup_old_states()
    state = secrets.token_hex(32)
    conn = get_connection(DB_PATH)
    conn.execute(
        "INSERT INTO oauth_state (state, created_at) VALUES (?, ?)",
        (state, _now().isoformat()),
    )
    conn.commit()
    conn.close()
    return state


def consume_state(state: str) -> bool:
    """Atomically delete state if found and within TTL; return True only for the winner.

    Atomic single-statement DELETE prevents two concurrent /auth/callback requests
    with the same state from both succeeding (would break one-shot semantics).
    Stale or unknown rows are not deleted by this call (rowcount==0 for expired
    rows means the WHERE didn't match) — they get cleaned up later by
    cleanup_old_states()."""
    cutoff = (_now() - STATE_TTL).isoformat()
    conn = get_connection(DB_PATH)
    cur = conn.execute(
        "DELETE FROM oauth_state WHERE state = ? AND created_at > ?",
        (state, cutoff),
    )
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted == 1


def cleanup_old_states() -> None:
    cutoff = (_now() - STATE_TTL).isoformat()
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM oauth_state WHERE created_at <= ?", (cutoff,))
    conn.commit()
    conn.close()
