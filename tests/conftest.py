import os
import sqlite3
import pytest

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
