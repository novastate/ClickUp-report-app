from fastapi import APIRouter, HTTPException, Request, Depends
from src.services.sprint_service import get_sprint, close_forecast as do_close_forecast, close_sprint as do_close_sprint, get_sprint_status, get_sprint_capacity, set_sprint_capacity
from pydantic import BaseModel
from src.services.snapshot_service import save_forecast_snapshot, record_daily_progress, detect_scope_changes, get_scope_changes, get_forecast_snapshot, get_daily_progress_history, save_final_snapshot
from src.services.trend_service import get_sprint_summary
from src.services.team_service import get_team
from src.auth.middleware import get_current_user

router = APIRouter(prefix="/sprints", tags=["sprints"])

async def _fetch_tasks(sprint: dict, client):
    """Fetch tasks for a sprint using a caller-provided client."""
    team = get_team(sprint["team_id"])
    raw_tasks = await client.get_list_tasks(
        sprint["clickup_list_id"],
        space_id=team["clickup_space_id"],
        workspace_id=team.get("clickup_workspace_id"),
    )
    return raw_tasks

@router.get("/{sprint_id}")
def sprint_detail(sprint_id: int, user=Depends(get_current_user)):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    sprint["status"] = get_sprint_status(sprint)
    sprint["summary"] = get_sprint_summary(sprint_id)
    sprint["scope_changes"] = get_scope_changes(sprint_id)
    sprint["progress_history"] = get_daily_progress_history(sprint_id)
    sprint["forecast_snapshot"] = get_forecast_snapshot(sprint_id)
    return sprint

@router.post("/{sprint_id}/close-forecast")
async def close_forecast_route(sprint_id: int, request: Request,
                               user=Depends(get_current_user)):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    if sprint.get("forecast_closed_at"):
        raise HTTPException(400, "Forecast already closed")
    client = request.state.user_client
    raw_tasks = await _fetch_tasks(sprint, client)
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    save_forecast_snapshot(sprint_id, tasks)
    # Detect carry-overs from previous sprint
    from src.services.sprint_service import get_team_sprints
    team_sprints = get_team_sprints(sprint["team_id"])
    prev_closed = None
    for s in team_sprints:
        if s["id"] != sprint_id and s.get("closed_at"):
            if prev_closed is None or (s.get("start_date") or "") > (prev_closed.get("start_date") or ""):
                prev_closed = s
    if prev_closed:
        from src.services.snapshot_service import get_final_snapshot
        prev_final = get_final_snapshot(prev_closed["id"])
        if prev_final:
            unfinished_ids = {t["task_id"] for t in prev_final if t["task_status"] not in ("complete", "closed")}
            current_ids = {t["task_id"] for t in tasks}
            carried = unfinished_ids & current_ids
            if carried:
                from src.database import get_connection
                from src.services.snapshot_service import _db
                conn = get_connection(_db())
                for tid in carried:
                    conn.execute("UPDATE sprint_snapshots SET carried_over = 1 WHERE sprint_id = ? AND task_id = ?", (sprint_id, tid))
                conn.commit()
                conn.close()
    updated = do_close_forecast(sprint_id)
    completed = sum(1 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_points = sum(t["points"] or 0 for t in tasks)
    completed_points = sum(t["points"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_hours = sum(t["hours"] or 0 for t in tasks)
    completed_hours = sum(t["hours"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    record_daily_progress(sprint_id, len(tasks), completed, total_points, completed_points, total_hours, completed_hours)
    return {"sprint": updated, "tasks_captured": len(tasks)}

@router.post("/{sprint_id}/close")
async def close_sprint_route(sprint_id: int, request: Request,
                             user=Depends(get_current_user)):
    await refresh_route(sprint_id, request, user)
    sprint = get_sprint(sprint_id)
    client = request.state.user_client
    raw_tasks = await _fetch_tasks(sprint, client)
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    # Save final snapshot with current task states
    save_final_snapshot(sprint_id, tasks)
    # Capture any new scope additions to baseline
    snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint_id)}
    added_tasks = [t for t in tasks if t["task_id"] not in snapshot_ids]
    if added_tasks:
        save_forecast_snapshot(sprint_id, added_tasks)
    try:
        updated = do_close_sprint(sprint_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return updated

@router.post("/{sprint_id}/refresh")
async def refresh_route(sprint_id: int, request: Request,
                        user=Depends(get_current_user)):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    if not sprint.get("forecast_closed_at"):
        raise HTTPException(400, "Forecast not yet closed")
    if sprint.get("closed_at"):
        raise HTTPException(400, "Sprint is closed")
    client = request.state.user_client
    raw_tasks = await _fetch_tasks(sprint, client)
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    new_changes = detect_scope_changes(sprint_id, tasks, sprint_start_date=sprint.get("start_date"))
    completed = sum(1 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_points = sum(t["points"] or 0 for t in tasks)
    completed_points = sum(t["points"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_hours = sum(t["hours"] or 0 for t in tasks)
    completed_hours = sum(t["hours"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    record_daily_progress(sprint_id, len(tasks), completed, total_points, completed_points, total_hours, completed_hours)
    return {"tasks": len(tasks), "completed": completed, "new_scope_changes": len(new_changes)}

@router.get("/{sprint_id}/tasks")
async def sprint_tasks(sprint_id: int, request: Request, filter: str = None,
                       user=Depends(get_current_user)):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    if sprint.get("closed_at"):
        snapshot = get_forecast_snapshot(sprint_id)
        changes = get_scope_changes(sprint_id)
        added_ids = {c["task_id"] for c in changes if c["change_type"] == "added"}
        removed_ids = {c["task_id"] for c in changes if c["change_type"] == "removed"}
        tasks = []
        for t in snapshot:
            t["scope_change"] = "removed" if t["task_id"] in removed_ids else None
            tasks.append(t)
        for c in changes:
            if c["change_type"] == "added":
                tasks.append({**c, "scope_change": "added", "points": None, "hours": None})
    else:
        client = request.state.user_client
        raw_tasks = await _fetch_tasks(sprint, client)
        snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint_id)} if sprint.get("forecast_closed_at") else set()
        tasks = []
        for t in raw_tasks:
            extracted = client.extract_task_data(t)
            extracted["scope_change"] = "added" if extracted["task_id"] not in snapshot_ids and snapshot_ids else None
            tasks.append(extracted)
    if filter == "completed":
        tasks = [t for t in tasks if t.get("task_status") in ("complete", "closed")]
    elif filter == "not_completed":
        tasks = [t for t in tasks if t.get("task_status") not in ("complete", "closed")]
    elif filter == "scope_changes":
        tasks = [t for t in tasks if t.get("scope_change")]
    return tasks

class CapacityEntry(BaseModel):
    username: str
    capacity: float

@router.get("/{sprint_id}/capacity")
def get_capacity(sprint_id: int, user=Depends(get_current_user)):
    return get_sprint_capacity(sprint_id)

@router.post("/{sprint_id}/capacity")
def save_capacity(sprint_id: int, entries: list[CapacityEntry],
                  user=Depends(get_current_user)):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    set_sprint_capacity(sprint_id, [e.model_dump() for e in entries])
    return {"ok": True}
