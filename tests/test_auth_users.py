import os
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib
    import src.config as cfg_mod
    importlib.reload(cfg_mod)
    import src.auth.encryption as enc_mod
    importlib.reload(enc_mod)
    import src.auth.users as users_mod
    importlib.reload(users_mod)
    from src.database import init_db
    init_db(db)
    yield


def test_upsert_creates_new_user():
    from src.auth.users import upsert_user, get_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color="#ff0000", profile_picture="http://i/a")
    u = get_user("u1")
    assert u["id"] == "u1"
    assert u["email"] == "a@x.se"
    assert u["username"] == "anna"


def test_upsert_updates_existing_user():
    from src.auth.users import upsert_user, get_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color="#ff0000", profile_picture=None)
    upsert_user(id="u1", email="a@x.se", username="anna2",
                color="#00ff00", profile_picture="http://i/a2")
    u = get_user("u1")
    assert u["username"] == "anna2"
    assert u["color"] == "#00ff00"


def test_get_user_returns_none_when_missing():
    from src.auth.users import get_user
    assert get_user("nope") is None


def test_save_and_get_token_roundtrip():
    from src.auth.users import upsert_user, save_user_token, get_user_token
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz_123", scopes="read")
    assert get_user_token("u1") == "oauth_xyz_123"


def test_save_token_replaces_existing():
    from src.auth.users import upsert_user, save_user_token, get_user_token
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="first", scopes=None)
    save_user_token(user_id="u1", access_token="second", scopes=None)
    assert get_user_token("u1") == "second"


def test_token_is_encrypted_in_db():
    """Verify the raw DB row holds ciphertext, not plaintext."""
    from src.auth.users import upsert_user, save_user_token
    from src.database import get_connection
    from src.config import DB_PATH
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="plain_token_value", scopes=None)
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT encrypted_access_token FROM user_tokens WHERE user_id = 'u1'").fetchone()
    conn.close()
    assert row["encrypted_access_token"] != "plain_token_value"
    assert row["encrypted_access_token"].startswith("gAAAAA")  # Fernet ciphertext prefix


def test_delete_user_token_removes_row():
    from src.auth.users import upsert_user, save_user_token, get_user_token, delete_user_token
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="t", scopes=None)
    delete_user_token("u1")
    assert get_user_token("u1") is None
