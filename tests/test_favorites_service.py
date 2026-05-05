import pytest
from datetime import datetime


@pytest.fixture(autouse=True)
def _setup(monkeypatch, tmp_path):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, src.config, src.services.favorites_service
    importlib.reload(src.config)
    importlib.reload(src.services.favorites_service)
    from src.database import init_db, get_connection
    init_db(db)
    # Insert prerequisite rows: a user and a team. The user_favorites FKs require both.
    conn = get_connection(db)
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO users (id, email, username, color, profile_picture, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("u1", "a@x.se", "anna", None, None, now, now),
    )
    conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id) "
        "VALUES (?, ?, ?, ?)",
        ("LAN", "ws1", "sp1", "fld1"),
    )
    conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id) "
        "VALUES (?, ?, ?, ?)",
        ("WAN", "ws1", "sp1", "fld2"),
    )
    conn.commit()
    conn.close()
    yield


def test_toggle_favorite_adds_then_removes():
    from src.services.favorites_service import toggle_favorite, get_favorite_team_ids
    assert get_favorite_team_ids("u1") == set()
    assert toggle_favorite("u1", 1) is True
    assert get_favorite_team_ids("u1") == {1}
    assert toggle_favorite("u1", 1) is False
    assert get_favorite_team_ids("u1") == set()


def test_toggle_favorite_independent_per_user():
    from src.services.favorites_service import toggle_favorite, get_favorite_team_ids
    from src.database import get_connection
    from src.config import DB_PATH
    from datetime import datetime
    conn = get_connection(DB_PATH)
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO users (id, email, username, color, profile_picture, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("u2", "b@x.se", "bjorn", None, None, now, now),
    )
    conn.commit()
    conn.close()
    toggle_favorite("u1", 1)
    toggle_favorite("u2", 2)
    assert get_favorite_team_ids("u1") == {1}
    assert get_favorite_team_ids("u2") == {2}


def test_get_favorited_teams_returns_full_team_rows():
    from src.services.favorites_service import toggle_favorite, get_favorited_teams
    toggle_favorite("u1", 1)
    toggle_favorite("u1", 2)
    teams = get_favorited_teams("u1")
    assert len(teams) == 2
    names = {t["name"] for t in teams}
    assert names == {"LAN", "WAN"}
    # Returned rows should look like team_service.get_all_teams() rows
    assert all("clickup_space_id" in t for t in teams)


def test_get_favorited_teams_empty_for_unknown_user():
    from src.services.favorites_service import get_favorited_teams
    assert get_favorited_teams("never_existed") == []


def test_team_delete_cascades_to_favorites():
    from src.services.favorites_service import toggle_favorite, get_favorite_team_ids
    from src.database import get_connection
    from src.config import DB_PATH
    toggle_favorite("u1", 1)
    assert get_favorite_team_ids("u1") == {1}
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM teams WHERE id = 1")
    conn.commit()
    conn.close()
    assert get_favorite_team_ids("u1") == set()
