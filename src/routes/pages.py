from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from src.services.team_service import get_all_teams, get_team, get_team_members
from src.services.sprint_service import get_team_sprints, get_sprint, get_sprint_status, get_sprint_capacity
from src.services.trend_service import get_sprint_summary
from src.services.snapshot_service import get_scope_changes, get_daily_progress_history, get_forecast_snapshot, get_final_snapshot
from src.config import get_clickup_api_key, DB_PATH
from src.database import set_setting
from datetime import datetime, date

templates = Jinja2Templates(directory="templates")

import re as _re

def _display_name(name):
    if not name:
        return name
    return _re.sub(r"\s*\([^)]*\)\s*$", "", str(name)).strip()

templates.env.filters["display_name"] = _display_name
router = APIRouter(tags=["pages"])


def _ctx(request, breadcrumbs=None, team_sub_nav_active=None, **kwargs):
    kwargs["request"] = request
    kwargs["nav_teams"] = get_all_teams()
    kwargs["breadcrumbs"] = breadcrumbs or []
    kwargs["team_sub_nav_active"] = team_sub_nav_active
    return kwargs


def _breadcrumbs(*pairs):
    """Build a breadcrumbs list. Each pair is (label, href). Pass None as href for the last entry."""
    return [{"label": label, "href": href} for label, href in pairs]


def _needs_setup() -> bool:
    return not get_clickup_api_key()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    if _needs_setup():
        return RedirectResponse("/setup")
    teams = get_all_teams()
    for team in teams:
        team["sprints"] = get_team_sprints(team["id"])
        team["active_sprint"] = None
        for s in team["sprints"]:
            s["status"] = get_sprint_status(s)
            if s["status"] == "active":
                team["active_sprint"] = s
    return templates.TemplateResponse("home.html", _ctx(request, teams=teams))


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    current_key = get_clickup_api_key()
    masked = f"pk_...{current_key[-8:]}" if current_key and len(current_key) > 12 else ""
    return templates.TemplateResponse("setup.html", _ctx(request, masked_key=masked, has_key=bool(current_key)))


@router.post("/setup")
async def save_setup(request: Request):
    form = await request.form()
    api_key = form.get("api_key", "").strip()
    if api_key:
        set_setting(DB_PATH, "clickup_api_key", api_key)
    return RedirectResponse("/teams/new", status_code=303)


@router.get("/teams/new", response_class=HTMLResponse)
def new_team_page(request: Request):
    if _needs_setup():
        return RedirectResponse("/setup")
    return templates.TemplateResponse("team_settings.html", _ctx(request, team=None))


@router.get("/teams/{team_id}/settings", response_class=HTMLResponse)
def team_settings_page(request: Request, team_id: int):
    team = get_team(team_id)
    members = get_team_members(team_id) if team else []
    return templates.TemplateResponse("team_settings.html", _ctx(request, team=team, current_members=members))


@router.get("/teams/{team_id}/sprints", response_class=HTMLResponse)
def sprint_history_page(request: Request, team_id: int):
    team = get_team(team_id)
    sprints = get_team_sprints(team_id)
    sprint_data = []
    for s in sprints:
        s["status"] = get_sprint_status(s)
        if s["status"] == "closed":
            s["summary"] = get_sprint_summary(s["id"])
        sprint_data.append(s)
    return templates.TemplateResponse("sprint_history.html", _ctx(request, team=team, sprints=sprint_data))


@router.get("/sprint/{sprint_id}", response_class=HTMLResponse)
async def sprint_page(request: Request, sprint_id: int):
    sprint = get_sprint(sprint_id)
    status = get_sprint_status(sprint)
    team = get_team(sprint["team_id"])

    if status != "closed":
        from src.clickup_client import ClickUpClient
        from src.config import get_clickup_api_key
        client = ClickUpClient(get_clickup_api_key())
        raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"], space_id=team["clickup_space_id"], workspace_id=team.get("clickup_workspace_id"))
        tasks = [client.extract_task_data(t) for t in raw_tasks]
        # Detect and persist scope changes for active sprints
        if status == "active":
            from src.services.snapshot_service import detect_scope_changes
            detect_scope_changes(sprint_id, tasks, sprint_start_date=sprint.get("start_date"))
            snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint_id)}
            for t in tasks:
                if t["task_id"] not in snapshot_ids:
                    t["scope_change"] = "added"
                else:
                    t["scope_change"] = None
        else:
            for t in tasks:
                t["scope_change"] = None
    else:
        # For closed sprints, use final snapshot for accurate final status
        snapshot = get_forecast_snapshot(sprint_id)
        final = get_final_snapshot(sprint_id)
        changes = get_scope_changes(sprint_id)
        added_ids = {c["task_id"] for c in changes if c["change_type"] == "added"}
        removed_ids = {c["task_id"] for c in changes if c["change_type"] == "removed"}
        final_by_id = {t["task_id"]: t for t in final}

        tasks = []
        for t in snapshot:
            if t["task_id"] in added_ids:
                continue  # scope additions handled below
            if t["task_id"] in removed_ids:
                t["scope_change"] = "removed"
            elif final and final_by_id.get(t["task_id"], {}).get("task_status") not in ("complete", "closed"):
                t["scope_change"] = "unfinished"
                if t["task_id"] in final_by_id:
                    t["task_status"] = final_by_id[t["task_id"]]["task_status"]
            else:
                t["scope_change"] = None
                if t["task_id"] in final_by_id:
                    t["task_status"] = final_by_id[t["task_id"]]["task_status"]
            tasks.append(t)

        # Sort: unfinished first, then completed, then removed
        order = {"unfinished": 0, None: 1, "removed": 2}
        tasks.sort(key=lambda t: order.get(t.get("scope_change"), 1))

        # Scope additions at the end
        for c in changes:
            if c["change_type"] == "added":
                final_status = final_by_id.get(c["task_id"], {}).get("task_status", c.get("task_status", "unknown"))
                tasks.append({
                    **c,
                    "scope_change": "added",
                    "task_status": final_status,
                    "points": None,
                    "hours": None,
                })

    summary = get_sprint_summary(sprint_id) if status != "planning" else {}
    scope_changes = get_scope_changes(sprint_id) if status != "planning" else []
    progress = get_daily_progress_history(sprint_id) if status != "planning" else []

    # For active sprints, update summary with live task data
    if status == "active" and summary:
        completed_live = sum(1 for t in tasks if t.get("task_status") in ("complete", "closed"))
        summary["completed"] = completed_live
        summary["total_current"] = len(tasks)
        summary["completion_rate"] = completed_live / summary["forecasted"] if summary["forecasted"] > 0 else 0
        summary["velocity"] = completed_live
        summary["forecast_accuracy"] = completed_live / summary["forecasted"] if summary["forecasted"] > 0 else 0

    # Calculate sprint day and on_track status
    sprint_day = None
    on_track = None
    if status == "active" and sprint.get("start_date"):
        try:
            start = date.fromisoformat(str(sprint["start_date"]))
            sprint_day = (date.today() - start).days + 1
            if summary and summary.get("forecasted", 0) > 0:
                from src.services.trend_service import calculate_on_track_status
                ideal_remaining = summary["forecasted"] - (summary["forecasted"] / team["sprint_length_days"]) * sprint_day
                actual_remaining = summary["forecasted"] - summary.get("completed", 0)
                on_track = calculate_on_track_status(actual_remaining, max(ideal_remaining, 0))
        except (ValueError, TypeError):
            pass

    workload = []
    final_snapshot_data = []
    if status == "closed":
        from src.services.trend_service import get_workload_distribution
        workload = get_workload_distribution(sprint_id, team.get("metric_type", "task_count"))
        final_snapshot_data = get_final_snapshot(sprint_id)

    template = "sprint_live.html" if status != "closed" else "sprint_report.html"
    return templates.TemplateResponse(template, _ctx(
        request,
        sprint=sprint,
        status=status,
        team=team,
        tasks=tasks,
        summary=summary,
        scope_changes=scope_changes,
        progress_history=progress,
        sprint_day=sprint_day,
        on_track=on_track,
        team_members=[m["username"] for m in get_team_members(team["id"])],
        capacity=get_sprint_capacity(sprint["id"]),
        workload=workload,
        final_snapshot=final_snapshot_data,
    ))


@router.get("/teams/{team_id}/trends", response_class=HTMLResponse)
def team_trends_page(request: Request, team_id: int, range: int = 8):
    team = get_team(team_id)
    from src.services.trend_service import get_team_trends
    trends = get_team_trends(team_id, limit=range if range > 0 else None)
    return templates.TemplateResponse("team_trends.html", _ctx(request, team=team, trends=trends, range=range))
