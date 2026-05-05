"""ClickUp OAuth client. Pure functions — no DB access here."""
import logging
from urllib.parse import urlencode
import httpx
from src.config import (
    CLICKUP_OAUTH_CLIENT_ID,
    CLICKUP_OAUTH_CLIENT_SECRET,
    OAUTH_REDIRECT_URI,
)

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://app.clickup.com/api"
TOKEN_URL = "https://api.clickup.com/api/v2/oauth/token"
API_BASE = "https://api.clickup.com/api/v2"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def build_authorize_url(state: str) -> str:
    """Return URL to redirect the user to for ClickUp authorization."""
    params = {
        "client_id": CLICKUP_OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Exchange the OAuth `code` for an access token. Returns the token string.
    Raises on non-2xx response."""
    params = {
        "client_id": CLICKUP_OAUTH_CLIENT_ID,
        "client_secret": CLICKUP_OAUTH_CLIENT_SECRET,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(TOKEN_URL, params=params)
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"ClickUp /oauth/token response missing access_token: {data}")
    log.info("OAuth code exchange succeeded")
    return token


async def fetch_user(access_token: str) -> dict:
    """Get the authenticated user's profile.
    Returns: {"id": str, "email": str, "username": str, "color": str, "profile_picture": str}"""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{API_BASE}/user",
            headers={"Authorization": access_token},
        )
    response.raise_for_status()
    u = response.json().get("user", {})
    return {
        "id": str(u.get("id")),
        "email": u.get("email", ""),
        "username": u.get("username"),
        "color": u.get("color"),
        "profile_picture": u.get("profile_picture"),
    }


async def fetch_workspaces(access_token: str) -> list[dict]:
    """List the workspaces the authenticated user belongs to.
    ClickUp calls them 'teams' in the API but the UI calls them 'Workspaces'."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{API_BASE}/team",
            headers={"Authorization": access_token},
        )
    response.raise_for_status()
    return response.json().get("teams", [])
