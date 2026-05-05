import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import src.config as mod
    importlib.reload(mod)
    return mod


def test_oauth_env_vars_loaded(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        CLICKUP_OAUTH_CLIENT_ID="abc",
        CLICKUP_OAUTH_CLIENT_SECRET="def",
        OAUTH_REDIRECT_URI="http://localhost:8000/auth/callback",
        CLICKUP_SERVICE_API_KEY="pk_service_xyz",
    )
    assert cfg.CLICKUP_OAUTH_CLIENT_ID == "abc"
    assert cfg.CLICKUP_OAUTH_CLIENT_SECRET == "def"
    assert cfg.OAUTH_REDIRECT_URI == "http://localhost:8000/auth/callback"
    assert cfg.CLICKUP_SERVICE_API_KEY == "pk_service_xyz"


def test_cookie_secure_default_true(monkeypatch):
    # setenv to "" instead of delenv — load_dotenv() in _reload_config would
    # otherwise repopulate COOKIE_SECURE from a developer's local .env file.
    monkeypatch.setenv("COOKIE_SECURE", "")
    cfg = _reload_config(monkeypatch)
    assert cfg.COOKIE_SECURE is True


def test_cookie_secure_can_be_disabled(monkeypatch):
    cfg = _reload_config(monkeypatch, COOKIE_SECURE="false")
    assert cfg.COOKIE_SECURE is False


def test_get_service_api_key_prefers_new_var(monkeypatch):
    monkeypatch.setenv("CLICKUP_SERVICE_API_KEY", "pk_new")
    monkeypatch.setenv("CLICKUP_API_KEY", "pk_old")
    import src.config as mod
    importlib.reload(mod)
    assert mod.get_service_api_key() == "pk_new"


def test_get_service_api_key_falls_back_to_legacy(monkeypatch):
    monkeypatch.delenv("CLICKUP_SERVICE_API_KEY", raising=False)
    monkeypatch.setenv("CLICKUP_API_KEY", "pk_legacy")
    import src.config as mod
    importlib.reload(mod)
    assert mod.get_service_api_key() == "pk_legacy"
