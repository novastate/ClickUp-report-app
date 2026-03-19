from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from src.services.team_service import get_all_teams, get_team, get_team_members
from src.services.sprint_service import get_team_sprints, get_sprint, get_sprint_status
from src.services.trend_service import get_sprint_summary
from src.services.snapshot_service import get_scope_changes, get_daily_progress_history, get_forecast_snapshot
from src.config import get_clickup_api_key, DB_PATH
from src.database import set_setting
from datetime import datetime, date

templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["pages"])


def _ctx(request, **kwargs):
    kwargs["request"] = request
    kwargs["nav_teams"] = get_all_teams()
    return kwargs


def _needs_setup() -> bool:
    return not get_clickup_api_key()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    if _needs_setup():
        return RedirectResponse("/setup")
    teams = get_all_teams()
    for team in teams:
        sprints = get_team_sprints(team["id"])
        for s in sprints:
            if get_sprint_status(s) == "active":
                return RedirectResponse(f"/sprint/{s['id']}")
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
    return templates.TemplateResponse("team_settings.html", _ctx(request, team=team))


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
        # Mark scope changes for active sprints
        if status == "active":
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
        # For closed sprints, reconstruct task list from snapshot + scope changes
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
                tasks.append({
                    **c,
                    "scope_change": "added",
                    "points": None,
                    "hours": None,
                })

    summary = get_sprint_summary(sprint_id) if status != "planning" else {}
    scope_changes = get_scope_changes(sprint_id) if status != "planning" else []
    progress = get_daily_progress_history(sprint_id) if status != "planning" else []

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
    ))


@router.get("/teams/{team_id}/trends", response_class=HTMLResponse)
def team_trends_page(request: Request, team_id: int, range: int = 8):
    team = get_team(team_id)
    from src.services.trend_service import get_team_trends
    trends = get_team_trends(team_id, limit=range if range > 0 else None)
    return templates.TemplateResponse("team_trends.html", _ctx(request, team=team, trends=trends, range=range))
