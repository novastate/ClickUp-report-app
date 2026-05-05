from src.database import init_db, get_connection


def test_init_db_creates_users_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    conn.close()
    assert cols == {"id", "email", "username", "color", "profile_picture",
                    "created_at", "updated_at"}


def test_init_db_creates_user_tokens_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_tokens)").fetchall()}
    conn.close()
    assert cols == {"user_id", "encrypted_access_token", "scopes", "granted_at"}


def test_init_db_creates_sessions_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    conn.close()
    assert cols == {"session_id", "user_id", "active_workspace_id",
                    "created_at", "expires_at", "last_seen"}


def test_init_db_creates_oauth_state_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(oauth_state)").fetchall()}
    conn.close()
    assert cols == {"state", "created_at"}


def test_init_db_adds_workspace_id_to_teams(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(teams)").fetchall()}
    conn.close()
    assert "workspace_id" in cols


def test_init_db_is_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    init_db(db)  # must not raise
    conn = get_connection(db)
    n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    conn.close()
    assert n == 0


def test_workspace_id_backfilled_from_clickup_workspace_id(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    conn.execute("""
        INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id)
        VALUES ('Acme', 'ws_42', 'sp_1', 'fld_1')
    """)
    conn.commit()
    conn.close()
    # Now re-init to trigger the backfill
    init_db(db)
    conn = get_connection(db)
    row = conn.execute("SELECT workspace_id FROM teams WHERE name = 'Acme'").fetchone()
    conn.close()
    assert row["workspace_id"] == "ws_42"
