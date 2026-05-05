"""Auth routes: login, callback, workspace picker, logout."""
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from src.auth.oauth import (
    build_authorize_url,
    exchange_code,
    fetch_user,
    fetch_workspaces,
)
from src.auth.sessions import create_session
from src.auth.state import create_state, consume_state
from src.auth.users import upsert_user, save_user_token
from src.config import COOKIE_SECURE

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")

COOKIE_NAME = "sprint_reporter_session"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


@router.get("/login")
def login(request: Request):
    """Redirect to ClickUp's authorization page with a fresh state."""
    state = create_state()
    url = build_authorize_url(state=state)
    log.info("Redirecting to ClickUp authorize")
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def callback(request: Request, code: str | None = None,
                   state: str | None = None, error: str | None = None):
    """Handle ClickUp's OAuth redirect.

    On success: exchange code, fetch user + workspaces, store, set cookie, redirect.
    On error: render the auth error template.
    On missing/invalid state: 400."""

    if not state or not consume_state(state):
        log.warning("OAuth callback rejected: invalid or missing state")
        raise HTTPException(status_code=400, detail="invalid_state")

    if error:
        log.info("OAuth callback received error=%s", error)
        return templates.TemplateResponse(
            "auth/error.html",
            {"request": request, "error": error},
        )

    if not code:
        log.warning("OAuth callback rejected: missing code")
        raise HTTPException(status_code=400, detail="missing_code")

    access_token = await exchange_code(code)
    user_data = await fetch_user(access_token)
    workspaces = await fetch_workspaces(access_token)

    upsert_user(
        id=user_data["id"],
        email=user_data["email"],
        username=user_data["username"],
        color=user_data["color"],
        profile_picture=user_data["profile_picture"],
    )
    save_user_token(user_id=user_data["id"], access_token=access_token, scopes=None)

    if len(workspaces) == 1:
        active_ws = workspaces[0]["id"]
        next_path = "/"
    else:
        active_ws = None
        next_path = "/auth/workspace"

    sid = create_session(user_id=user_data["id"], active_workspace_id=active_ws)
    log.info("Login successful for user=%s (%d workspace(s))",
             user_data["id"], len(workspaces))

    response = RedirectResponse(next_path, status_code=302)
    response.set_cookie(
        key=COOKIE_NAME, value=sid,
        max_age=COOKIE_MAX_AGE, httponly=True,
        samesite="lax", secure=COOKIE_SECURE,
    )
    return response
