import pytest
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
