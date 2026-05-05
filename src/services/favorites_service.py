"""Per-user team favorites: toggle, lookup, and joined retrieval."""
from datetime import datetime
from src.config import DB_PATH
from src.database import get_connection


def _now() -> str:
    return datetime.utcnow().isoformat()


def toggle_favorite(user_id: str, team_id: int) -> bool:
    """Toggle favorite. Returns True if now favorited, False if just un-favorited."""
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT 1 FROM user_favorites WHERE user_id = ? AND team_id = ?",
        (user_id, team_id),
    ).fetchone()
    if row:
        conn.execute(
            "DELETE FROM user_favorites WHERE user_id = ? AND team_id = ?",
            (user_id, team_id),
        )
        result = False
    else:
        conn.execute(
            "INSERT INTO user_favorites (user_id, team_id, created_at) VALUES (?, ?, ?)",
            (user_id, team_id, _now()),
        )
        result = True
    conn.commit()
    conn.close()
    return result


def get_favorite_team_ids(user_id: str) -> set[int]:
    """Return the set of team IDs the given user has favorited.
    Empty set if user has no favorites or doesn't exist."""
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT team_id FROM user_favorites WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    return {r["team_id"] for r in rows}


def get_favorited_teams(user_id: str) -> list[dict]:
    """Return the user's favorited teams as full team rows, ordered by team name.
    Joined against the teams table; teams that no longer exist are excluded by INNER JOIN."""
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        """
        SELECT t.* FROM teams t
        INNER JOIN user_favorites f ON f.team_id = t.id
        WHERE f.user_id = ?
        ORDER BY LOWER(t.name)
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
