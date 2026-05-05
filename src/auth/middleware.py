"""FastAPI dependency for auth-required routes.

Usage:
    from src.auth.middleware import get_current_user

    @router.get("/something")
    def handler(request: Request, user = Depends(get_current_user)):
        client = request.state.user_client  # ClickUpClient with user's token
        ...
"""
import logging
from fastapi import Request, HTTPException
from src.auth.sessions import get_session, roll_session
from src.auth.users import get_user, get_user_token
from src.clickup_client import get_user_client

log = logging.getLogger(__name__)
COOKIE_NAME = "sprint_reporter_session"


def get_current_user(request: Request) -> dict:
    """Look up the session cookie, validate it, populate request.state.

    On success, sets:
      request.state.user                  — dict from users table
      request.state.session_id            — the session_id
      request.state.active_workspace_id   — selected workspace, may be None
      request.state.user_client           — ClickUpClient with the user's OAuth token

    Raises HTTPException(401) on missing/expired/broken session.
    """
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="not_authenticated")

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="session_expired")

    user = get_user(session["user_id"])
    if not user:
        log.warning("Session %s references missing user %s", session_id, session["user_id"])
        raise HTTPException(status_code=401, detail="user_missing")

    token = get_user_token(user["id"])
    if not token:
        log.warning("User %s has session but no token (revoked?)", user["id"])
        raise HTTPException(status_code=401, detail="token_missing")

    # Roll expiry on every authenticated request
    roll_session(session_id)

    request.state.user = user
    request.state.session_id = session_id
    request.state.active_workspace_id = session.get("active_workspace_id")
    request.state.user_client = get_user_client(token)
    return user


from fastapi.responses import RedirectResponse, JSONResponse
from src.auth.users import delete_user_token
from src.auth.sessions import delete_sessions_for_user, delete_session


def handle_clickup_error(request: Request, exc) -> RedirectResponse | JSONResponse:
    """Catch ClickUpError. On 401, treat as token revoked: delete token + sessions
    and redirect to login (or 401 JSON for AJAX)."""
    from src.clickup_client import ClickUpError
    if not isinstance(exc, ClickUpError) or exc.status_code != 401:
        # Re-raise non-401 ClickUp errors as 502
        return JSONResponse({"detail": str(exc)}, status_code=502)

    user = getattr(request.state, "user", None)
    sid = getattr(request.state, "session_id", None)
    if user:
        log.warning("ClickUp 401 for user %s — purging token and sessions", user["id"])
        delete_user_token(user["id"])
        delete_sessions_for_user(user["id"])
    elif sid:
        delete_session(sid)

    accept = request.headers.get("accept", "")
    is_json_request = "application/json" in accept and "text/html" not in accept
    if is_json_request or request.url.path.startswith("/api"):
        return JSONResponse({"detail": "session_expired"}, status_code=401)
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response
