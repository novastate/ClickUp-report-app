from fastapi import APIRouter, Request, Depends
from src.auth.middleware import get_current_user

router = APIRouter(prefix="/api/clickup", tags=["clickup"])

@router.get("/spaces")
async def list_spaces(request: Request, user=Depends(get_current_user)):
    client = request.state.user_client
    workspaces = await client.get_workspaces()
    result = []
    for ws in workspaces:
        spaces = await client.get_spaces(ws["id"])
        for space in spaces:
            result.append({"workspace": ws["name"], "workspace_id": ws["id"], "space_id": space["id"], "space_name": space["name"]})
    return result

@router.get("/folders/{space_id}")
async def list_folders(space_id: str, request: Request, user=Depends(get_current_user)):
    client = request.state.user_client
    folders = await client.get_folders(space_id)
    return [{"id": f["id"], "name": f["name"]} for f in folders]

@router.get("/teams/{workspace_id}")
async def list_clickup_teams(workspace_id: str, request: Request, user=Depends(get_current_user)):
    client = request.state.user_client
    teams = await client.get_teams(workspace_id)
    return [{"id": g["id"], "name": g["name"], "handle": g.get("handle", ""),
             "members": [{"id": m["id"], "username": m["username"]} for m in g.get("members", [])]}
            for g in teams]
