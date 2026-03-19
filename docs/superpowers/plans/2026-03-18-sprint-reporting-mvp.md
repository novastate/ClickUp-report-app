# Sprint Reporting MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app that tracks ClickUp sprint performance with forecast snapshots, scope change detection, burndown charts, and multi-sprint trend analysis.

**Architecture:** Single Python FastAPI app serving both REST API and HTML dashboard. SQLite stores only snapshots and metrics. ClickUp API called live for current data. Chart.js for visualizations.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Jinja2, Chart.js, httpx, APScheduler, python-dotenv

**Spec:** `docs/superpowers/specs/2026-03-18-sprint-reporting-mvp-design.md`

---

## File Structure

```
ClickUp+PowerBI/
├── app.py                      # Entry point — starts FastAPI + scheduler
├── .env                        # ClickUp API key, host, port, db path (gitignored)
├── .env.example                # Template for .env
├── .gitignore
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── config.py               # Load .env, expose settings
│   ├── database.py             # SQLite setup, table creation, connection helper
│   ├── models.py               # Pydantic models for API request/response
│   ├── clickup_client.py       # ClickUp API wrapper (spaces, folders, lists, tasks)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── team_service.py     # CRUD for teams
│   │   ├── sprint_service.py   # Sprint lifecycle (sync, close forecast, close sprint)
│   │   ├── snapshot_service.py # Forecast snapshots, daily progress, scope change detection
│   │   └── trend_service.py    # Multi-sprint aggregations and trend calculations
│   └── routes/
│       ├── __init__.py
│       ├── teams.py            # Team CRUD + sync endpoints
│       ├── sprints.py          # Sprint lifecycle + refresh endpoints
│       ├── clickup_proxy.py    # Proxy endpoints for spaces/folders
│       └── pages.py            # HTML page routes (dashboard, reports, settings)
├── templates/
│   ├── base.html               # Base template with nav, Chart.js, CSS
│   ├── home.html               # Home redirect / active sprint
│   ├── sprint_live.html        # Live sprint view
│   ├── sprint_report.html      # Closed sprint report
│   ├── team_trends.html        # Team performance over time
│   ├── team_settings.html      # Team config form
│   ├── sprint_history.html     # Sprint list
│   └── components/
│       ├── kpi_cards.html      # Reusable KPI card row
│       ├── task_table.html     # Reusable task table with filtering
│       ├── burndown_chart.html # Chart.js burndown
│       └── scope_timeline.html # Scope change timeline
├── static/
│   ├── style.css               # Dashboard CSS
│   └── dashboard.js            # KPI card click filtering, refresh button
└── tests/
    ├── __init__.py
    ├── test_database.py
    ├── test_clickup_client.py
    ├── test_snapshot_service.py
    ├── test_sprint_service.py
    ├── test_trend_service.py
    └── conftest.py             # Shared fixtures (test db, mock ClickUp responses)
```

---

### Task 1: Project Setup & Configuration

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `app.py` (minimal — just startup confirmation)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn==0.30.0
httpx==0.27.0
python-dotenv==1.0.1
jinja2==3.1.4
apscheduler==3.10.4
pytest==8.3.0
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Create .env.example and .gitignore**

`.env.example`:
```
CLICKUP_API_KEY=pk_your_key_here
HOST=localhost
PORT=8000
DB_PATH=./sprint_data.db
DAILY_SNAPSHOT_TIME=06:00
```

`.gitignore`:
```
.env
*.db
__pycache__/
.pytest_cache/
.superpowers/
```

- [ ] **Step 3: Create src/config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY", "")
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = os.getenv("DB_PATH", "./sprint_data.db")
DAILY_SNAPSHOT_TIME = os.getenv("DAILY_SNAPSHOT_TIME", "06:00")
```

- [ ] **Step 4: Create minimal app.py**

```python
import uvicorn
from fastapi import FastAPI
from src.config import HOST, PORT

app = FastAPI(title="Sprint Reporter")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
```

- [ ] **Step 5: Create tests/conftest.py with shared fixtures**

```python
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
```

- [ ] **Step 6: Install dependencies and verify app starts**

Run:
```bash
cd /Users/collin/dev/projects/ClickUp+PowerBI
python -m pip install -r requirements.txt
python app.py &
sleep 2
curl http://localhost:8000/health
kill %1
```
Expected: `{"status":"ok"}`

- [ ] **Step 7: Commit**

```bash
git init
git add requirements.txt .env.example .gitignore src/__init__.py src/config.py app.py tests/__init__.py tests/conftest.py
git commit -m "feat: project setup with FastAPI, config, and test fixtures"
```

---

### Task 2: Database Schema & Connection

**Files:**
- Create: `src/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write the failing test**

`tests/test_database.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Implement src/database.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/database.py tests/test_database.py
git commit -m "feat: SQLite schema with teams, sprints, snapshots, progress, scope changes"
```

---

### Task 3: ClickUp API Client

**Files:**
- Create: `src/clickup_client.py`
- Create: `tests/test_clickup_client.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_clickup_client.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch
from src.clickup_client import ClickUpClient

@pytest.mark.asyncio
async def test_get_spaces():
    mock_response = AsyncMock()
    mock_response.json.return_value = {"teams": [{"id": "123", "name": "SGIT"}]}
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        client = ClickUpClient("fake_key")
        result = await client.get_workspaces()
        assert result[0]["name"] == "SGIT"
        mock_get.assert_called_once()

@pytest.mark.asyncio
async def test_get_folder_lists():
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "lists": [
            {"id": "list_1", "name": "Iteration 5 (23/2 - 8/3)", "task_count": 10},
            {"id": "list_2", "name": "Backlog", "task_count": 20},
        ]
    }
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        client = ClickUpClient("fake_key")
        result = await client.get_folder_lists("folder_1")
        assert len(result) == 2
        assert result[0]["name"] == "Iteration 5 (23/2 - 8/3)"

@pytest.mark.asyncio
async def test_get_list_tasks_handles_pagination():
    page_0 = AsyncMock()
    page_0.json.return_value = {"tasks": [{"id": f"t{i}"} for i in range(100)]}
    page_0.raise_for_status = lambda: None

    page_1 = AsyncMock()
    page_1.json.return_value = {"tasks": [{"id": "t100"}]}
    page_1.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", side_effect=[page_0, page_1]):
        client = ClickUpClient("fake_key")
        result = await client.get_list_tasks("list_1")
        assert len(result) == 101

@pytest.mark.asyncio
async def test_extract_task_data():
    client = ClickUpClient("fake_key")
    raw_task = {
        "id": "abc123",
        "name": "Fix bug",
        "status": {"status": "in progress"},
        "assignees": [{"username": "Anna"}, {"username": "Erik"}],
        "points": 3.0,
        "time_estimate": 7200000,
    }
    extracted = client.extract_task_data(raw_task)
    assert extracted["task_id"] == "abc123"
    assert extracted["task_name"] == "Fix bug"
    assert extracted["task_status"] == "in progress"
    assert extracted["assignee_name"] == "Anna"
    assert extracted["points"] == 3.0
    assert extracted["hours"] == 2.0  # 7200000ms = 2h
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_clickup_client.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement src/clickup_client.py**

```python
import httpx
from typing import Optional

BASE_URL = "https://api.clickup.com/api/v2"

class ClickUpClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": api_key}

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{path}",
                headers=self.headers,
                params=params or {},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_workspaces(self) -> list[dict]:
        data = await self._get("/team")
        return data.get("teams", [])

    async def get_spaces(self, team_id: str) -> list[dict]:
        data = await self._get(f"/team/{team_id}/space", {"archived": "false"})
        return data.get("spaces", [])

    async def get_folders(self, space_id: str) -> list[dict]:
        data = await self._get(f"/space/{space_id}/folder")
        return data.get("folders", [])

    async def get_folder_lists(self, folder_id: str) -> list[dict]:
        data = await self._get(f"/folder/{folder_id}/list")
        return data.get("lists", [])

    async def get_list_tasks(self, list_id: str) -> list[dict]:
        all_tasks = []
        page = 0
        while True:
            data = await self._get(
                f"/list/{list_id}/task",
                {"include_closed": "true", "subtasks": "true", "page": str(page)},
            )
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)
            if len(tasks) < 100:
                break
            page += 1
        return all_tasks

    def extract_task_data(self, raw_task: dict) -> dict:
        assignees = raw_task.get("assignees", [])
        time_estimate = raw_task.get("time_estimate")
        return {
            "task_id": raw_task["id"],
            "task_name": raw_task["name"],
            "task_status": raw_task["status"]["status"],
            "assignee_name": assignees[0]["username"] if assignees else None,
            "points": raw_task.get("points"),
            "hours": round(time_estimate / 3_600_000, 2) if time_estimate else None,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_clickup_client.py -v`
Expected: All 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/clickup_client.py tests/test_clickup_client.py
git commit -m "feat: ClickUp API client with pagination and task extraction"
```

---

### Task 4: Team Service (CRUD)

**Files:**
- Create: `src/services/__init__.py`
- Create: `src/services/team_service.py`
- Create: `src/models.py`

- [ ] **Step 1: Create src/models.py with Pydantic models**

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date

class TeamCreate(BaseModel):
    name: str
    clickup_space_id: str
    clickup_folder_id: str
    metric_type: str = "task_count"
    sprint_length_days: int = 14

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    clickup_space_id: Optional[str] = None
    clickup_folder_id: Optional[str] = None
    metric_type: Optional[str] = None
    sprint_length_days: Optional[int] = None

class TeamOut(BaseModel):
    id: int
    name: str
    clickup_space_id: str
    clickup_folder_id: str
    metric_type: str
    sprint_length_days: int
    created_at: str
```

- [ ] **Step 2: Implement src/services/team_service.py**

```python
from src.database import get_connection
from src.config import DB_PATH

def create_team(name: str, space_id: str, folder_id: str, metric_type: str = "task_count", sprint_length_days: int = 14) -> dict:
    conn = get_connection(DB_PATH)
    cursor = conn.execute(
        "INSERT INTO teams (name, clickup_space_id, clickup_folder_id, metric_type, sprint_length_days) VALUES (?, ?, ?, ?, ?)",
        (name, space_id, folder_id, metric_type, sprint_length_days),
    )
    conn.commit()
    team_id = cursor.lastrowid
    team = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    conn.close()
    return dict(team)

def get_team(team_id: int) -> dict | None:
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_teams() -> list[dict]:
    conn = get_connection(DB_PATH)
    rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_team(team_id: int, **kwargs) -> dict | None:
    if not kwargs:
        return get_team(team_id)
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [team_id]
    conn = get_connection(DB_PATH)
    conn.execute(f"UPDATE teams SET {sets} WHERE id = ?", values)
    conn.commit()
    team = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    conn.close()
    return dict(team) if team else None

def delete_team(team_id: int) -> bool:
    conn = get_connection(DB_PATH)
    cursor = conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
```

- [ ] **Step 3: Quick smoke test**

Run: `pytest tests/test_database.py -v`
Expected: Still passing (no regressions)

- [ ] **Step 4: Commit**

```bash
git add src/models.py src/services/__init__.py src/services/team_service.py
git commit -m "feat: team CRUD service and Pydantic models"
```

---

### Task 5: Sprint Service (Sync, Lifecycle)

**Files:**
- Create: `src/services/sprint_service.py`
- Create: `tests/test_sprint_service.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_sprint_service.py`:
```python
import pytest
from datetime import datetime
from src.database import init_db, get_connection
from src.services.team_service import create_team
from src.services.sprint_service import (
    create_sprint_from_list,
    get_sprint,
    get_team_sprints,
    close_forecast,
    close_sprint,
    get_sprint_status,
    parse_iteration_dates,
)

def test_parse_iteration_dates():
    name = "Iteration 6 (9/3 - 22/3)"
    start, end = parse_iteration_dates(name, 2026)
    assert start.month == 3
    assert start.day == 9
    assert end.month == 3
    assert end.day == 22

def test_parse_iteration_dates_cross_year():
    name = "Iteration 1 (23/12 - 5/1)"
    start, end = parse_iteration_dates(name, 2025)
    assert start.month == 12
    assert end.month == 1
    assert end.year == 2026

def test_create_sprint(test_db):
    team = create_team("Test Team", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    assert sprint["name"] == "Iteration 6 (9/3 - 22/3)"
    assert sprint["clickup_list_id"] == "list_1"

def test_sprint_status_planning(test_db):
    team = create_team("Test Team", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    assert get_sprint_status(sprint) == "planning"

def test_close_forecast_changes_status(test_db):
    team = create_team("Test Team", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    updated = close_forecast(sprint["id"])
    assert updated["forecast_closed_at"] is not None
    assert get_sprint_status(updated) == "active"

def test_close_sprint_changes_status(test_db):
    team = create_team("Test Team", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    close_forecast(sprint["id"])
    updated = close_sprint(sprint["id"])
    assert updated["closed_at"] is not None
    assert get_sprint_status(updated) == "closed"

def test_cannot_close_sprint_before_forecast(test_db):
    team = create_team("Test Team", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    with pytest.raises(ValueError, match="forecast"):
        close_sprint(sprint["id"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sprint_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement src/services/sprint_service.py**

```python
import re
from datetime import datetime, date
from src.database import get_connection
from src.config import DB_PATH

def parse_iteration_dates(name: str, reference_year: int = None) -> tuple[date, date]:
    if reference_year is None:
        reference_year = datetime.now().year
    match = re.search(r"\((\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,2})\)", name)
    if not match:
        return None, None
    start_day, start_month, end_day, end_month = (int(g) for g in match.groups())
    start = date(reference_year, start_month, start_day)
    end_year = reference_year + 1 if end_month < start_month else reference_year
    end = date(end_year, end_month, end_day)
    return start, end

def create_sprint_from_list(team_id: int, list_id: str, list_name: str) -> dict:
    start, end = parse_iteration_dates(list_name)
    conn = get_connection(DB_PATH)
    cursor = conn.execute(
        "INSERT OR IGNORE INTO sprints (team_id, name, clickup_list_id, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
        (team_id, list_name, list_id, start, end),
    )
    conn.commit()
    if cursor.lastrowid:
        sprint = conn.execute("SELECT * FROM sprints WHERE id = ?", (cursor.lastrowid,)).fetchone()
    else:
        sprint = conn.execute("SELECT * FROM sprints WHERE clickup_list_id = ?", (list_id,)).fetchone()
    conn.close()
    return dict(sprint)

def get_sprint(sprint_id: int) -> dict | None:
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_team_sprints(team_id: int) -> list[dict]:
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT * FROM sprints WHERE team_id = ? ORDER BY start_date DESC", (team_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sprint_status(sprint: dict) -> str:
    if sprint.get("closed_at"):
        return "closed"
    if sprint.get("forecast_closed_at"):
        return "active"
    return "planning"

def close_forecast(sprint_id: int) -> dict:
    conn = get_connection(DB_PATH)
    now = datetime.now().isoformat()
    conn.execute("UPDATE sprints SET forecast_closed_at = ? WHERE id = ?", (now, sprint_id))
    conn.commit()
    sprint = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
    conn.close()
    return dict(sprint)

def close_sprint(sprint_id: int) -> dict:
    sprint = get_sprint(sprint_id)
    if not sprint or not sprint.get("forecast_closed_at"):
        raise ValueError("Cannot close sprint before forecast is closed")
    conn = get_connection(DB_PATH)
    now = datetime.now().isoformat()
    conn.execute("UPDATE sprints SET closed_at = ? WHERE id = ?", (now, sprint_id))
    conn.commit()
    sprint = conn.execute("SELECT * FROM sprints WHERE id = ?", (sprint_id,)).fetchone()
    conn.close()
    return dict(sprint)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sprint_service.py -v`
Expected: All 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/sprint_service.py tests/test_sprint_service.py
git commit -m "feat: sprint service with lifecycle management and date parsing"
```

---

### Task 6: Snapshot Service (Forecast, Progress, Scope Changes)

**Files:**
- Create: `src/services/snapshot_service.py`
- Create: `tests/test_snapshot_service.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_snapshot_service.py`:
```python
import pytest
from src.database import init_db, get_connection
from src.services.team_service import create_team
from src.services.sprint_service import create_sprint_from_list, close_forecast
from src.services.snapshot_service import (
    save_forecast_snapshot,
    get_forecast_snapshot,
    record_daily_progress,
    detect_scope_changes,
    get_scope_changes,
    get_daily_progress_history,
)

def _make_tasks(ids_and_statuses):
    return [
        {"task_id": tid, "task_name": f"Task {tid}", "task_status": status,
         "assignee_name": "Anna", "points": 2, "hours": 1}
        for tid, status in ids_and_statuses
    ]

def test_save_and_get_forecast_snapshot(test_db):
    team = create_team("T", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    save_forecast_snapshot(sprint["id"], tasks)
    snapshot = get_forecast_snapshot(sprint["id"])
    assert len(snapshot) == 3
    assert {t["task_id"] for t in snapshot} == {"t1", "t2", "t3"}

def test_record_daily_progress(test_db):
    team = create_team("T", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    record_daily_progress(sprint["id"], total_tasks=10, completed_tasks=3,
                          total_points=20, completed_points=6,
                          total_hours=40, completed_hours=12)
    history = get_daily_progress_history(sprint["id"])
    assert len(history) == 1
    assert history[0]["completed_tasks"] == 3

def test_detect_scope_changes_added(test_db):
    team = create_team("T", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do"), ("t2", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    current_tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    changes = detect_scope_changes(sprint["id"], current_tasks)
    assert len(changes) == 1
    assert changes[0]["change_type"] == "added"
    assert changes[0]["task_id"] == "t3"

def test_detect_scope_changes_removed(test_db):
    team = create_team("T", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    current_tasks = _make_tasks([("t1", "to do"), ("t2", "to do")])
    changes = detect_scope_changes(sprint["id"], current_tasks)
    assert len(changes) == 1
    assert changes[0]["change_type"] == "removed"
    assert changes[0]["task_id"] == "t3"

def test_closed_sprint_task_list_reconstruction(test_db):
    """Verify that after closing a sprint, the full task list can be reconstructed
    from forecast snapshot + scope changes with correct annotations."""
    team = create_team("T", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    # Simulate scope changes: t4 added, t3 removed
    current_tasks = _make_tasks([("t1", "complete"), ("t2", "in progress"), ("t4", "to do")])
    detect_scope_changes(sprint["id"], current_tasks)
    # Get snapshot + changes
    snapshot = get_forecast_snapshot(sprint["id"])
    changes = get_scope_changes(sprint["id"])
    added_ids = {c["task_id"] for c in changes if c["change_type"] == "added"}
    removed_ids = {c["task_id"] for c in changes if c["change_type"] == "removed"}
    assert "t4" in added_ids
    assert "t3" in removed_ids
    assert len(snapshot) == 3  # Original forecast
    # Full task list = snapshot + added - removed
    all_ids = {t["task_id"] for t in snapshot} | added_ids
    assert all_ids == {"t1", "t2", "t3", "t4"}

def test_detect_scope_changes_no_duplicates(test_db):
    team = create_team("T", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    current_tasks = _make_tasks([("t1", "to do"), ("t2", "to do")])
    detect_scope_changes(sprint["id"], current_tasks)
    # Second detection of same change should not duplicate
    changes = detect_scope_changes(sprint["id"], current_tasks)
    assert len(changes) == 0
    all_changes = get_scope_changes(sprint["id"])
    assert len(all_changes) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_snapshot_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement src/services/snapshot_service.py**

```python
from datetime import datetime
from src.database import get_connection
from src.config import DB_PATH

def save_forecast_snapshot(sprint_id: int, tasks: list[dict]):
    conn = get_connection(DB_PATH)
    for t in tasks:
        conn.execute(
            "INSERT INTO sprint_snapshots (sprint_id, task_id, task_name, task_status, assignee_name, points, hours) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sprint_id, t["task_id"], t["task_name"], t["task_status"], t.get("assignee_name"), t.get("points"), t.get("hours")),
        )
    conn.commit()
    conn.close()

def get_forecast_snapshot(sprint_id: int) -> list[dict]:
    conn = get_connection(DB_PATH)
    rows = conn.execute("SELECT * FROM sprint_snapshots WHERE sprint_id = ?", (sprint_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def record_daily_progress(sprint_id: int, total_tasks: int, completed_tasks: int,
                          total_points: float = None, completed_points: float = None,
                          total_hours: float = None, completed_hours: float = None):
    conn = get_connection(DB_PATH)
    conn.execute(
        "INSERT INTO daily_progress (sprint_id, total_tasks, completed_tasks, total_points, completed_points, total_hours, completed_hours) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sprint_id, total_tasks, completed_tasks, total_points, completed_points, total_hours, completed_hours),
    )
    conn.commit()
    conn.close()

def get_daily_progress_history(sprint_id: int) -> list[dict]:
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT * FROM daily_progress WHERE sprint_id = ? ORDER BY captured_at", (sprint_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_scope_changes(sprint_id: int) -> list[dict]:
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT * FROM scope_changes WHERE sprint_id = ? ORDER BY detected_at", (sprint_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def detect_scope_changes(sprint_id: int, current_tasks: list[dict]) -> list[dict]:
    snapshot = get_forecast_snapshot(sprint_id)
    existing_changes = get_scope_changes(sprint_id)

    snapshot_ids = {t["task_id"] for t in snapshot}
    current_ids = {t["task_id"] for t in current_tasks}
    current_by_id = {t["task_id"]: t for t in current_tasks}

    # Already recorded changes — track net state per task
    already_added = set()
    already_removed = set()
    for ch in existing_changes:
        if ch["change_type"] == "added":
            already_added.add(ch["task_id"])
            already_removed.discard(ch["task_id"])
        else:
            already_removed.add(ch["task_id"])
            already_added.discard(ch["task_id"])

    new_changes = []
    conn = get_connection(DB_PATH)

    # Detect additions: in current but not in snapshot, and not already recorded as added
    for tid in current_ids - snapshot_ids:
        if tid not in already_added:
            task = current_by_id[tid]
            conn.execute(
                "INSERT INTO scope_changes (sprint_id, task_id, task_name, change_type, assignee_name) VALUES (?, ?, ?, 'added', ?)",
                (sprint_id, tid, task["task_name"], task.get("assignee_name")),
            )
            new_changes.append({"task_id": tid, "task_name": task["task_name"], "change_type": "added"})

    # Detect removals: in snapshot but not in current, and not already recorded as removed
    for tid in snapshot_ids - current_ids:
        if tid not in already_removed:
            snapshot_task = next(t for t in snapshot if t["task_id"] == tid)
            conn.execute(
                "INSERT INTO scope_changes (sprint_id, task_id, task_name, change_type, assignee_name) VALUES (?, ?, ?, 'removed', ?)",
                (sprint_id, tid, snapshot_task["task_name"], snapshot_task.get("assignee_name")),
            )
            new_changes.append({"task_id": tid, "task_name": snapshot_task["task_name"], "change_type": "removed"})

    conn.commit()
    conn.close()
    return new_changes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_snapshot_service.py -v`
Expected: All 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/snapshot_service.py tests/test_snapshot_service.py
git commit -m "feat: snapshot service with forecast baseline, daily progress, and scope change detection"
```

---

### Task 7: Trend Service (Multi-Sprint Aggregations)

**Files:**
- Create: `src/services/trend_service.py`
- Create: `tests/test_trend_service.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_trend_service.py`:
```python
import pytest
from src.services.team_service import create_team
from src.services.sprint_service import create_sprint_from_list, close_forecast, close_sprint
from src.services.snapshot_service import save_forecast_snapshot, record_daily_progress
from src.services.trend_service import get_team_trends, calculate_on_track_status

def _setup_closed_sprint(team_id, list_id, name, forecast_count, completed_count, points_total, points_done):
    sprint = create_sprint_from_list(team_id, list_id, name)
    tasks = [
        {"task_id": f"{list_id}_t{i}", "task_name": f"Task {i}", "task_status": "to do",
         "assignee_name": "Anna", "points": points_total / forecast_count, "hours": None}
        for i in range(forecast_count)
    ]
    save_forecast_snapshot(sprint["id"], tasks)
    close_forecast(sprint["id"])
    record_daily_progress(sprint["id"], total_tasks=forecast_count, completed_tasks=completed_count,
                          total_points=points_total, completed_points=points_done)
    close_sprint(sprint["id"])
    return sprint

def test_get_team_trends(test_db):
    team = create_team("T", "s", "f")
    _setup_closed_sprint(team["id"], "l1", "Iteration 1 (1/1 - 14/1)", 10, 8, 20, 16)
    _setup_closed_sprint(team["id"], "l2", "Iteration 2 (15/1 - 28/1)", 12, 10, 24, 20)
    trends = get_team_trends(team["id"])
    assert len(trends["sprints"]) == 2
    assert trends["avg_completion_rate"] == pytest.approx(0.833, abs=0.01)

def test_on_track_status():
    assert calculate_on_track_status(remaining=8, ideal_remaining=10) == "ahead"
    assert calculate_on_track_status(remaining=10, ideal_remaining=10) == "on_track"
    assert calculate_on_track_status(remaining=12, ideal_remaining=10) == "behind"
    assert calculate_on_track_status(remaining=9.5, ideal_remaining=10) == "on_track"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_trend_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement src/services/trend_service.py**

```python
from src.database import get_connection
from src.config import DB_PATH
from src.services.sprint_service import get_team_sprints, get_sprint_status
from src.services.snapshot_service import get_forecast_snapshot, get_daily_progress_history, get_scope_changes

def calculate_on_track_status(remaining: float, ideal_remaining: float) -> str:
    if ideal_remaining == 0:
        return "on_track" if remaining == 0 else "behind"
    diff_pct = (remaining - ideal_remaining) / ideal_remaining
    if diff_pct < -0.10:
        return "ahead"
    elif diff_pct > 0.10:
        return "behind"
    return "on_track"

def get_sprint_summary(sprint_id: int) -> dict:
    snapshot = get_forecast_snapshot(sprint_id)
    progress = get_daily_progress_history(sprint_id)
    scope = get_scope_changes(sprint_id)

    forecasted_count = len(snapshot)
    latest = progress[-1] if progress else None

    completed = latest["completed_tasks"] if latest else 0
    total = latest["total_tasks"] if latest else forecasted_count
    completion_rate = completed / forecasted_count if forecasted_count > 0 else 0

    added = sum(1 for s in scope if s["change_type"] == "added")
    removed = sum(1 for s in scope if s["change_type"] == "removed")

    return {
        "forecasted": forecasted_count,
        "completed": completed,
        "total_current": total,
        "completion_rate": completion_rate,
        "scope_added": added,
        "scope_removed": removed,
        "velocity": completed,
        "forecast_accuracy": completed / forecasted_count if forecasted_count > 0 else 0,
        "completed_points": latest["completed_points"] if latest else 0,
        "completed_hours": latest["completed_hours"] if latest else 0,
    }

def get_team_trends(team_id: int, limit: int = None) -> dict:
    sprints = get_team_sprints(team_id)
    closed = [s for s in sprints if get_sprint_status(s) == "closed"]
    if limit:
        closed = closed[:limit]

    sprint_summaries = []
    for s in closed:
        summary = get_sprint_summary(s["id"])
        summary["sprint_id"] = s["id"]
        summary["sprint_name"] = s["name"]
        summary["start_date"] = s["start_date"]
        summary["end_date"] = s["end_date"]
        sprint_summaries.append(summary)

    if not sprint_summaries:
        return {"sprints": [], "avg_velocity": 0, "avg_completion_rate": 0, "avg_scope_added": 0}

    avg_velocity = sum(s["velocity"] for s in sprint_summaries) / len(sprint_summaries)
    avg_completion = sum(s["completion_rate"] for s in sprint_summaries) / len(sprint_summaries)
    avg_scope = sum(s["scope_added"] for s in sprint_summaries) / len(sprint_summaries)

    avg_forecast_accuracy = sum(
        s["completed"] / s["forecasted"] if s["forecasted"] > 0 else 0
        for s in sprint_summaries
    ) / len(sprint_summaries)

    return {
        "sprints": sprint_summaries,
        "avg_velocity": avg_velocity,
        "avg_completion_rate": avg_completion,
        "avg_scope_added": avg_scope,
        "avg_forecast_accuracy": avg_forecast_accuracy,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_trend_service.py -v`
Expected: All 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/trend_service.py tests/test_trend_service.py
git commit -m "feat: trend service with multi-sprint aggregation and on-track calculation"
```

---

### Task 8: API Routes (Teams, Sprints, ClickUp Proxy)

**Files:**
- Create: `src/routes/__init__.py`
- Create: `src/routes/teams.py`
- Create: `src/routes/sprints.py`
- Create: `src/routes/clickup_proxy.py`
- Modify: `app.py` — register routers, init DB on startup

- [ ] **Step 1: Create src/routes/teams.py**

```python
from fastapi import APIRouter, HTTPException
from src.models import TeamCreate, TeamUpdate
from src.services import team_service
from src.services.sprint_service import create_sprint_from_list
from src.clickup_client import ClickUpClient
from src.config import CLICKUP_API_KEY

router = APIRouter(prefix="/teams", tags=["teams"])

@router.get("")
def list_teams():
    return team_service.get_all_teams()

@router.post("")
def create_team(body: TeamCreate):
    return team_service.create_team(body.name, body.clickup_space_id, body.clickup_folder_id, body.metric_type, body.sprint_length_days)

@router.get("/{team_id}")
def get_team(team_id: int):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team

@router.put("/{team_id}")
def update_team(team_id: int, body: TeamUpdate):
    updates = body.model_dump(exclude_none=True)
    team = team_service.update_team(team_id, **updates)
    if not team:
        raise HTTPException(404, "Team not found")
    return team

@router.delete("/{team_id}")
def delete_team(team_id: int):
    if not team_service.delete_team(team_id):
        raise HTTPException(404, "Team not found")
    return {"ok": True}

@router.get("/{team_id}/sprints")
def team_sprints(team_id: int):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    from src.services.sprint_service import get_team_sprints, get_sprint_status
    sprints = get_team_sprints(team_id)
    for s in sprints:
        s["status"] = get_sprint_status(s)
    return sprints

@router.get("/{team_id}/trends")
def team_trends(team_id: int, limit: int = 8):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    from src.services.trend_service import get_team_trends
    return get_team_trends(team_id, limit=limit)

@router.post("/{team_id}/sync-sprints")
async def sync_sprints(team_id: int):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    client = ClickUpClient(CLICKUP_API_KEY)
    lists = await client.get_folder_lists(team["clickup_folder_id"])
    synced = []
    for lst in lists:
        sprint = create_sprint_from_list(team["id"], lst["id"], lst["name"])
        synced.append(sprint)
    return {"synced": len(synced), "sprints": synced}
```

- [ ] **Step 2: Create src/routes/sprints.py**

```python
from fastapi import APIRouter, HTTPException
from src.services.sprint_service import get_sprint, get_team_sprints, close_forecast as do_close_forecast, close_sprint as do_close_sprint, get_sprint_status
from src.services.snapshot_service import save_forecast_snapshot, record_daily_progress, detect_scope_changes, get_scope_changes, get_forecast_snapshot, get_daily_progress_history
from src.services.trend_service import get_sprint_summary, get_team_trends
from src.clickup_client import ClickUpClient
from src.config import CLICKUP_API_KEY

router = APIRouter(prefix="/sprints", tags=["sprints"])

@router.get("/{sprint_id}")
def sprint_detail(sprint_id: int):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    sprint["status"] = get_sprint_status(sprint)
    sprint["summary"] = get_sprint_summary(sprint_id)
    sprint["scope_changes"] = get_scope_changes(sprint_id)
    sprint["progress_history"] = get_daily_progress_history(sprint_id)
    sprint["forecast_snapshot"] = get_forecast_snapshot(sprint_id)
    return sprint

@router.post("/{sprint_id}/close-forecast")
async def close_forecast_route(sprint_id: int):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    if sprint.get("forecast_closed_at"):
        raise HTTPException(400, "Forecast already closed")
    client = ClickUpClient(CLICKUP_API_KEY)
    raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"])
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    save_forecast_snapshot(sprint_id, tasks)
    updated = do_close_forecast(sprint_id)
    # Record initial daily progress
    completed = sum(1 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_points = sum(t["points"] or 0 for t in tasks)
    completed_points = sum(t["points"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_hours = sum(t["hours"] or 0 for t in tasks)
    completed_hours = sum(t["hours"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    record_daily_progress(sprint_id, len(tasks), completed, total_points, completed_points, total_hours, completed_hours)
    return {"sprint": updated, "tasks_captured": len(tasks)}

@router.post("/{sprint_id}/close")
async def close_sprint_route(sprint_id: int):
    # Do a final refresh before closing
    await refresh_route(sprint_id)
    # Save final state of scope-added tasks into sprint_snapshots
    # so the closed report has complete data for all tasks
    sprint = get_sprint(sprint_id)
    client = ClickUpClient(CLICKUP_API_KEY)
    raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"])
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint_id)}
    added_tasks = [t for t in tasks if t["task_id"] not in snapshot_ids]
    if added_tasks:
        from src.services.snapshot_service import save_forecast_snapshot
        save_forecast_snapshot(sprint_id, added_tasks)  # Appends to existing snapshot
    try:
        updated = do_close_sprint(sprint_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return updated

@router.post("/{sprint_id}/refresh")
async def refresh_route(sprint_id: int):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    if not sprint.get("forecast_closed_at"):
        raise HTTPException(400, "Forecast not yet closed — nothing to refresh against")
    if sprint.get("closed_at"):
        raise HTTPException(400, "Sprint is closed — cannot refresh")
    client = ClickUpClient(CLICKUP_API_KEY)
    raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"])
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    # Detect scope changes
    new_changes = detect_scope_changes(sprint_id, tasks)
    # Record progress
    completed = sum(1 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_points = sum(t["points"] or 0 for t in tasks)
    completed_points = sum(t["points"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_hours = sum(t["hours"] or 0 for t in tasks)
    completed_hours = sum(t["hours"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    record_daily_progress(sprint_id, len(tasks), completed, total_points, completed_points, total_hours, completed_hours)
    return {"tasks": len(tasks), "completed": completed, "new_scope_changes": len(new_changes)}

@router.get("/{sprint_id}/tasks")
async def sprint_tasks(sprint_id: int, filter: str = None):
    sprint = get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    # If sprint is closed, return from snapshot + scope changes
    # If active, fetch live from ClickUp
    if sprint.get("closed_at"):
        snapshot = get_forecast_snapshot(sprint_id)
        changes = get_scope_changes(sprint_id)
        added_ids = {c["task_id"] for c in changes if c["change_type"] == "added"}
        removed_ids = {c["task_id"] for c in changes if c["change_type"] == "removed"}
        tasks = []
        for t in snapshot:
            t["scope_change"] = "removed" if t["task_id"] in removed_ids else None
            tasks.append(t)
        for c in changes:
            if c["change_type"] == "added":
                tasks.append({**c, "scope_change": "added", "points": None, "hours": None})
    else:
        client = ClickUpClient(CLICKUP_API_KEY)
        raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"])
        snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint_id)} if sprint.get("forecast_closed_at") else set()
        tasks = []
        for t in raw_tasks:
            extracted = client.extract_task_data(t)
            extracted["scope_change"] = "added" if extracted["task_id"] not in snapshot_ids and snapshot_ids else None
            tasks.append(extracted)
    if filter == "completed":
        tasks = [t for t in tasks if t.get("task_status") in ("complete", "closed")]
    elif filter == "not_completed":
        tasks = [t for t in tasks if t.get("task_status") not in ("complete", "closed")]
    elif filter == "scope_changes":
        tasks = [t for t in tasks if t.get("scope_change")]
    return tasks
```

- [ ] **Step 3: Create src/routes/clickup_proxy.py**

```python
from fastapi import APIRouter
from src.clickup_client import ClickUpClient
from src.config import CLICKUP_API_KEY

router = APIRouter(prefix="/api/clickup", tags=["clickup"])

@router.get("/spaces")
async def list_spaces():
    client = ClickUpClient(CLICKUP_API_KEY)
    workspaces = await client.get_workspaces()
    result = []
    for ws in workspaces:
        spaces = await client.get_spaces(ws["id"])
        for space in spaces:
            result.append({"workspace": ws["name"], "space_id": space["id"], "space_name": space["name"]})
    return result

@router.get("/folders/{space_id}")
async def list_folders(space_id: str):
    client = ClickUpClient(CLICKUP_API_KEY)
    folders = await client.get_folders(space_id)
    return [{"id": f["id"], "name": f["name"]} for f in folders]
```

- [ ] **Step 4: Update app.py to register all routers and init DB**

```python
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import HOST, PORT, DB_PATH
from src.database import init_db
from src.routes import teams, sprints, clickup_proxy, pages

app = FastAPI(title="Sprint Reporter")

app.include_router(teams.router)
app.include_router(sprints.router)
app.include_router(clickup_proxy.router)
app.include_router(pages.router)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def startup():
    init_db(DB_PATH)

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
```

Note: `pages.router` will be created in Task 9. For now create a placeholder:

`src/routes/pages.py`:
```python
from fastapi import APIRouter

router = APIRouter(tags=["pages"])
```

- [ ] **Step 5: Verify app starts with all routes**

Run:
```bash
python app.py &
sleep 2
curl http://localhost:8000/health
curl http://localhost:8000/teams
kill %1
```
Expected: `{"status":"ok"}` and `[]`

- [ ] **Step 6: Commit**

```bash
git add src/routes/ app.py
git commit -m "feat: API routes for teams, sprints, and ClickUp proxy"
```

---

### Task 9: HTML Templates & Static Assets (Base + Team Settings + Sprint History)

**Files:**
- Create: `templates/base.html`
- Create: `templates/home.html`
- Create: `templates/team_settings.html`
- Create: `templates/sprint_history.html`
- Create: `static/style.css`
- Create: `static/dashboard.js`
- Modify: `src/routes/pages.py`

- [ ] **Step 1: Create static/style.css**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #2d3748; }
a { color: #5f55ee; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Top bar */
.top-bar { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; background: #1a202c; color: white; }
.top-bar h1 { font-size: 18px; font-weight: bold; }
.top-bar .meta { opacity: 0.6; margin-left: 12px; }
.top-bar .actions { display: flex; gap: 12px; }

/* Buttons */
.btn { padding: 8px 16px; border-radius: 6px; font-size: 13px; cursor: pointer; border: none; color: white; }
.btn-secondary { background: #4a5568; }
.btn-danger { background: #e53e3e; }
.btn-primary { background: #5f55ee; }
.btn-success { background: #38a169; }
.btn:hover { opacity: 0.9; }

/* Status badges */
.badge { padding: 2px 10px; border-radius: 12px; font-size: 12px; }
.badge-active { background: #38a169; color: white; }
.badge-closed { background: #718096; color: white; }
.badge-planning { background: #dd6b20; color: white; }
.badge-complete { background: #c6f6d5; color: #22543d; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.badge-progress { background: #e9d8fd; color: #553c9a; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.badge-todo { background: #edf2f7; color: #4a5568; padding: 2px 8px; border-radius: 4px; font-size: 11px; }

/* KPI cards */
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; padding: 20px 24px; }
.kpi-card { background: white; padding: 16px; border-radius: 8px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); cursor: pointer; border: 2px solid transparent; transition: border-color 0.2s; }
.kpi-card:hover { border-color: #e2e8f0; }
.kpi-card.active { border-color: #5f55ee; }
.kpi-card .label { font-size: 12px; color: #718096; text-transform: uppercase; }
.kpi-card .value { font-size: 28px; font-weight: bold; margin: 4px 0; }
.kpi-card .sub { font-size: 12px; color: #a0aec0; }
.kpi-card .value.green { color: #38a169; }
.kpi-card .value.red { color: #e53e3e; }
.kpi-card .value.purple { color: #5f55ee; }
.kpi-card .value.orange { color: #dd6b20; }

/* Content panels */
.content { padding: 0 24px 24px; }
.panel { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px; }
.panel h3 { font-weight: bold; margin-bottom: 16px; }
.grid-2 { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }
.grid-half { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

/* Task table */
.task-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.task-table th { text-align: left; font-size: 11px; text-transform: uppercase; color: #718096; padding: 8px; border-bottom: 1px solid #e2e8f0; }
.task-table td { padding: 10px 8px; border-bottom: 1px solid #f7fafc; }
.task-table tr.scope-added td:first-child { color: #38a169; }
.task-table tr.scope-removed td { text-decoration: line-through; opacity: 0.5; }
.task-table tr[data-filter] { transition: opacity 0.2s; }
.task-table tr.filtered-out { display: none; }
.scope-badge { font-size: 11px; color: #dd6b20; margin-left: 8px; }

/* Scope timeline */
.scope-timeline { padding-left: 20px; border-left: 2px solid #e2e8f0; }
.scope-event { margin-bottom: 16px; position: relative; }
.scope-event::before { content: ''; position: absolute; left: -26px; top: 2px; width: 12px; height: 12px; border-radius: 50%; }
.scope-event.added::before { background: #38a169; }
.scope-event.removed::before { background: #e53e3e; }
.scope-event .date { font-size: 12px; color: #718096; }
.scope-event .detail { font-size: 14px; }

/* Charts */
.chart-container { position: relative; height: 250px; }

/* Verdict banner */
.verdict { margin: 20px 24px; padding: 20px; border-radius: 8px; display: flex; align-items: center; gap: 12px; }
.verdict.good { background: #f0fff4; border: 1px solid #c6f6d5; }
.verdict.ok { background: #fffff0; border: 1px solid #fefcbf; }
.verdict.bad { background: #fff5f5; border: 1px solid #fed7d7; }
.verdict .icon { font-size: 32px; }
.verdict h3 { font-size: 16px; }
.verdict p { font-size: 13px; color: #718096; }

/* Forecast accuracy bar */
.accuracy-bar { display: flex; height: 40px; border-radius: 6px; overflow: hidden; margin: 16px 0; }
.accuracy-bar .done { background: #38a169; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }
.accuracy-bar .not-done { background: #e53e3e; display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; }

/* Forms */
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-weight: bold; margin-bottom: 4px; font-size: 14px; }
.form-group input, .form-group select { padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 14px; width: 100%; max-width: 400px; }
.form-group .radio-group { display: flex; gap: 16px; }
.form-group .radio-group label { font-weight: normal; }

/* Trend arrows */
.trend-up { color: #38a169; font-size: 12px; }
.trend-down { color: #e53e3e; font-size: 12px; }

/* Nav */
nav { background: white; border-bottom: 1px solid #e2e8f0; padding: 12px 24px; display: flex; gap: 24px; }
nav a { color: #4a5568; font-size: 14px; }
nav a:hover { color: #5f55ee; }
```

- [ ] **Step 2: Create static/dashboard.js**

```javascript
// KPI card click filtering
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.kpi-card[data-filter]').forEach(card => {
    card.addEventListener('click', function() {
      const filter = this.dataset.filter;
      const isActive = this.classList.contains('active');

      // Clear all active cards
      document.querySelectorAll('.kpi-card').forEach(c => c.classList.remove('active'));

      if (isActive) {
        // Clear filter — show all rows
        document.querySelectorAll('.task-table tr[data-filter]').forEach(row => {
          row.classList.remove('filtered-out');
        });
      } else {
        // Activate this card and filter
        this.classList.add('active');
        document.querySelectorAll('.task-table tr[data-filter]').forEach(row => {
          if (row.dataset.filter === filter || row.dataset.filter.includes(filter)) {
            row.classList.remove('filtered-out');
          } else {
            row.classList.add('filtered-out');
          }
        });
      }
    });
  });
});

// Refresh button
async function refreshSprint(sprintId) {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = 'Refreshing...';
  btn.disabled = true;
  try {
    const resp = await fetch(`/sprints/${sprintId}/refresh`, { method: 'POST' });
    if (resp.ok) { location.reload(); }
    else { alert('Refresh failed: ' + (await resp.json()).detail); }
  } catch(e) { alert('Refresh failed: ' + e.message); }
  btn.disabled = false;
  btn.textContent = '🔄 Refresh Now';
}

// Close forecast
async function closeForecast(sprintId) {
  if (!confirm('Close the forecast? This captures the baseline snapshot. Tasks added after this will be tracked as scope changes.')) return;
  const resp = await fetch(`/sprints/${sprintId}/close-forecast`, { method: 'POST' });
  if (resp.ok) { location.reload(); }
  else { alert('Failed: ' + (await resp.json()).detail); }
}

// Close sprint
async function closeSprint(sprintId) {
  if (!confirm('Close this sprint? The report will be frozen for historical reference.')) return;
  const resp = await fetch(`/sprints/${sprintId}/close`, { method: 'POST' });
  if (resp.ok) { location.reload(); }
  else { alert('Failed: ' + (await resp.json()).detail); }
}

// Sync sprints
async function syncSprints(teamId) {
  const btn = document.getElementById('sync-btn');
  btn.textContent = 'Syncing...';
  btn.disabled = true;
  const resp = await fetch(`/teams/${teamId}/sync-sprints`, { method: 'POST' });
  if (resp.ok) { location.reload(); }
  else { alert('Sync failed'); }
}
```

- [ ] **Step 3: Create templates/base.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Sprint Reporter{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
  <nav>
    <a href="/">Home</a>
    {% for t in nav_teams|default([]) %}
    <a href="/teams/{{ t.id }}/sprints">{{ t.name }}</a>
    {% endfor %}
    <a href="/teams/new">+ New Team</a>
  </nav>
  {% block content %}{% endblock %}
  <script src="/static/dashboard.js"></script>
</body>
</html>
```

Note: inject `nav_teams` via a FastAPI middleware or by adding it in each page route. Simplest approach: add a helper in `pages.py`:

```python
def _ctx(request, **kwargs):
    kwargs["request"] = request
    kwargs["nav_teams"] = get_all_teams()
    return kwargs
```

Then use `templates.TemplateResponse("page.html", _ctx(request, team=team, ...))` in each route.

- [ ] **Step 4: Create templates/team_settings.html**

```html
{% extends "base.html" %}
{% block title %}{{ "Edit " + team.name if team else "New Team" }}{% endblock %}
{% block content %}
<div class="top-bar">
  <h1>{{ "Edit " + team.name if team else "New Team" }}</h1>
</div>
<div class="content" style="padding-top: 24px;">
  <div class="panel" style="max-width: 600px;">
    <form id="team-form" method="POST">
      <div class="form-group">
        <label>Team Name</label>
        <input name="name" value="{{ team.name if team else '' }}" required>
      </div>
      <div class="form-group">
        <label>ClickUp Space</label>
        <select name="clickup_space_id" id="space-select" required>
          <option value="">Loading spaces...</option>
        </select>
      </div>
      <div class="form-group">
        <label>ClickUp Folder</label>
        <select name="clickup_folder_id" id="folder-select" required>
          <option value="">Select a space first</option>
        </select>
      </div>
      <div class="form-group">
        <label>Metric Type</label>
        <div class="radio-group">
          <label><input type="radio" name="metric_type" value="task_count" {{ 'checked' if not team or team.metric_type == 'task_count' }}> Task Count</label>
          <label><input type="radio" name="metric_type" value="points" {{ 'checked' if team and team.metric_type == 'points' }}> Points</label>
          <label><input type="radio" name="metric_type" value="hours" {{ 'checked' if team and team.metric_type == 'hours' }}> Hours</label>
        </div>
      </div>
      <div class="form-group">
        <label>Sprint Length (days)</label>
        <input type="number" name="sprint_length_days" value="{{ team.sprint_length_days if team else 14 }}" min="1" max="30">
      </div>
      <button type="submit" class="btn btn-primary">{{ "Update" if team else "Create" }} Team</button>
    </form>
  </div>
</div>
<script>
const currentSpace = "{{ team.clickup_space_id if team else '' }}";
const currentFolder = "{{ team.clickup_folder_id if team else '' }}";
const teamId = {{ team.id if team else 'null' }};

fetch('/api/clickup/spaces').then(r => r.json()).then(spaces => {
  const sel = document.getElementById('space-select');
  sel.innerHTML = '<option value="">Select space...</option>';
  spaces.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.space_id;
    opt.textContent = s.workspace + ' / ' + s.space_name;
    if (s.space_id === currentSpace) opt.selected = true;
    sel.appendChild(opt);
  });
  if (currentSpace) loadFolders(currentSpace);
});

document.getElementById('space-select').addEventListener('change', e => loadFolders(e.target.value));

function loadFolders(spaceId) {
  fetch('/api/clickup/folders/' + spaceId).then(r => r.json()).then(folders => {
    const sel = document.getElementById('folder-select');
    sel.innerHTML = '<option value="">Select folder...</option>';
    folders.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.id;
      opt.textContent = f.name;
      if (f.id === currentFolder) opt.selected = true;
      sel.appendChild(opt);
    });
  });
}

document.getElementById('team-form').addEventListener('submit', async e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  data.sprint_length_days = parseInt(data.sprint_length_days);
  const url = teamId ? `/teams/${teamId}` : '/teams';
  const method = teamId ? 'PUT' : 'POST';
  const resp = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) });
  if (resp.ok) {
    const team = await resp.json();
    window.location.href = `/teams/${team.id}/sprints`;
  } else { alert('Failed: ' + (await resp.json()).detail); }
});
</script>
{% endblock %}
```

- [ ] **Step 5: Create templates/sprint_history.html**

Table page extending base.html. Lists all sprints for a team with columns: name, dates, status badge, velocity, completion %, scope changes. Each row links to sprint detail. Status filter tabs (All / Planning / Active / Closed). "Sync Sprints" button → POST to `/teams/{id}/sync-sprints`.

- [ ] **Step 6: Create templates/home.html**

Simple redirect/landing: if there's an active sprint, redirect to it. Otherwise show team list with links to settings and history.

- [ ] **Step 7: Update src/routes/pages.py with HTML routes**

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from src.services.team_service import get_all_teams, get_team
from src.services.sprint_service import get_team_sprints, get_sprint, get_sprint_status
from src.services.trend_service import get_sprint_summary

templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["pages"])

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    teams = get_all_teams()
    # Check for active sprint
    for team in teams:
        sprints = get_team_sprints(team["id"])
        for s in sprints:
            if get_sprint_status(s) == "active":
                return RedirectResponse(f"/sprint/{s['id']}")
    return templates.TemplateResponse("home.html", {"request": request, "teams": teams})

@router.get("/teams/{team_id}/settings", response_class=HTMLResponse)
def team_settings_page(request: Request, team_id: int = None):
    team = get_team(team_id) if team_id else None
    return templates.TemplateResponse("team_settings.html", {"request": request, "team": team})

@router.get("/teams/new", response_class=HTMLResponse)
def new_team_page(request: Request):
    return templates.TemplateResponse("team_settings.html", {"request": request, "team": None})

@router.get("/teams/{team_id}/sprints", response_class=HTMLResponse)
def sprint_history_page(request: Request, team_id: int):
    team = get_team(team_id)
    sprints = get_team_sprints(team_id)
    sprint_data = []
    for s in sprints:
        s["status"] = get_sprint_status(s)
        if s["status"] == "closed":
            s["summary"] = get_sprint_summary(s["id"])
        sprint_data.append(s)
    return templates.TemplateResponse("sprint_history.html", {"request": request, "team": team, "sprints": sprint_data})
```

- [ ] **Step 8: Verify pages render**

Run:
```bash
python app.py &
sleep 2
curl -s http://localhost:8000/ | head -5
kill %1
```
Expected: HTML output

- [ ] **Step 9: Commit**

```bash
git add templates/ static/ src/routes/pages.py
git commit -m "feat: base templates, team settings, sprint history, and static assets"
```

---

### Task 10: Live Sprint View Page

**Files:**
- Create: `templates/sprint_live.html`
- Create: `templates/components/kpi_cards.html`
- Create: `templates/components/task_table.html`
- Create: `templates/components/burndown_chart.html`
- Create: `templates/components/scope_timeline.html`
- Modify: `src/routes/pages.py` — add sprint detail page route

- [ ] **Step 1: Create templates/components/kpi_cards.html**

```html
<div class="kpi-row">
  <div class="kpi-card" data-filter="forecasted">
    <div class="label">Forecasted</div>
    <div class="value">{{ summary.forecasted|default(0) }}</div>
    <div class="sub">{{ team.metric_type }}</div>
  </div>
  <div class="kpi-card" data-filter="completed">
    <div class="value green">{{ summary.completed|default(0) }}</div>
    <div class="label">Completed</div>
    <div class="sub">of {{ summary.forecasted|default(0) }}</div>
  </div>
  <div class="kpi-card" data-filter="scope_changes">
    <div class="value red">+{{ summary.scope_added|default(0) }} / -{{ summary.scope_removed|default(0) }}</div>
    <div class="label">Scope Changes</div>
    <div class="sub">added / removed</div>
  </div>
  <div class="kpi-card" data-filter="not_completed">
    <div class="value purple">{{ (summary.completion_rate|default(0) * 100)|round|int }}%</div>
    <div class="label">Completion</div>
    <div class="sub">Day {{ sprint_day|default('?') }} of {{ team.sprint_length_days }}</div>
  </div>
  {% if on_track is defined %}
  <div class="kpi-card">
    <div class="value">{% if on_track == 'ahead' %}✅{% elif on_track == 'on_track' %}👍{% else %}⚠️{% endif %}</div>
    <div class="label">On Track?</div>
    <div class="sub">{{ on_track|replace('_', ' ')|title }}</div>
  </div>
  {% endif %}
</div>
```

- [ ] **Step 2: Create templates/components/burndown_chart.html**

```html
<div class="panel">
  <h3>Burndown Chart</h3>
  <div class="chart-container">
    <canvas id="burndownChart"></canvas>
  </div>
</div>
<script>
(function() {
  const progressData = {{ progress_history|tojson }};
  const forecasted = {{ summary.forecasted|default(0) }};
  const sprintDays = {{ team.sprint_length_days }};

  // Build ideal line
  const idealLabels = [];
  const idealData = [];
  for (let i = 0; i <= sprintDays; i++) {
    idealLabels.push('Day ' + i);
    idealData.push(Math.round(forecasted - (forecasted / sprintDays) * i));
  }

  // Build actual line from progress snapshots
  const actualData = progressData.map(p => forecasted - p.completed_tasks);

  new Chart(document.getElementById('burndownChart'), {
    type: 'line',
    data: {
      labels: idealLabels.slice(0, Math.max(actualData.length, 2)),
      datasets: [
        { label: 'Ideal', data: idealData, borderColor: '#cbd5e0', borderDash: [6, 4], borderWidth: 2, pointRadius: 0, fill: false },
        { label: 'Actual', data: actualData, borderColor: '#5f55ee', borderWidth: 3, pointRadius: 3, fill: false }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { y: { beginAtZero: true, title: { display: true, text: 'Remaining' } } },
      plugins: { legend: { position: 'bottom' } }
    }
  });
})();
</script>
```

- [ ] **Step 3: Create templates/components/scope_timeline.html**

```html
{% if scope_changes %}
<div class="panel">
  <h3>Scope Changes</h3>
  <div class="scope-timeline">
    {% for change in scope_changes %}
    <div class="scope-event {{ change.change_type }}">
      <div class="date">{{ change.detected_at[:10] }}</div>
      <div class="detail">
        {% if change.change_type == 'added' %}➕{% else %}➖{% endif %}
        "{{ change.task_name }}"
        {% if change.assignee_name %} — {{ change.assignee_name }}{% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 4: Create templates/components/task_table.html**

```html
<div class="panel">
  <h3>Tasks</h3>
  <table class="task-table">
    <thead>
      <tr><th></th><th>Task</th><th>Assignee</th><th>Status</th><th>{{ team.metric_type|title }}</th></tr>
    </thead>
    <tbody>
      {% for task in tasks %}
      <tr data-filter="{% if task.task_status in ['complete','closed'] %}completed forecasted{% elif task.scope_change == 'added' %}scope_changes{% elif task.scope_change == 'removed' %}scope_changes{% else %}not_completed forecasted{% endif %}"
          class="{% if task.scope_change == 'added' %}scope-added{% elif task.scope_change == 'removed' %}scope-removed{% endif %}">
        <td>{% if task.task_status in ['complete','closed'] %}✅{% elif task.scope_change == 'added' %}➕{% elif task.scope_change == 'removed' %}➖{% elif task.task_status == 'in progress' %}🔵{% else %}⬜{% endif %}</td>
        <td>{{ task.task_name }}{% if task.scope_change == 'added' %}<span class="scope-badge">(added)</span>{% endif %}</td>
        <td>{{ task.assignee_name or '—' }}</td>
        <td><span class="badge-{{ 'complete' if task.task_status in ['complete','closed'] else ('progress' if task.task_status == 'in progress' else 'todo') }}">{{ task.task_status }}</span></td>
        <td>{% if team.metric_type == 'points' %}{{ task.points or '—' }}{% elif team.metric_type == 'hours' %}{{ task.hours or '—' }}{% else %}1{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

- [ ] **Step 5: Create templates/sprint_live.html**

```html
{% extends "base.html" %}
{% block title %}{{ sprint.name }} — Sprint Reporter{% endblock %}
{% block content %}
<div class="top-bar">
  <div>
    <h1 style="display:inline">{{ sprint.name }}</h1>
    <span class="meta">{{ sprint.start_date }} — {{ sprint.end_date }}</span>
    <span class="badge badge-{{ status }}">{{ status|upper }}</span>
  </div>
  <div class="actions">
    {% if status == 'active' %}
    <button class="btn btn-secondary" id="refresh-btn" onclick="refreshSprint({{ sprint.id }})">🔄 Refresh Now</button>
    <button class="btn btn-danger" onclick="closeSprint({{ sprint.id }})">🔒 Close Sprint</button>
    {% elif status == 'planning' %}
    <button class="btn btn-success" onclick="closeForecast({{ sprint.id }})">📋 Close Forecast</button>
    {% endif %}
  </div>
</div>

{% if status != 'planning' %}
{% include "components/kpi_cards.html" %}
<div class="content">
  <div class="grid-2">
    {% include "components/burndown_chart.html" %}
    {% include "components/scope_timeline.html" %}
  </div>
  {% include "components/task_table.html" %}
</div>
{% else %}
<div class="content" style="padding-top: 24px;">
  <div class="panel">
    <h3>Planning Phase</h3>
    <p>This sprint is in planning. Fill the iteration list in ClickUp, then click <strong>Close Forecast</strong> to start tracking.</p>
    <p style="margin-top: 12px; color: #718096;">{{ tasks|length }} tasks currently in this list.</p>
  </div>
  {% include "components/task_table.html" %}
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 6: Add sprint detail page route to src/routes/pages.py**

```python
@router.get("/sprint/{sprint_id}", response_class=HTMLResponse)
async def sprint_page(request: Request, sprint_id: int):
    sprint = get_sprint(sprint_id)
    status = get_sprint_status(sprint)
    team = get_team(sprint["team_id"])

    # Get live tasks if active, or snapshot if closed
    if status == "active":
        from src.clickup_client import ClickUpClient
        from src.config import CLICKUP_API_KEY
        client = ClickUpClient(CLICKUP_API_KEY)
        raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"])
        tasks = [client.extract_task_data(t) for t in raw_tasks]
    elif status == "planning":
        from src.clickup_client import ClickUpClient
        from src.config import CLICKUP_API_KEY
        client = ClickUpClient(CLICKUP_API_KEY)
        raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"])
        tasks = [client.extract_task_data(t) for t in raw_tasks]
    else:
        tasks = []  # Closed sprints use sprint_report.html

    summary = get_sprint_summary(sprint_id) if status != "planning" else {}
    scope_changes = get_scope_changes(sprint_id) if status != "planning" else []
    progress = get_daily_progress_history(sprint_id) if status != "planning" else []

    template = "sprint_live.html" if status != "closed" else "sprint_report.html"
    return templates.TemplateResponse(template, {
        "request": request, "sprint": sprint, "status": status,
        "team": team, "tasks": tasks, "summary": summary,
        "scope_changes": scope_changes, "progress_history": progress,
    })
```

Add missing imports at top of pages.py:
```python
from src.services.snapshot_service import get_scope_changes, get_daily_progress_history
```

- [ ] **Step 7: Manual test — create team, sync sprints, view live page**

Run app, then in browser:
1. Go to `/team/new` → create team pointing to PA Setup Template
2. Click "Sync Sprints"
3. Click on an iteration to see live view
4. Verify KPI cards, burndown placeholder, task table render

- [ ] **Step 8: Commit**

```bash
git add templates/ src/routes/pages.py
git commit -m "feat: live sprint view with KPI cards, burndown chart, scope timeline, and task table"
```

---

### Task 11: Sprint Report Page (Closed Sprint View)

**Files:**
- Create: `templates/sprint_report.html`

- [ ] **Step 1: Create templates/sprint_report.html**

Extends base.html. Same structure as live view but frozen. Components: top bar with CLOSED badge and "Back to History" link (no Refresh/Close buttons), summary verdict banner (green if >80%, yellow if 60-80%, red if <60%), KPI cards (clickable filters — same component), final burndown chart, forecast accuracy bar (stacked horizontal bar), scope change timeline, full task list with not-completed tasks highlighted in red section at bottom.

The page receives the same template variables as the live view (sprint, status, team, tasks, summary, scope_changes, progress_history) — all from stored snapshots, no live API calls.

- [ ] **Step 2: Manual test — close a sprint, verify report renders**

In the running app:
1. Open an active sprint → click "Close Sprint"
2. Verify redirect to report page
3. Check verdict banner, burndown, accuracy bar, task list

- [ ] **Step 3: Commit**

```bash
git add templates/sprint_report.html
git commit -m "feat: frozen sprint report page with verdict, accuracy bar, and scope timeline"
```

---

### Task 12: Team Performance Over Time Page

**Files:**
- Create: `templates/team_trends.html`
- Modify: `src/routes/pages.py` — add trends page route

- [ ] **Step 1: Create templates/team_trends.html**

Extends base.html. Components:
- Top bar with team name and sprint range selector (Last 4 / Last 8 / All — links with query param `?range=4`)
- Trend KPI cards: avg velocity, avg completion rate, avg scope change — each with trend arrow computed by comparing first half vs second half of sprints
- Velocity bar chart (Chart.js bar + trend line)
- Completion rate line chart with 80% target line
- Scope changes chart (stacked bar: green added, red removed)
- Sprint comparison table: all closed sprints with velocity, completion %, scope changes, forecast accuracy. Each row links to `/sprint/{id}`

- [ ] **Step 2: Add trends page route to src/routes/pages.py**

```python
@router.get("/teams/{team_id}/trends", response_class=HTMLResponse)
def team_trends_page(request: Request, team_id: int, range: int = 8):
    team = get_team(team_id)
    trends = get_team_trends(team_id, limit=range)
    return templates.TemplateResponse("team_trends.html", {
        "request": request, "team": team, "trends": trends, "range": range,
    })
```

- [ ] **Step 3: Manual test — view trends page with closed sprints**

Verify charts render, sprint comparison table links work, range selector changes data.

- [ ] **Step 4: Commit**

```bash
git add templates/team_trends.html src/routes/pages.py
git commit -m "feat: team performance trends page with velocity, completion, and scope charts"
```

---

### Task 13: Daily Auto-Snapshot Scheduler

**Files:**
- Modify: `app.py` — add APScheduler for daily snapshots

- [ ] **Step 1: Add scheduler to app.py**

```python
from apscheduler.schedulers.background import BackgroundScheduler
from src.config import DAILY_SNAPSHOT_TIME, CLICKUP_API_KEY, DB_PATH
from src.services.sprint_service import get_sprint, get_sprint_status
from src.services.snapshot_service import detect_scope_changes, record_daily_progress
from src.clickup_client import ClickUpClient
from src.database import get_connection
import asyncio

async def daily_snapshot_job():
    conn = get_connection(DB_PATH)
    sprints = conn.execute(
        "SELECT * FROM sprints WHERE forecast_closed_at IS NOT NULL AND closed_at IS NULL"
    ).fetchall()
    conn.close()

    client = ClickUpClient(CLICKUP_API_KEY)
    for sprint in sprints:
        sprint = dict(sprint)
        raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"])
        tasks = [client.extract_task_data(t) for t in raw_tasks]
        detect_scope_changes(sprint["id"], tasks)
        completed = sum(1 for t in tasks if t["task_status"] in ("complete", "closed"))
        total_points = sum(t["points"] or 0 for t in tasks)
        completed_points = sum(t["points"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
        total_hours = sum(t["hours"] or 0 for t in tasks)
        completed_hours = sum(t["hours"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
        record_daily_progress(sprint["id"], len(tasks), completed, total_points, completed_points, total_hours, completed_hours)

def run_daily_snapshot():
    asyncio.run(daily_snapshot_job())

# In startup event, add:
scheduler = BackgroundScheduler()
hour, minute = DAILY_SNAPSHOT_TIME.split(":")
scheduler.add_job(run_daily_snapshot, "cron", hour=int(hour), minute=int(minute))

@app.on_event("startup")
def startup():
    init_db(DB_PATH)
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()
```

- [ ] **Step 2: Verify scheduler starts without errors**

Run: `python app.py`
Check log output for APScheduler startup message. No errors.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: daily auto-snapshot scheduler using APScheduler"
```

---

### Task 14: End-to-End Integration Test

**Files:**
- No new files — manual test against PA Setup Template space

- [ ] **Step 1: Create .env with real ClickUp API key**

```
CLICKUP_API_KEY=pk_<your_new_rotated_key>
HOST=localhost
PORT=8000
DB_PATH=./sprint_data.db
DAILY_SNAPSHOT_TIME=06:00
```

- [ ] **Step 2: Start app and create team**

Run: `python app.py`
Browser: go to `http://localhost:8000/teams/new`
- Name: "Product Team Template 1"
- Space: PA Setup Template (90125112812)
- Folder: Product Team Template 1 (90128667171)
- Metric: task_count
- Sprint length: 14

- [ ] **Step 3: Sync sprints**

Click "Sync Sprints" — verify iteration lists appear in sprint history.

- [ ] **Step 4: Test full sprint lifecycle**

1. Click on "Iteration 6 (9/3 - 22/3)" → live view in planning state
2. Click "Close Forecast" → verify snapshot captured, KPIs appear
3. Click "Refresh Now" → verify data updates
4. Click "Close Sprint" → verify report page renders with verdict
5. Go to sprint history → verify closed sprint appears with stats
6. Go to team trends → verify charts render (may only have 1 data point)

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete sprint reporting MVP with full lifecycle"
```
