import os
from src.database import get_connection

def _db_path() -> str:
    return os.environ.get("DB_PATH", "./sprint_data.db")

def create_team(name: str, workspace_id: str, space_id: str, folder_id: str, metric_type: str = "task_count", sprint_length_days: int = 14) -> dict:
    conn = get_connection(_db_path())
    cursor = conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id, metric_type, sprint_length_days) VALUES (?, ?, ?, ?, ?, ?)",
        (name, workspace_id, space_id, folder_id, metric_type, sprint_length_days),
    )
    conn.commit()
    team_id = cursor.lastrowid
    team = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    conn.close()
    return dict(team)

def get_team(team_id: int) -> dict | None:
    conn = get_connection(_db_path())
    row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_teams() -> list[dict]:
    conn = get_connection(_db_path())
    rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_team(team_id: int, **kwargs) -> dict | None:
    if not kwargs:
        return get_team(team_id)
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [team_id]
    conn = get_connection(_db_path())
    conn.execute(f"UPDATE teams SET {sets} WHERE id = ?", values)
    conn.commit()
    team = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    conn.close()
    return dict(team) if team else None

def delete_team(team_id: int) -> bool:
    conn = get_connection(_db_path())
    cursor = conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
