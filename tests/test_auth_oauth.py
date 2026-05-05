import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse, parse_qs


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_ID", "client_abc")
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_SECRET", "secret_def")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY",
                       "Lp4XU3p1LpC8e2iEmHjJqQqFvXW8eJMcS6P-5nJyqNg=")
    import importlib, src.config, src.auth.oauth
    importlib.reload(src.config)
    importlib.reload(src.auth.oauth)


def test_build_authorize_url_contains_required_params():
    from src.auth.oauth import build_authorize_url
    url = build_authorize_url(state="state_xyz")
    parsed = urlparse(url)
    assert parsed.netloc == "app.clickup.com"
    assert parsed.path == "/api"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["client_abc"]
    assert qs["redirect_uri"] == ["http://localhost:8000/auth/callback"]
    assert qs["state"] == ["state_xyz"]


@pytest.mark.asyncio
async def test_exchange_code_returns_access_token():
    from src.auth.oauth import exchange_code
    mock_response = AsyncMock()
    mock_response.json = MagicMock(return_value={"access_token": "oauth_token_xyz"})
    mock_response.raise_for_status = lambda: None
    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        token = await exchange_code("the_code")
        assert token == "oauth_token_xyz"
        # verify call was made with correct params
        call = mock_post.call_args
        assert "oauth/token" in call.args[0]
        sent_params = call.kwargs.get("params") or call.kwargs.get("data") or {}
        assert sent_params["client_id"] == "client_abc"
        assert sent_params["client_secret"] == "secret_def"
        assert sent_params["code"] == "the_code"


@pytest.mark.asyncio
async def test_exchange_code_raises_on_error():
    from src.auth.oauth import exchange_code
    import httpx
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: (_ for _ in ()).throw(
        httpx.HTTPStatusError("bad", request=None, response=httpx.Response(401))
    )
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(Exception):
            await exchange_code("bad_code")


@pytest.mark.asyncio
async def test_fetch_user_returns_user_data():
    from src.auth.oauth import fetch_user
    mock_response = AsyncMock()
    mock_response.json = MagicMock(return_value={
        "user": {
            "id": 12345,
            "email": "a@x.se",
            "username": "anna",
            "color": "#ff0000",
            "profile_picture": "http://i/a",
        }
    })
    mock_response.raise_for_status = lambda: None
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        u = await fetch_user("token_xyz")
        assert u["id"] == "12345"  # coerced to string
        assert u["email"] == "a@x.se"
        assert u["username"] == "anna"


@pytest.mark.asyncio
async def test_fetch_workspaces_returns_list():
    from src.auth.oauth import fetch_workspaces
    mock_response = AsyncMock()
    mock_response.json = MagicMock(return_value={
        "teams": [
            {"id": "ws1", "name": "Acme Co", "color": "#000"},
            {"id": "ws2", "name": "Side Project", "color": "#fff"},
        ]
    })
    mock_response.raise_for_status = lambda: None
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        ws = await fetch_workspaces("token_xyz")
        assert len(ws) == 2
        assert ws[0]["id"] == "ws1"
        assert ws[0]["name"] == "Acme Co"
