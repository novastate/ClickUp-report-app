"""Auth routes: login, callback, workspace picker, logout."""
import logging
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from src.auth.middleware import get_current_user
from src.auth.oauth import (
    build_authorize_url,
    exchange_code,
    fetch_user,
    fetch_workspaces,
)
from src.auth.sessions import create_session, delete_session, set_active_workspace
from src.auth.state import create_state, consume_state
from src.auth.users import get_user_token, save_user_token, upsert_user
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


@router.get("/workspace", response_class=HTMLResponse)
async def workspace_get(request: Request, user=Depends(get_current_user)):
    """Show the workspace picker. Fetches workspaces fresh from ClickUp."""
    token = get_user_token(user["id"])
    workspaces = await fetch_workspaces(token)
    return templates.TemplateResponse(
        "auth/workspace.html",
        {"request": request, "workspaces": workspaces, "user": user},
    )


@router.post("/workspace")
def workspace_post(request: Request, workspace_id: str = Form(...),
                   user=Depends(get_current_user)):
    """Save the selected workspace on the session."""
    set_active_workspace(request.state.session_id, workspace_id)
    log.info("User %s selected workspace %s", user["id"], workspace_id)
    return RedirectResponse("/", status_code=302)


@router.post("/logout")
def logout(request: Request):
    """Delete the session row, clear the cookie, redirect to login."""
    sid = request.cookies.get(COOKIE_NAME)
    if sid:
        delete_session(sid)
        log.info("Logged out session=%s", sid[:8])
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response
