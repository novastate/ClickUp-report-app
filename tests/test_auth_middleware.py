import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_ID", "x")
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_SECRET", "y")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://x/cb")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    import importlib, src.config, src.auth.encryption, src.auth.users, src.auth.sessions, src.auth.middleware
    importlib.reload(src.config)
    importlib.reload(src.auth.encryption)
    importlib.reload(src.auth.users)
    importlib.reload(src.auth.sessions)
    importlib.reload(src.auth.middleware)
    from src.database import init_db
    init_db(str(tmp_path / "test.db"))
    from src.auth.users import upsert_user, save_user_token
    from src.auth.middleware import get_current_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz", scopes=None)

    app = FastAPI()

    @app.get("/protected")
    def protected(user=Depends(get_current_user)):
        return {"user_id": user["id"], "username": user["username"]}

    return app


def test_no_cookie_returns_401(app):
    client = TestClient(app)
    r = client.get("/protected")
    assert r.status_code == 401


def test_invalid_cookie_returns_401(app):
    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", "totally_fake")
    r = client.get("/protected")
    assert r.status_code == 401


def test_valid_session_returns_user(app):
    from src.auth.sessions import create_session
    sid = create_session(user_id="u1", active_workspace_id="ws_1")
    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    r = client.get("/protected")
    assert r.status_code == 200
    assert r.json() == {"user_id": "u1", "username": "anna"}


def test_valid_session_rolls_expiry(app):
    from src.auth.sessions import create_session, get_session
    from src.database import get_connection
    from src.config import DB_PATH
    from datetime import datetime, timedelta
    sid = create_session(user_id="u1", active_workspace_id="ws_1")
    # Squash expiry to 1 hour from now
    near = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    conn = get_connection(DB_PATH)
    conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (near, sid))
    conn.commit()
    conn.close()

    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    client.get("/protected")

    s = get_session(sid)
    new_exp = datetime.fromisoformat(s["expires_at"])
    assert new_exp > datetime.utcnow() + timedelta(days=29)


def test_clickup_401_clears_token_and_session(monkeypatch, tmp_path):
    """When the user_client gets 401 from ClickUp, the next request must require re-login."""
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("COOKIE_SECURE", "false")
    import importlib, src.config, src.auth.encryption, src.auth.users, src.auth.sessions
    import src.auth.middleware
    for m in (src.config, src.auth.encryption, src.auth.users,
              src.auth.sessions, src.auth.middleware):
        importlib.reload(m)
    from src.database import init_db
    init_db(str(tmp_path / "test.db"))
    from src.auth.users import upsert_user, save_user_token, get_user_token
    from src.auth.sessions import create_session, get_session
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz", scopes=None)
    sid = create_session(user_id="u1", active_workspace_id="ws_1")

    from fastapi import FastAPI, Depends, Request
    from fastapi.testclient import TestClient
    from src.auth.middleware import get_current_user
    from src.clickup_client import ClickUpError
    from app import auth_exception_handler
    from fastapi import HTTPException

    app = FastAPI()
    app.add_exception_handler(HTTPException, auth_exception_handler)
    app.add_exception_handler(ClickUpError, lambda r, e: src.auth.middleware.handle_clickup_error(r, e))

    @app.get("/explodes")
    def boom(request: Request, user=Depends(get_current_user)):
        raise ClickUpError("token revoked", status_code=401)

    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    r = client.get("/explodes", follow_redirects=False)

    # Token + session cleared
    assert get_user_token("u1") is None
    assert get_session(sid) is None
    # Response should redirect
    assert r.status_code == 302
