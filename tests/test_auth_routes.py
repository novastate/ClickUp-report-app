import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_ID", "client_abc")
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_SECRET", "secret_def")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    import importlib, src.config, src.auth.encryption, src.auth.oauth
    import src.auth.users, src.auth.sessions, src.auth.state, src.auth.middleware
    import src.routes.auth
    for m in (src.config, src.auth.encryption, src.auth.oauth,
              src.auth.users, src.auth.sessions, src.auth.state,
              src.auth.middleware, src.routes.auth):
        importlib.reload(m)
    from src.database import init_db
    init_db(str(tmp_path / "test.db"))
    from fastapi.templating import Jinja2Templates
    app = FastAPI()
    app.include_router(src.routes.auth.router)
    return app


def test_login_redirects_to_clickup(app):
    client = TestClient(app)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 307 or r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("https://app.clickup.com/api?")
    assert "client_id=client_abc" in location
    assert "redirect_uri=" in location
    assert "state=" in location


def test_login_persists_state_to_db(app):
    from src.database import get_connection
    from src.config import DB_PATH
    client = TestClient(app)
    r = client.get("/auth/login", follow_redirects=False)
    location = r.headers["location"]
    # Extract the state param from the redirect
    from urllib.parse import urlparse, parse_qs
    state = parse_qs(urlparse(location).query)["state"][0]
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT * FROM oauth_state WHERE state = ?", (state,)).fetchone()
    conn.close()
    assert row is not None


def test_callback_rejects_invalid_state(app):
    client = TestClient(app)
    r = client.get("/auth/callback?code=abc&state=fake_state", follow_redirects=False)
    assert r.status_code == 400


def test_callback_rejects_missing_code(app):
    from src.auth.state import create_state
    state = create_state()
    client = TestClient(app)
    r = client.get(f"/auth/callback?state={state}", follow_redirects=False)
    assert r.status_code == 400


def test_callback_handles_oauth_denial(app):
    from src.auth.state import create_state
    state = create_state()
    client = TestClient(app)
    r = client.get(f"/auth/callback?error=access_denied&state={state}",
                   follow_redirects=False)
    # Expect 200 with error template, not a 302
    assert r.status_code == 200
    assert "denied" in r.text.lower() or "avbruten" in r.text.lower() or "error" in r.text.lower()


def _mock_token_response(token):
    resp = AsyncMock()
    resp.json = MagicMock(return_value={"access_token": token})
    resp.raise_for_status = lambda: None
    return resp


def _mock_user_response(uid, email, username):
    resp = AsyncMock()
    resp.json = MagicMock(return_value={
        "user": {"id": uid, "email": email, "username": username,
                 "color": "#ccc", "profile_picture": None}
    })
    resp.raise_for_status = lambda: None
    return resp


def _mock_workspaces_response(workspaces):
    resp = AsyncMock()
    resp.json = MagicMock(return_value={"teams": workspaces})
    resp.raise_for_status = lambda: None
    return resp


def test_callback_creates_user_token_session_and_redirects_when_one_workspace(app):
    from src.auth.state import create_state
    from src.auth.users import get_user, get_user_token
    state = create_state()

    with patch("httpx.AsyncClient.post",
               return_value=_mock_token_response("oauth_abc")), \
         patch("httpx.AsyncClient.get",
               side_effect=[
                   _mock_user_response(12345, "a@x.se", "anna"),
                   _mock_workspaces_response([{"id": "ws1", "name": "Acme"}]),
               ]):
        client = TestClient(app)
        r = client.get(f"/auth/callback?code=the_code&state={state}",
                       follow_redirects=False)

    assert r.status_code == 302
    assert r.headers["location"] == "/"
    assert "sprint_reporter_session" in r.cookies
    # User and token stored
    assert get_user("12345") is not None
    assert get_user_token("12345") == "oauth_abc"


def test_callback_redirects_to_workspace_picker_when_multiple_workspaces(app):
    from src.auth.state import create_state
    state = create_state()

    with patch("httpx.AsyncClient.post",
               return_value=_mock_token_response("oauth_abc")), \
         patch("httpx.AsyncClient.get",
               side_effect=[
                   _mock_user_response(12345, "a@x.se", "anna"),
                   _mock_workspaces_response([
                       {"id": "ws1", "name": "Acme"},
                       {"id": "ws2", "name": "Side"},
                   ]),
               ]):
        client = TestClient(app)
        r = client.get(f"/auth/callback?code=the_code&state={state}",
                       follow_redirects=False)

    assert r.status_code == 302
    assert r.headers["location"] == "/auth/workspace"


def test_callback_state_is_one_shot(app):
    """A state can only be consumed once — replay is rejected."""
    from src.auth.state import create_state
    state = create_state()

    with patch("httpx.AsyncClient.post",
               return_value=_mock_token_response("oauth_abc")), \
         patch("httpx.AsyncClient.get",
               side_effect=[
                   _mock_user_response(12345, "a@x.se", "anna"),
                   _mock_workspaces_response([{"id": "ws1", "name": "Acme"}]),
               ]):
        client = TestClient(app)
        r1 = client.get(f"/auth/callback?code=the_code&state={state}",
                        follow_redirects=False)
        assert r1.status_code == 302

    # Replay with same state
    client2 = TestClient(app)
    r2 = client2.get(f"/auth/callback?code=the_code&state={state}",
                     follow_redirects=False)
    assert r2.status_code == 400
