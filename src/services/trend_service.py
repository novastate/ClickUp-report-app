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

    # Count carry-overs
    carried_over = sum(1 for t in snapshot if t.get("carried_over"))

    return {
        "forecasted": forecasted_count,
        "completed": completed,
        "total_current": total,
        "completion_rate": completion_rate,
        "scope_added": added,
        "scope_removed": removed,
        "unfinished": unfinished,
        "carried_over": carried_over,
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
        return {"sprints": [], "avg_velocity": 0, "avg_completion_rate": 0, "avg_scope_added": 0, "avg_forecast_accuracy": 0, "avg_unfinished": 0, "avg_carried_over": 0, "deltas": {}}

    n = len(sprint_summaries)
    avg_velocity = sum(s["velocity"] for s in sprint_summaries) / n
    avg_completion = sum(s["completion_rate"] for s in sprint_summaries) / n
    avg_scope = sum(s["scope_added"] for s in sprint_summaries) / n
    avg_forecast_accuracy = sum(
        s["completed"] / s["forecasted"] if s["forecasted"] > 0 else 0
        for s in sprint_summaries
    ) / n
    avg_unfinished = sum(s.get("unfinished", 0) for s in sprint_summaries) / n
    avg_carried_over = sum(s.get("carried_over", 0) for s in sprint_summaries) / n

    # Sprint-over-sprint deltas: compare recent half vs older half
    deltas = {}
    if n >= 2:
        mid = n // 2
        recent = sprint_summaries[:mid]
        older = sprint_summaries[mid:]
        def _avg(lst, key):
            return sum(s.get(key, 0) for s in lst) / len(lst) if lst else 0
        def _pct_delta(recent_val, older_val):
            if older_val == 0:
                return 0
            return round((recent_val - older_val) / abs(older_val) * 100)
        deltas = {
            "velocity": _pct_delta(_avg(recent, "velocity"), _avg(older, "velocity")),
            "completion_rate": _pct_delta(_avg(recent, "completion_rate"), _avg(older, "completion_rate")),
            "scope_added": _pct_delta(_avg(recent, "scope_added"), _avg(older, "scope_added")),
            "forecast_accuracy": _pct_delta(_avg(recent, "forecast_accuracy"), _avg(older, "forecast_accuracy")),
        }

    return {
        "sprints": sprint_summaries,
        "avg_velocity": avg_velocity,
        "avg_completion_rate": avg_completion,
        "avg_scope_added": avg_scope,
        "avg_forecast_accuracy": avg_forecast_accuracy,
        "avg_unfinished": avg_unfinished,
        "avg_carried_over": avg_carried_over,
        "deltas": deltas,
    }


def get_workload_distribution(sprint_id: int, metric_type: str = "task_count") -> list[dict]:
    import json
    snapshot = get_forecast_snapshot(sprint_id)
    final = get_final_snapshot(sprint_id)
    if not final:
        return []

    final_by_id = {t["task_id"]: t for t in final}

    # Build per-assignee stats
    assignee_stats = {}
    for t in snapshot:
        assignee = t.get("assignee_name") or "Unassigned"
        names = [n.strip() for n in assignee.split(",")] if assignee != "Unassigned" else ["Unassigned"]
        for name in names:
            if name not in assignee_stats:
                assignee_stats[name] = {"assigned": 0, "completed": 0, "hours": 0, "points": 0}
            assignee_stats[name]["assigned"] += 1
            final_task = final_by_id.get(t["task_id"])
            if final_task and final_task["task_status"] in ("complete", "closed"):
                assignee_stats[name]["completed"] += 1
            assignee_stats[name]["hours"] += t.get("hours") or 0
            assignee_stats[name]["points"] += t.get("points") or 0

    if not assignee_stats:
        return []

    avg_assigned = sum(s["assigned"] for s in assignee_stats.values()) / len(assignee_stats)

    result = []
    for name, stats in sorted(assignee_stats.items(), key=lambda x: x[1]["assigned"], reverse=True):
        pct = round(stats["completed"] / stats["assigned"] * 100) if stats["assigned"] > 0 else 0
        metric_value = 0
        if metric_type == "hours":
            metric_value = round(stats["hours"], 1)
        elif metric_type == "points":
            metric_value = round(stats["points"], 1)
        result.append({
            "name": name,
            "assigned": stats["assigned"],
            "completed": stats["completed"],
            "pct": pct,
            "metric_value": metric_value,
            "overloaded": stats["assigned"] > avg_assigned * 1.5,
        })

    return result
