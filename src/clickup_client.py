import httpx
from typing import Optional

BASE_URL = "https://api.clickup.com/api/v2"

class ClickUpClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": api_key}

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{path}",
                headers=self.headers,
                params=params or {},
                timeout=30.0,
            )
            response.raise_for_status()
            return await response.json()

    async def get_workspaces(self) -> list[dict]:
        data = await self._get("/team")
        return data.get("teams", [])

    async def get_spaces(self, team_id: str) -> list[dict]:
        data = await self._get(f"/team/{team_id}/space", {"archived": "false"})
        return data.get("spaces", [])

    async def get_folders(self, space_id: str) -> list[dict]:
        data = await self._get(f"/space/{space_id}/folder")
        return data.get("folders", [])

    async def get_folder_lists(self, folder_id: str) -> list[dict]:
        data = await self._get(f"/folder/{folder_id}/list")
        return data.get("lists", [])

    async def get_list_tasks(self, list_id: str) -> list[dict]:
        all_tasks = []
        page = 0
        while True:
            data = await self._get(
                f"/list/{list_id}/task",
                {"include_closed": "true", "subtasks": "true", "page": str(page)},
            )
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)
            if len(tasks) < 100:
                break
            page += 1
        return all_tasks

    def extract_task_data(self, raw_task: dict) -> dict:
        assignees = raw_task.get("assignees", [])
        time_estimate = raw_task.get("time_estimate")
        return {
            "task_id": raw_task["id"],
            "task_name": raw_task["name"],
            "task_status": raw_task["status"]["status"],
            "assignee_name": assignees[0]["username"] if assignees else None,
            "points": raw_task.get("points"),
            "hours": round(time_estimate / 3_600_000, 2) if time_estimate else None,
        }
