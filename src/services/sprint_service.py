import os
import re
from datetime import datetime, date
from src.database import get_connection

def _db_path() -> str:
    return os.environ.get("DB_PATH", "./sprint_data.db")

def parse_iteration_dates(name: str, reference_year: int = None) -> tuple[date, date]:
    if reference_year is None:
        reference_year = datetime.now().year
    match = re.search(r"\((\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,2})\)", name)
    if not match:
        return None, None
    a, b, c, d = (int(g) for g in match.groups())
    # Detect day/month vs month/day format:
    # - If any first-position value > 12, it must be a day (day/month)
    # - If any second-position value > 12, it must be a day (month/day)
    # - If both dates share the same second value, it's likely day/month (same month)
    # - Otherwise default to month/day
    if a > 12 or c > 12:
        start_day, start_month, end_day, end_month = a, b, c, d
    elif b > 12 or d > 12:
        start_month, start_day, end_month, end_day = a, b, c, d
    elif b == d:
        # Same second value = same month, so format is day/month
        start_day, start_month, end_day, end_month = a, b, c, d
    else:
        start_month, start_day, end_month, end_day = a, b, c, d
    start = date(reference_year, start_month, start_day)
    end_year = reference_year + 1 if end_month < start_month else reference_year
    end = date(end_year, end_month, end_day)
    return start, end

def create_sprint_from_list(team_id: int, list_id: str, list_name: str) -> dict:
    start, end = parse_iteration_dates(list_name)
    conn = get_connection(_db_path())
    cursor = conn.execute(
        "INSERT OR IGNORE INTO sprints (team_id, name, clickup_list_id, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
        (team_id, list_name, list_id, start, end),
    )
    conn.commit()
    if cursor.lastrowid:
        sprint = conn.execute("SELECT * FROM sprints WHERE id = ?", (cursor.lastrowid,)).fetchone()
    else:
        sprint = conn.execute("SELECT * FROM sprints WHERE clickup_list_id = ?", (list_id,)).fetchone()
    conn.close()
    return dict(sprint)

def get_sprint(sprint_id: int) -> dict | None:
    conn = get_connection(_db_path())
    row = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_team_sprints(team_id: int) -> list[dict]:
    conn = get_connection(_db_path())
    rows = conn.execute(
        "SELECT * FROM sprints WHERE team_id = ? ORDER BY start_date DESC", (team_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sprint_status(sprint: dict) -> str:
    if sprint.get("closed_at"):
        return "closed"
    if sprint.get("forecast_closed_at"):
        return "active"
    return "planning"

def get_sprint_capacity(sprint_id: int) -> list[dict]:
    conn = get_connection(_db_path())
    rows = conn.execute("SELECT * FROM sprint_capacity WHERE sprint_id = ? ORDER BY username", (sprint_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_sprint_capacity(sprint_id: int, capacities: list[dict]):
    conn = get_connection(_db_path())
    for c in capacities:
        conn.execute(
            "INSERT OR REPLACE INTO sprint_capacity (sprint_id, username, capacity) VALUES (?, ?, ?)",
            (sprint_id, c["username"], c["capacity"]),
        )
    conn.commit()
    conn.close()

def close_forecast(sprint_id: int) -> dict:
    conn = get_connection(_db_path())
    now = datetime.now().isoformat()
    conn.execute("UPDATE sprints SET forecast_closed_at = ? WHERE id = ?", (now, sprint_id))
    conn.commit()
    sprint = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
    conn.close()
    return dict(sprint)

def close_sprint(sprint_id: int) -> dict:
    sprint = get_sprint(sprint_id)
    if not sprint or not sprint.get("forecast_closed_at"):
        raise ValueError("Cannot close sprint before forecast is closed")
    conn = get_connection(_db_path())
    now = datetime.now().isoformat()
    conn.execute("UPDATE sprints SET closed_at = ? WHERE id = ?", (now, sprint_id))
    conn.commit()
    sprint = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
    conn.close()
    return dict(sprint)
