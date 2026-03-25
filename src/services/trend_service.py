import os
from src.database import get_connection
from src.services.sprint_service import get_team_sprints, get_sprint_status
from src.services.snapshot_service import get_forecast_snapshot, get_daily_progress_history, get_scope_changes, get_final_snapshot

def _db():
    return os.environ.get("DB_PATH", "./sprint_data.db")

def calculate_on_track_status(remaining: float, ideal_remaining: float) -> str:
    if ideal_remaining == 0:
        return "on_track" if remaining == 0 else "behind"
    diff_pct = (remaining - ideal_remaining) / ideal_remaining
    if diff_pct < -0.10:
        return "ahead"
    elif diff_pct > 0.10:
        return "behind"
    return "on_track"

def get_sprint_summary(sprint_id: int) -> dict:
    snapshot = get_forecast_snapshot(sprint_id)
    progress = get_daily_progress_history(sprint_id)
    scope = get_scope_changes(sprint_id)

    forecasted_count = len(snapshot)
    latest = progress[-1] if progress else None

    completed = latest["completed_tasks"] if latest else 0
    total = latest["total_tasks"] if latest else forecasted_count
    completion_rate = completed / forecasted_count if forecasted_count > 0 else 0

    added = sum(1 for s in scope if s["change_type"] == "added")
    removed = sum(1 for s in scope if s["change_type"] == "removed")

    # Count unfinished from final snapshot (baseline tasks not completed)
    final = get_final_snapshot(sprint_id)
    if final:
        baseline_ids = {t["task_id"] for t in snapshot}
        final_by_id = {t["task_id"]: t for t in final}
        unfinished = sum(1 for tid in baseline_ids if tid in final_by_id and final_by_id[tid]["task_status"] not in ("complete", "closed"))
    else:
        unfinished = 0

    return {
        "forecasted": forecasted_count,
        "completed": completed,
        "total_current": total,
        "completion_rate": completion_rate,
        "scope_added": added,
        "scope_removed": removed,
        "unfinished": unfinished,
        "velocity": completed,
        "forecast_accuracy": completed / forecasted_count if forecasted_count > 0 else 0,
        "completed_points": latest["completed_points"] if latest else 0,
        "completed_hours": latest["completed_hours"] if latest else 0,
    }

def get_team_trends(team_id: int, limit: int = None) -> dict:
    sprints = get_team_sprints(team_id)
    closed = [s for s in sprints if get_sprint_status(s) == "closed"]
    if limit:
        closed = closed[:limit]

    sprint_summaries = []
    for s in closed:
        summary = get_sprint_summary(s["id"])
        summary["sprint_id"] = s["id"]
        summary["sprint_name"] = s["name"]
        summary["start_date"] = s["start_date"]
        summary["end_date"] = s["end_date"]
        sprint_summaries.append(summary)

    if not sprint_summaries:
        return {"sprints": [], "avg_velocity": 0, "avg_completion_rate": 0, "avg_scope_added": 0, "avg_forecast_accuracy": 0}

    avg_velocity = sum(s["velocity"] for s in sprint_summaries) / len(sprint_summaries)
    avg_completion = sum(s["completion_rate"] for s in sprint_summaries) / len(sprint_summaries)
    avg_scope = sum(s["scope_added"] for s in sprint_summaries) / len(sprint_summaries)
    avg_forecast_accuracy = sum(
        s["completed"] / s["forecasted"] if s["forecasted"] > 0 else 0
        for s in sprint_summaries
    ) / len(sprint_summaries)

    return {
        "sprints": sprint_summaries,
        "avg_velocity": avg_velocity,
        "avg_completion_rate": avg_completion,
        "avg_scope_added": avg_scope,
        "avg_forecast_accuracy": avg_forecast_accuracy,
    }
