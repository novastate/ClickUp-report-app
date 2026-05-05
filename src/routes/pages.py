from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from src.services.team_service import get_all_teams, get_team, get_team_members
from src.services.sprint_service import get_team_sprints, get_sprint, get_sprint_status, get_sprint_capacity
from src.services.trend_service import get_sprint_summary
from src.services.snapshot_service import get_scope_changes, get_daily_progress_history, get_forecast_snapshot, get_final_snapshot
from src.config import get_clickup_api_key, DB_PATH
from src.database import set_setting
from src.auth.middleware import get_current_user
from src.auth.oauth import fetch_workspaces as oauth_fetch_workspaces
from src.auth.users import get_user_token
from datetime import datetime, date

templates = Jinja2Templates(directory="templates")

import re as _re

def _display_name(name):
    if not name:
        return name
    return _re.sub(r"\s*\([^)]*\)\s*$", "", str(name)).strip()

templates.env.filters["display_name"] = _display_name


def _status_label(state):
    return {"planning": "Forecast", "active": "Active", "closed": "Closed"}.get(state, state)


templates.env.filters["status_label"] = _status_label
router = APIRouter(tags=["pages"])


def _ctx(request, breadcrumbs=None, team_sub_nav_active=None, **kwargs):
    kwargs["request"] = request
    kwargs["nav_teams"] = _scoped_teams(request)
    kwargs["breadcrumbs"] = breadcrumbs or []
    kwargs["team_sub_nav_active"] = team_sub_nav_active
    kwargs["current_user"] = getattr(request.state, "user", None)
    kwargs["active_workspace_id"] = getattr(request.state, "active_workspace_id", None)
    kwargs["user_workspaces"] = getattr(request.state, "user_workspaces", [])
    return kwargs


def _scoped_teams(request):
    """Return teams filtered to the active workspace (if set)."""
    ws = getattr(request.state, "active_workspace_id", None)
    all_teams = get_all_teams()
    if not ws:
        return all_teams
    return [t for t in all_teams if t.get("workspace_id") in (ws, None)]


def _breadcrumbs(*pairs):
    """Build a breadcrumbs list. Each pair is (label, href). Pass None as href for the last entry."""
    return [{"label": label, "href": href} for label, href in pairs]


def _needs_setup() -> bool:
    """Setup is needed only if no service key is configured anywhere.
    OAuth users don't trigger this; this is for the cron job."""
    from src.config import get_service_api_key
    return not get_service_api_key()


def _no_users_yet() -> bool:
    """Bootstrap mode: allow /setup if no users have ever logged in.
    After the first OAuth login, /setup requires authentication."""
    from src.database import get_connection
    from src.config import DB_PATH
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    conn.close()
    return row["n"] == 0


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user=Depends(get_current_user)):
    if _needs_setup():
        return RedirectResponse("/setup")
    token = get_user_token(user["id"])
    request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []
    teams = _scoped_teams(request)
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
    if not _no_users_yet():
        # Once users exist, /setup requires authentication
        try:
            get_current_user(request)
        except HTTPException:
            return RedirectResponse("/auth/login", status_code=302)
    current_key = get_clickup_api_key()
    masked = f"pk_...{current_key[-8:]}" if current_key and len(current_key) > 12 else ""
    return templates.TemplateResponse("setup.html", _ctx(request, masked_key=masked, has_key=bool(current_key)))


@router.post("/setup")
async def save_setup(request: Request):
    if not _no_users_yet():
        try:
            get_current_user(request)
        except HTTPException:
            return RedirectResponse("/auth/login", status_code=302)
    form = await request.form()
    api_key = form.get("api_key", "").strip()
    if api_key:
        set_setting(DB_PATH, "clickup_api_key", api_key)
    return RedirectResponse("/teams/new", status_code=303)


@router.get("/teams/new", response_class=HTMLResponse)
def new_team_page(request: Request, user=Depends(get_current_user)):
    if _needs_setup():
        return RedirectResponse("/setup")
    return templates.TemplateResponse("team_settings.html", _ctx(
        request,
        team=None,
        breadcrumbs=_breadcrumbs(("Home", "/"), ("New Team", None)),
    ))


@router.get("/teams/{team_id}/settings", response_class=HTMLResponse)
def team_settings_page(request: Request, team_id: int, user=Depends(get_current_user)):
    team = get_team(team_id)
    members = get_team_members(team_id) if team else []
    return templates.TemplateResponse("team_settings.html", _ctx(
        request,
        team=team,
        current_members=members,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Settings", None)),
        team_sub_nav_active="settings",
    ))


@router.get("/teams/{team_id}/sprints", response_class=HTMLResponse)
async def sprint_history_page(request: Request, team_id: int, user=Depends(get_current_user)):
    token = get_user_token(user["id"])
    request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []
    team = get_team(team_id)
    sprints = get_team_sprints(team_id)
    sprint_data = []
    for s in sprints:
        s["status"] = get_sprint_status(s)
        if s["status"] == "closed":
            s["summary"] = get_sprint_summary(s["id"])
        sprint_data.append(s)
    return templates.TemplateResponse("sprint_history.html", _ctx(
        request,
        team=team,
        sprints=sprint_data,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], None)),
        team_sub_nav_active="sprints",
    ))


@router.get("/sprint/{sprint_id}", response_class=HTMLResponse)
async def sprint_page(request: Request, sprint_id: int, user=Depends(get_current_user)):
    sprint = get_sprint(sprint_id)
    status = get_sprint_status(sprint)
    team = get_team(sprint["team_id"])

    if status != "closed":
        client = request.state.user_client
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

    # Compute prev/next sprint for navigation (by start_date within the same team)
    team_sprints = sorted(
        [s for s in get_team_sprints(team["id"]) if s.get("start_date")],
        key=lambda s: str(s["start_date"]),
    )
    prev_sprint = None
    next_sprint = None
    for i, s in enumerate(team_sprints):
        if s["id"] == sprint["id"]:
            if i > 0:
                prev_sprint = team_sprints[i - 1]
            if i < len(team_sprints) - 1:
                next_sprint = team_sprints[i + 1]
            break

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
        prev_sprint=prev_sprint,
        next_sprint=next_sprint,
        breadcrumbs=_breadcrumbs(
            ("Home", "/"),
            (team["name"], f"/teams/{team['id']}/sprints"),
            (_display_name(sprint["name"]), None),
        ),
        team_sub_nav_active="sprints",
    ))


@router.get("/teams/{team_id}/trends", response_class=HTMLResponse)
def team_trends_page(request: Request, team_id: int, range: int = 8, user=Depends(get_current_user)):
    team = get_team(team_id)
    from src.services.trend_service import get_team_trends
    trends = get_team_trends(team_id, limit=range if range > 0 else None)
    # Always count ALL closed sprints (independent of the range filter) so we know
    # which filter buttons to show
    all_trends = get_team_trends(team_id, limit=None)
    closed_count = len(all_trends.get("sprints", []))
    return templates.TemplateResponse("team_trends.html", _ctx(
        request,
        team=team,
        trends=trends,
        range=range,
        closed_count=closed_count,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Trends", None)),
        team_sub_nav_active="trends",
    ))
