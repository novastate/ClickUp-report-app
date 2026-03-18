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
            clickup_space_id TEXT NOT NULL,
            clickup_folder_id TEXT NOT NULL,
            metric_type TEXT NOT NULL DEFAULT 'task_count',
            sprint_length_days INTEGER NOT NULL DEFAULT 14,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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

        CREATE TABLE IF NOT EXISTS scope_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            task_name TEXT NOT NULL,
            change_type TEXT NOT NULL CHECK(change_type IN ('added', 'removed')),
            detected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            assignee_name TEXT
        );
    """)
    conn.commit()
    conn.close()
