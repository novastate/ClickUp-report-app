import asyncio
import logging
import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.clickup.com/api/v2"

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_BASE = 1.0   # seconds; doubles each retry → 1, 2, 4


class ClickUpError(Exception):
    """Raised when a ClickUp API call fails permanently (after retries)
    or with a non-retriable status code."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ClickUpClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": api_key}

    async def _get(self, path: str, params: dict = None) -> dict:
        url = f"{BASE_URL}{path}"
        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    response = await client.get(url, headers=self.headers, params=params or {})
                if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                    delay = BACKOFF_BASE * (2 ** attempt)
                    log.warning(
                        "ClickUp %s returned %d; retrying in %.1fs (attempt %d/%d)",
                        path, response.status_code, delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt < MAX_RETRIES:
                    delay = BACKOFF_BASE * (2 ** attempt)
                    log.warning(
                        "ClickUp %s network error (%s); retrying in %.1fs (attempt %d/%d)",
                        path, type(e).__name__, delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue
                log.error("ClickUp %s exhausted retries on network error: %s", path, e)
                raise ClickUpError(f"Network error after {MAX_RETRIES} retries: {e}") from e
            except httpx.HTTPStatusError as e:
                # 4xx (non-429) — caller's fault, don't retry
                log.error(
                    "ClickUp %s returned %d (non-retriable); body=%s",
                    path, e.response.status_code, e.response.text[:500],
                )
                raise ClickUpError(
                    f"ClickUp returned {e.response.status_code} for {path}",
                    status_code=e.response.status_code,
                    body=e.response.text[:500],
                ) from e
        # Loop exited because retries exhausted on a retriable status
        log.error(
            "ClickUp %s returned %d after %d retries",
            path, response.status_code if response is not None else -1, MAX_RETRIES,
        )
        raise ClickUpError(
            f"ClickUp {path} returned {response.status_code if response is not None else 'no response'} after {MAX_RETRIES} retries",
            status_code=response.status_code if response is not None else None,
            body=response.text[:500] if response is not None else None,
        )

    async def get_workspaces(self) -> list[dict]:
        data = await self._get("/team")
        return data.get("teams", [])

    async def get_spaces(self, team_id: str) -> list[dict]:
        data = await self._get(f"/team/{team_id}/space", {"archived": "false"})
        return data.get("spaces", [])

    async def get_folders(self, space_id: str) -> list[dict]:
        data = await self._get(f"/space/{space_id}/folder")
        return data.get("folders", [])

    async def get_teams(self, workspace_id: str) -> list[dict]:
        data = await self._get("/group", {"team_id": workspace_id})
        return data.get("groups", [])

    async def get_folder_lists(self, folder_id: str) -> list[dict]:
        data = await self._get(f"/folder/{folder_id}/list")
        return data.get("lists", [])

    async def get_list_tasks(self, list_id: str, **_kwargs) -> list[dict]:
        """Get all tasks in a list, including tasks in multiple lists (TIML)."""
        all_tasks = []
        page = 0
        while True:
            data = await self._get(
                f"/list/{list_id}/task",
                {
                    "include_closed": "true",
                    "subtasks": "true",
                    "include_timl": "true",
                    "page": str(page),
                },
            )
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)
            if len(tasks) < 100:
                break
            page += 1
        # Filter out subtasks whose parent is also in this list (avoid double-counting)
        task_ids = {t["id"] for t in all_tasks}
        return [t for t in all_tasks if not t.get("parent") or t["parent"] not in task_ids]

    def extract_task_data(self, raw_task: dict) -> dict:
        assignees = raw_task.get("assignees", [])
        time_estimate = raw_task.get("time_estimate")
        time_by_user = raw_task.get("time_estimates_by_user", [])

        assignee_hours = []
        for entry in time_by_user:
            user = entry.get("user", {})
            ms = entry.get("time_estimate", 0) or 0
            assignee_hours.append({
                "name": user.get("username", "?"),
                "hours": round(ms / 3_600_000, 2),
            })

        # If no per-user breakdown, fall back to assignees with total split
        if not assignee_hours and assignees:
            total_h = round(time_estimate / 3_600_000, 2) if time_estimate else 0
            if len(assignees) == 1:
                assignee_hours = [{"name": assignees[0]["username"], "hours": total_h}]
            else:
                assignee_hours = [{"name": a["username"], "hours": 0} for a in assignees]

        return {
            "task_id": raw_task["id"],
            "task_name": raw_task["name"],
            "task_status": raw_task["status"]["status"],
            "assignee_name": ", ".join(a["username"] for a in assignees) if assignees else None,
            "assignee_hours": assignee_hours,
            "points": raw_task.get("points"),
            "hours": round(time_estimate / 3_600_000, 2) if time_estimate else None,
        }


def get_system_client() -> ClickUpClient:
    """Build a client for the impersonal background-job 'service account'.
    Reads CLICKUP_SERVICE_API_KEY (with legacy fallback to CLICKUP_API_KEY)."""
    from src.config import get_service_api_key
    return ClickUpClient(api_key=get_service_api_key())


def get_user_client(access_token: str) -> ClickUpClient:
    """Build a client for an authenticated user's request, using their OAuth token.
    The Authorization header format is identical to API keys for ClickUp."""
    return ClickUpClient(api_key=access_token)
