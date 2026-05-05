import os
from src.database import get_connection

def _db_path() -> str:
    return os.environ.get("DB_PATH", "./sprint_data.db")

def create_team(name: str, workspace_id: str, space_id: str, folder_id: str,
                metric_type: str = "task_count", capacity_mode: str = "individual",
                sprint_length_days: int = 14, workspace_id_new: str | None = None) -> dict:
    """Create a team. `workspace_id` (positional) is the ClickUp workspace_id (legacy
    `clickup_workspace_id` column). `workspace_id_new` (kw-only optional) is the new
    `workspace_id` column added by Task 1; equals the same ClickUp workspace_id but
    stored separately to enable workspace scoping in OAuth flows."""
    conn = get_connection(_db_path())
    cursor = conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id, metric_type, capacity_mode, sprint_length_days, workspace_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, workspace_id, space_id, folder_id, metric_type, capacity_mode, sprint_length_days, workspace_id_new),
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

def set_team_members(team_id: int, members: list[dict]):
    conn = get_connection(_db_path())
    conn.execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
    for m in members:
        conn.execute(
            "INSERT INTO team_members (team_id, clickup_user_id, username) VALUES (?, ?, ?)",
            (team_id, str(m["id"]), m["username"]),
        )
    conn.commit()
    conn.close()

def get_team_members(team_id: int) -> list[dict]:
    conn = get_connection(_db_path())
    rows = conn.execute("SELECT * FROM team_members WHERE team_id = ? ORDER BY username", (team_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
