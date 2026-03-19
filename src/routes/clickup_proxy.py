from fastapi import APIRouter
from src.clickup_client import ClickUpClient
from src.config import get_clickup_api_key

router = APIRouter(prefix="/api/clickup", tags=["clickup"])

@router.get("/spaces")
async def list_spaces():
    client = ClickUpClient(get_clickup_api_key())
    workspaces = await client.get_workspaces()
    result = []
    for ws in workspaces:
        spaces = await client.get_spaces(ws["id"])
        for space in spaces:
            result.append({"workspace": ws["name"], "space_id": space["id"], "space_name": space["name"]})
    return result

@router.get("/folders/{space_id}")
async def list_folders(space_id: str):
    client = ClickUpClient(get_clickup_api_key())
    folders = await client.get_folders(space_id)
    return [{"id": f["id"], "name": f["name"]} for f in folders]
