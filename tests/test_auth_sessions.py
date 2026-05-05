import pytest
from datetime import datetime, timedelta
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, src.config, src.auth.encryption, src.auth.sessions, src.auth.users
    importlib.reload(src.config)
    importlib.reload(src.auth.encryption)
    importlib.reload(src.auth.users)
    importlib.reload(src.auth.sessions)
    from src.database import init_db
    init_db(db)
    from src.auth.users import upsert_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    yield


def test_create_session_returns_id_and_persists():
    from src.auth.sessions import create_session, get_session
    sid = create_session(user_id="u1", active_workspace_id="ws_42")
    assert sid and len(sid) >= 32
    s = get_session(sid)
    assert s["user_id"] == "u1"
    assert s["active_workspace_id"] == "ws_42"


def test_get_session_returns_none_for_unknown():
    from src.auth.sessions import get_session
    assert get_session("nope") is None


def test_get_session_returns_none_for_expired():
    from src.auth.sessions import create_session, get_session
    from src.database import get_connection
    from src.config import DB_PATH
    sid = create_session(user_id="u1", active_workspace_id=None)
    conn = get_connection(DB_PATH)
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (past, sid))
    conn.commit()
    conn.close()
    assert get_session(sid) is None


def test_roll_session_extends_expiry():
    from src.auth.sessions import create_session, roll_session, get_session
    from src.database import get_connection
    from src.config import DB_PATH
    sid = create_session(user_id="u1", active_workspace_id=None)
    # Squash expiry
    conn = get_connection(DB_PATH)
    near = (datetime.utcnow() + timedelta(minutes=1)).isoformat()
    conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (near, sid))
    conn.commit()
    conn.close()

    roll_session(sid)
    s = get_session(sid)
    new_exp = datetime.fromisoformat(s["expires_at"])
    assert new_exp > datetime.utcnow() + timedelta(days=29)


def test_set_active_workspace():
    from src.auth.sessions import create_session, set_active_workspace, get_session
    sid = create_session(user_id="u1", active_workspace_id=None)
    set_active_workspace(sid, "ws_99")
    assert get_session(sid)["active_workspace_id"] == "ws_99"


def test_delete_session():
    from src.auth.sessions import create_session, delete_session, get_session
    sid = create_session(user_id="u1", active_workspace_id=None)
    delete_session(sid)
    assert get_session(sid) is None


def test_delete_sessions_for_user_clears_all():
    from src.auth.sessions import create_session, delete_sessions_for_user, get_session
    sid_a = create_session(user_id="u1", active_workspace_id=None)
    sid_b = create_session(user_id="u1", active_workspace_id=None)
    delete_sessions_for_user("u1")
    assert get_session(sid_a) is None
    assert get_session(sid_b) is None
