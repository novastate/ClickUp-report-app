from datetime import datetime
from src.database import get_connection
import os

def _db():
    return os.environ.get("DB_PATH", "./sprint_data.db")

def save_forecast_snapshot(sprint_id: int, tasks: list[dict]):
    import json
    conn = get_connection(_db())
    for t in tasks:
        ah = t.get("assignee_hours")
        conn.execute(
            "INSERT INTO sprint_snapshots (sprint_id, task_id, task_name, task_status, assignee_name, points, hours, assignee_hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sprint_id, t["task_id"], t["task_name"], t["task_status"], t.get("assignee_name"), t.get("points"), t.get("hours"), json.dumps(ah) if ah else None),
        )
    conn.commit()
    conn.close()

def get_forecast_snapshot(sprint_id: int) -> list[dict]:
    conn = get_connection(_db())
    rows = conn.execute("SELECT * FROM sprint_snapshots WHERE sprint_id = ?", (sprint_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_final_snapshot(sprint_id: int, tasks: list[dict]):
    import json
    conn = get_connection(_db())
    for t in tasks:
        ah = t.get("assignee_hours")
        conn.execute(
            "INSERT INTO sprint_final_snapshots (sprint_id, task_id, task_name, task_status, assignee_name, assignee_hours, points, hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sprint_id, t["task_id"], t["task_name"], t["task_status"], t.get("assignee_name"), json.dumps(ah) if ah else None, t.get("points"), t.get("hours")),
        )
    conn.commit()
    conn.close()

def get_final_snapshot(sprint_id: int) -> list[dict]:
    import json
    conn = get_connection(_db())
    rows = conn.execute("SELECT * FROM sprint_final_snapshots WHERE sprint_id = ?", (sprint_id,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("assignee_hours"):
            d["assignee_hours"] = json.loads(d["assignee_hours"])
        else:
            d["assignee_hours"] = []
        result.append(d)
    return result

def record_daily_progress(sprint_id: int, total_tasks: int, completed_tasks: int,
                          total_points: float = None, completed_points: float = None,
                          total_hours: float = None, completed_hours: float = None):
    conn = get_connection(_db())
    conn.execute(
        "INSERT INTO daily_progress (sprint_id, total_tasks, completed_tasks, total_points, completed_points, total_hours, completed_hours) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sprint_id, total_tasks, completed_tasks, total_points, completed_points, total_hours, completed_hours),
    )
    conn.commit()
    conn.close()

def get_daily_progress_history(sprint_id: int) -> list[dict]:
    conn = get_connection(_db())
    rows = conn.execute(
        "SELECT * FROM daily_progress WHERE sprint_id = ? ORDER BY captured_at", (sprint_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_scope_changes(sprint_id: int) -> list[dict]:
    conn = get_connection(_db())
    rows = conn.execute(
        "SELECT * FROM scope_changes WHERE sprint_id = ? ORDER BY detected_at", (sprint_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def detect_scope_changes(sprint_id: int, current_tasks: list[dict]) -> list[dict]:
    snapshot = get_forecast_snapshot(sprint_id)
    existing_changes = get_scope_changes(sprint_id)

    snapshot_ids = {t["task_id"] for t in snapshot}
    current_ids = {t["task_id"] for t in current_tasks}
    current_by_id = {t["task_id"]: t for t in current_tasks}

    already_added = set()
    already_removed = set()
    for ch in existing_changes:
        if ch["change_type"] == "added":
            already_added.add(ch["task_id"])
            already_removed.discard(ch["task_id"])
        else:
            already_removed.add(ch["task_id"])
            already_added.discard(ch["task_id"])

    new_changes = []
    conn = get_connection(_db())

    for tid in current_ids - snapshot_ids:
        if tid not in already_added:
            task = current_by_id[tid]
            conn.execute(
                "INSERT INTO scope_changes (sprint_id, task_id, task_name, change_type, assignee_name) VALUES (?, ?, ?, 'added', ?)",
                (sprint_id, tid, task["task_name"], task.get("assignee_name")),
            )
            new_changes.append({"task_id": tid, "task_name": task["task_name"], "change_type": "added"})

    for tid in snapshot_ids - current_ids:
        if tid not in already_removed:
            snapshot_task = next(t for t in snapshot if t["task_id"] == tid)
            conn.execute(
                "INSERT INTO scope_changes (sprint_id, task_id, task_name, change_type, assignee_name) VALUES (?, ?, ?, 'removed', ?)",
                (sprint_id, tid, snapshot_task["task_name"], snapshot_task.get("assignee_name")),
            )
            new_changes.append({"task_id": tid, "task_name": snapshot_task["task_name"], "change_type": "removed"})

    conn.commit()
    conn.close()
    return new_changes
