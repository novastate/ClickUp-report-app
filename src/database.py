import sqlite3
from datetime import datetime

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(db_path: str):
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            clickup_workspace_id TEXT NOT NULL DEFAULT '',
            clickup_space_id TEXT NOT NULL,
            clickup_folder_id TEXT NOT NULL,
            metric_type TEXT NOT NULL DEFAULT 'task_count',
            sprint_length_days INTEGER NOT NULL DEFAULT 14,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            clickup_user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            UNIQUE(team_id, clickup_user_id)
        );

        CREATE TABLE IF NOT EXISTS sprint_capacity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
            username TEXT NOT NULL,
            capacity REAL NOT NULL DEFAULT 0,
            UNIQUE(sprint_id, username)
        );

        CREATE TABLE IF NOT EXISTS sprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            clickup_list_id TEXT NOT NULL UNIQUE,
            start_date DATE,
            end_date DATE,
            forecast_closed_at DATETIME,
            closed_at DATETIME,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sprint_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            task_name TEXT NOT NULL,
            task_status TEXT NOT NULL,
            assignee_name TEXT,
            points REAL,
            hours REAL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
            captured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            total_tasks INTEGER NOT NULL,
            completed_tasks INTEGER NOT NULL,
            total_points REAL,
            completed_points REAL,
            total_hours REAL,
            completed_hours REAL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scope_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            task_name TEXT NOT NULL,
            change_type TEXT NOT NULL CHECK(change_type IN ('added', 'removed')),
            detected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            assignee_name TEXT
        );

        CREATE TABLE IF NOT EXISTS sprint_final_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            task_name TEXT NOT NULL,
            task_status TEXT NOT NULL,
            assignee_name TEXT,
            assignee_hours TEXT,
            points REAL,
            hours REAL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_final_snap_sprint ON sprint_final_snapshots(sprint_id);

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            username TEXT,
            color TEXT,
            profile_picture TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_tokens (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            encrypted_access_token TEXT NOT NULL,
            scopes TEXT,
            granted_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            active_workspace_id TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

        CREATE TABLE IF NOT EXISTS oauth_state (
            state TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );
    """)
    # Migrations for existing databases
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN capacity_mode TEXT NOT NULL DEFAULT 'individual'")
    except Exception:
        pass  # Column already exists

    try:
        conn.execute("ALTER TABLE sprint_snapshots ADD COLUMN assignee_hours TEXT")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE sprint_snapshots ADD COLUMN carried_over BOOLEAN DEFAULT 0")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE scope_changes ADD COLUMN sprint_day INTEGER")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE teams ADD COLUMN workspace_id TEXT")
    except Exception:
        pass  # Column already exists

    try:
        conn.execute("ALTER TABLE teams ADD COLUMN space_name TEXT")
    except Exception:
        pass  # Column already exists

    # Backfill workspace_id from the existing clickup_workspace_id column
    conn.execute("""
        UPDATE teams
        SET workspace_id = clickup_workspace_id
        WHERE (workspace_id IS NULL OR workspace_id = '')
          AND clickup_workspace_id IS NOT NULL
          AND clickup_workspace_id != ''
    """)

    conn.execute("""
        UPDATE scope_changes SET sprint_day = CAST(
            julianday(detected_at) - julianday((SELECT start_date FROM sprints WHERE id = scope_changes.sprint_id)) + 1
        AS INTEGER)
        WHERE sprint_day IS NULL AND EXISTS (SELECT 1 FROM sprints WHERE id = scope_changes.sprint_id AND start_date IS NOT NULL)
    """)

    conn.commit()
    conn.close()

def get_setting(db_path: str, key: str) -> str | None:
    conn = get_connection(db_path)
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None

def set_setting(db_path: str, key: str, value: str):
    conn = get_connection(db_path)
    conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
