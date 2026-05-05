"""Auth routes: login, callback, workspace picker, logout."""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from src.auth.oauth import build_authorize_url
from src.auth.state import create_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("/login")
def login(request: Request):
    """Redirect to ClickUp's authorization page with a fresh state."""
    state = create_state()
    url = build_authorize_url(state=state)
    log.info("Redirecting to ClickUp authorize")
    return RedirectResponse(url, status_code=302)
