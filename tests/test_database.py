from src.database import init_db, get_connection

def test_init_db_creates_tables(test_db):
    conn = get_connection(test_db)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "teams" in tables
    assert "sprints" in tables
    assert "sprint_snapshots" in tables
    assert "daily_progress" in tables
    assert "scope_changes" in tables

def test_teams_table_columns(test_db):
    conn = get_connection(test_db)
    cursor = conn.execute("PRAGMA table_info(teams)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert columns == {"id", "name", "clickup_space_id", "clickup_folder_id", "metric_type", "sprint_length_days", "created_at"}

def test_sprints_table_has_no_status_column(test_db):
    conn = get_connection(test_db)
    cursor = conn.execute("PRAGMA table_info(sprints)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert "status" not in columns
    assert "forecast_closed_at" in columns
    assert "closed_at" in columns
