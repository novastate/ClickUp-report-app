import pytest
from datetime import datetime, timedelta
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, src.config, src.auth.state
    importlib.reload(src.config)
    importlib.reload(src.auth.state)
    from src.database import init_db
    init_db(db)
    yield


def test_create_state_returns_random_string():
    from src.auth.state import create_state
    a = create_state()
    b = create_state()
    assert a != b
    assert len(a) >= 32


def test_consume_state_returns_true_for_valid():
    from src.auth.state import create_state, consume_state
    s = create_state()
    assert consume_state(s) is True


def test_consume_state_is_one_shot():
    """consume_state returns True the first time, False on the second call."""
    from src.auth.state import create_state, consume_state
    s = create_state()
    assert consume_state(s) is True
    assert consume_state(s) is False


def test_consume_unknown_state_returns_false():
    from src.auth.state import consume_state
    assert consume_state("never_existed") is False


def test_consume_expired_state_returns_false():
    from src.auth.state import create_state, consume_state
    from src.database import get_connection
    from src.config import DB_PATH
    s = create_state()
    old = (datetime.utcnow() - timedelta(minutes=11)).isoformat()
    conn = get_connection(DB_PATH)
    conn.execute("UPDATE oauth_state SET created_at = ? WHERE state = ?", (old, s))
    conn.commit()
    conn.close()
    assert consume_state(s) is False


def test_cleanup_old_states_removes_expired_only():
    from src.auth.state import create_state, cleanup_old_states
    from src.database import get_connection
    from src.config import DB_PATH
    fresh = create_state()
    stale = create_state()
    conn = get_connection(DB_PATH)
    old = (datetime.utcnow() - timedelta(minutes=11)).isoformat()
    conn.execute("UPDATE oauth_state SET created_at = ? WHERE state = ?", (old, stale))
    conn.commit()
    conn.close()
    cleanup_old_states()
    conn = get_connection(DB_PATH)
    rows = {r["state"] for r in conn.execute("SELECT state FROM oauth_state").fetchall()}
    conn.close()
    assert fresh in rows
    assert stale not in rows
