from fastapi import APIRouter, HTTPException
from src.models import TeamCreate, TeamUpdate
from src.services import team_service
from src.services.sprint_service import create_sprint_from_list, get_team_sprints, get_sprint_status
from src.services.trend_service import get_team_trends
from src.clickup_client import ClickUpClient
from src.config import get_clickup_api_key

router = APIRouter(prefix="/teams", tags=["teams"])

@router.get("")
def list_teams():
    return team_service.get_all_teams()

@router.post("")
def create_team(body: TeamCreate):
    team = team_service.create_team(body.name, body.clickup_workspace_id, body.clickup_space_id, body.clickup_folder_id, body.metric_type, body.sprint_length_days)
    if body.members:
        team_service.set_team_members(team["id"], [m.model_dump() for m in body.members])
    return team

@router.get("/{team_id}")
def get_team(team_id: int):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team

@router.put("/{team_id}")
def update_team(team_id: int, body: TeamUpdate):
    updates = body.model_dump(exclude_none=True)
    team = team_service.update_team(team_id, **updates)
    if not team:
        raise HTTPException(404, "Team not found")
    return team

@router.delete("/{team_id}")
def delete_team(team_id: int):
    if not team_service.delete_team(team_id):
        raise HTTPException(404, "Team not found")
    return {"ok": True}

@router.get("/{team_id}/sprints")
def team_sprints(team_id: int):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    sprints = get_team_sprints(team_id)
    for s in sprints:
        s["status"] = get_sprint_status(s)
    return sprints

@router.get("/{team_id}/trends")
def team_trends(team_id: int, limit: int = 8):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return get_team_trends(team_id, limit=limit)

@router.post("/{team_id}/sync-sprints")
async def sync_sprints(team_id: int):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    client = ClickUpClient(get_clickup_api_key())
    lists = await client.get_folder_lists(team["clickup_folder_id"])
    synced = []
    for lst in lists:
        sprint = create_sprint_from_list(team["id"], lst["id"], lst["name"])
        synced.append(sprint)
    return {"synced": len(synced), "sprints": synced}
