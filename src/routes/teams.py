from fastapi import APIRouter, HTTPException, Request, Depends
from src.models import TeamCreate, TeamUpdate
from src.services import team_service
from src.services.sprint_service import create_sprint_from_list, get_team_sprints, get_sprint_status, parse_iteration_dates
from src.services.trend_service import get_team_trends
from src.auth.middleware import get_current_user

router = APIRouter(prefix="/teams", tags=["teams"])

@router.get("")
def list_teams(user=Depends(get_current_user)):
    return team_service.get_all_teams()

@router.post("")
def create_team(body: TeamCreate, request: Request,
                user=Depends(get_current_user)):
    workspace_id = request.state.active_workspace_id
    team = team_service.create_team(
        body.name, body.clickup_workspace_id, body.clickup_space_id,
        body.clickup_folder_id, body.metric_type, body.capacity_mode,
        body.sprint_length_days, workspace_id_new=workspace_id,
        space_name=body.space_name,
    )
    if body.members:
        team_service.set_team_members(team["id"], [m.model_dump() for m in body.members])
    return team

@router.get("/{team_id}")
def get_team(team_id: int, user=Depends(get_current_user)):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team

@router.put("/{team_id}")
def update_team(team_id: int, body: TeamUpdate, user=Depends(get_current_user)):
    members = body.members
    updates = body.model_dump(exclude_none=True)
    updates.pop("members", None)
    team = team_service.update_team(team_id, **updates)
    if not team:
        raise HTTPException(404, "Team not found")
    if members is not None:
        team_service.set_team_members(team_id, [m.model_dump() for m in members])
    return team

@router.delete("/{team_id}")
def delete_team(team_id: int, user=Depends(get_current_user)):
    if not team_service.delete_team(team_id):
        raise HTTPException(404, "Team not found")
    return {"ok": True}

@router.get("/{team_id}/sprints")
def team_sprints(team_id: int, user=Depends(get_current_user)):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    sprints = get_team_sprints(team_id)
    for s in sprints:
        s["status"] = get_sprint_status(s)
    return sprints

@router.get("/{team_id}/trends")
def team_trends(team_id: int, limit: int = 8, user=Depends(get_current_user)):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return get_team_trends(team_id, limit=limit)

@router.post("/{team_id}/sync-sprints")
async def sync_sprints(team_id: int, request: Request,
                       user=Depends(get_current_user)):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    client = request.state.user_client
    lists = await client.get_folder_lists(team["clickup_folder_id"])
    synced = []
    for lst in lists:
        start, end = parse_iteration_dates(lst["name"])
        if not start:
            continue  # Skip non-sprint lists (e.g. Intake, Backlog)
        sprint = create_sprint_from_list(team["id"], lst["id"], lst["name"])
        synced.append(sprint)
    return {"synced": len(synced), "sprints": synced}


@router.post("/{team_id}/favorite")
def toggle_team_favorite(team_id: int, request: Request,
                         user=Depends(get_current_user)):
    """Toggle the current user's favorite status on this team.
    Returns {"favorited": bool}. 404 if the team is missing or not in the
    user's active workspace."""
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    active_ws = request.state.active_workspace_id
    # Workspace check: avoid leaking team existence across workspaces.
    if active_ws and team.get("workspace_id") and team["workspace_id"] != active_ws:
        raise HTTPException(404, "Team not found")
    from src.services.favorites_service import toggle_favorite
    favorited = toggle_favorite(user["id"], team_id)
    return {"favorited": favorited}
