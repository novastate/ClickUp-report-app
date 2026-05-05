import os
import sqlite3
import pytest


@pytest.fixture(autouse=True)
def _reset_dev_flags(monkeypatch):
    """Strip dev-only env vars that may leak in from a developer's local .env.

    AUTH_BYPASS and COOKIE_SECURE are loaded by `load_dotenv()` at config
    import. If a developer has them set in `.env` for local dev (e.g.
    AUTH_BYPASS=true to skip OAuth), tests would unintentionally inherit
    those values. Force defaults for every test."""
    # NOTE: setenv (not delenv). load_dotenv() runs at src.config import time
    # and reads .env directly; with delenv it would re-populate from there.
    # Setting explicit defaults blocks load_dotenv()'s override=False from
    # overwriting them.
    monkeypatch.setenv("AUTH_BYPASS", "false")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.delenv("CLICKUP_WORKSPACE_ID", raising=False)


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    os.environ["DB_PATH"] = db_path
    from src.database import init_db, get_connection
    init_db(db_path)
    yield db_path

@pytest.fixture
def mock_clickup_tasks():
    return [
        {
            "id": "task_1",
            "name": "Set up CI pipeline",
            "status": {"status": "to do"},
            "assignees": [{"username": "Anna"}],
            "points": 3,
            "time_estimate": None,
        },
        {
            "id": "task_2",
            "name": "API rate limiting",
            "status": {"status": "in progress"},
            "assignees": [{"username": "Erik"}],
            "points": 2,
            "time_estimate": 7200000,
        },
        {
            "id": "task_3",
            "name": "User dashboard redesign",
            "status": {"status": "complete"},
            "assignees": [{"username": "Marcus"}],
            "points": 5,
            "time_estimate": None,
        },
    ]
