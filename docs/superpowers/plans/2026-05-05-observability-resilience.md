# Observability & Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app stable for unattended operation — structured logging, ClickUp API retry with backoff, daily snapshot resilience, catch-up on missed days.

**Architecture:** New `src/logging_config.py` for shared logger setup. `clickup_client.py` gets retry loop + custom error class. `app.py` gets per-sprint isolation in the snapshot job and a catch-up trigger in `lifespan`. No new dependencies, no DB schema changes.

**Tech Stack:** Python `logging` (stdlib), `httpx` (already pinned 0.27.0), APScheduler (already used), `asyncio`, SQLite via existing `app_settings` k/v table.

**Spec:** `docs/superpowers/specs/2026-05-05-observability-resilience-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/logging_config.py` | Create | `configure_logging(log_path, level)` — idempotent root-logger setup with rotating file + stdout handlers, plus level taming for httpx/apscheduler. |
| `src/clickup_client.py` | Modify | Add module logger, `ClickUpError` class, retry loop in `_get` with exponential backoff. |
| `src/services/snapshot_service.py` | Modify | Module logger; info logs for record_daily_progress, scope changes detected. |
| `src/services/sprint_service.py` | Modify | Module logger; info logs for close_forecast / close_sprint state transitions. |
| `app.py` | Modify | Call `configure_logging()` at lifespan start; refactor `daily_snapshot_job` for per-sprint isolation; add `_should_catch_up_snapshot()` + `_record_last_snapshot_run()`; trigger catch-up via `asyncio.create_task` stored on `app.state`. |

---

## Task 1: Logging foundation

**Files:**
- Create: `src/logging_config.py`
- Modify: `app.py` — call `configure_logging()` from `lifespan`

### Step 1: Create `src/logging_config.py`

Use `Write` with this exact content:

```python
"""Shared logging configuration for the Sprint Reporter app.

Call configure_logging() once at app startup. It's idempotent — second
call is a no-op so importing modules can safely call it defensively.
"""
import logging
import logging.handlers

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(log_path: str = "app.log", level: str = "INFO") -> None:
    """Set up root logger with rotating file + stdout handlers.

    File rotates at 5MB, keeps 5 backups (so app.log + app.log.1..app.log.5).
    Tames chatty libraries (httpx, apscheduler) to WARNING level.
    Idempotent: subsequent calls return immediately.
    """
    if getattr(configure_logging, "_done", False):
        return

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    configure_logging._done = True
```

### Step 2: Verify the module imports

Run:
```bash
.venv/bin/python -c "from src.logging_config import configure_logging; configure_logging('/tmp/test_log.log'); import logging; logging.getLogger('test').info('hello'); print('OK')"
```

Expected: prints `OK` plus a formatted line `[YYYY-MM-DD HH:MM:SS] [INFO] [test] hello` on stdout. Verify the file exists:

```bash
cat /tmp/test_log.log
```

Should show the same line. Cleanup: `rm /tmp/test_log.log`.

### Step 3: Wire `configure_logging()` into `app.py`'s lifespan

Find the existing `lifespan` function (lines 17-24) and insert the configure call as the first thing it does.

Use `Edit`:

old_string:
```
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    init_db(DB_PATH)
    scheduler.start()
    yield
    # shutdown
    scheduler.shutdown()
```

new_string:
```
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    configure_logging()
    log.info("App startup")
    init_db(DB_PATH)
    scheduler.start()
    yield
    # shutdown
    log.info("App shutdown")
    scheduler.shutdown()
```

### Step 4: Add the `configure_logging` import + module logger to `app.py`

Use `Edit`:

old_string:
```
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import HOST, PORT, DB_PATH
from src.database import init_db
from src.routes import teams, sprints, clickup_proxy, pages
import os
from apscheduler.schedulers.background import BackgroundScheduler
from src.config import DAILY_SNAPSHOT_TIME, get_clickup_api_key
from src.services.snapshot_service import detect_scope_changes, record_daily_progress
from src.clickup_client import ClickUpClient
from src.database import get_connection
import asyncio
```

new_string:
```
import uvicorn
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import HOST, PORT, DB_PATH
from src.database import init_db
from src.routes import teams, sprints, clickup_proxy, pages
import os
from apscheduler.schedulers.background import BackgroundScheduler
from src.config import DAILY_SNAPSHOT_TIME, get_clickup_api_key
from src.services.snapshot_service import detect_scope_changes, record_daily_progress
from src.clickup_client import ClickUpClient
from src.database import get_connection
from src.logging_config import configure_logging
import asyncio

log = logging.getLogger(__name__)
```

### Step 5: Restart and verify logs flow

Run: `./stop.sh && ./start.sh`
Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

Then:
```bash
tail -5 app.log
```

Expected: at least one line like `[2026-05-05 ...] [INFO] [app] App startup`.

If the format isn't there, STOP and report BLOCKED — `configure_logging` didn't fire.

### Step 6: Commit

```bash
git add src/logging_config.py app.py
git commit -m "$(cat <<'EOF'
feat(observability): add structured logging via Python's logging module

Adds src/logging_config.py with configure_logging() that sets up
rotating file (5MB × 5 backups) + stdout handlers, tames httpx and
apscheduler to WARNING level. app.py calls it at lifespan startup
and gets a module-level logger.

Format: [timestamp] [LEVEL] [module.name] message

Refs spec: docs/superpowers/specs/2026-05-05-observability-resilience-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Task 2: ClickUp client retry + ClickUpError

**Files:**
- Modify: `src/clickup_client.py` — replace `_get`, add `ClickUpError`, add module logger

### Step 1: Replace the entire content of `src/clickup_client.py`

Use `Write` (full replacement is cleaner than three separate Edits since the imports + new class + new `_get` interlock):

```python
import asyncio
import logging
import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.clickup.com/api/v2"

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_BASE = 1.0   # seconds; doubles each retry → 1, 2, 4


class ClickUpError(Exception):
    """Raised when a ClickUp API call fails permanently (after retries)
    or with a non-retriable status code."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ClickUpClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": api_key}

    async def _get(self, path: str, params: dict = None) -> dict:
        url = f"{BASE_URL}{path}"
        response = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    response = await client.get(url, headers=self.headers, params=params or {})
                if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                    delay = BACKOFF_BASE * (2 ** attempt)
                    log.warning(
                        "ClickUp %s returned %d; retrying in %.1fs (attempt %d/%d)",
                        path, response.status_code, delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt < MAX_RETRIES:
                    delay = BACKOFF_BASE * (2 ** attempt)
                    log.warning(
                        "ClickUp %s network error (%s); retrying in %.1fs (attempt %d/%d)",
                        path, type(e).__name__, delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue
                log.error("ClickUp %s exhausted retries on network error: %s", path, e)
                raise ClickUpError(f"Network error after {MAX_RETRIES} retries: {e}") from e
            except httpx.HTTPStatusError as e:
                # 4xx (non-429) — caller's fault, don't retry
                log.error(
                    "ClickUp %s returned %d (non-retriable); body=%s",
                    path, e.response.status_code, e.response.text[:500],
                )
                raise ClickUpError(
                    f"ClickUp returned {e.response.status_code} for {path}",
                    status_code=e.response.status_code,
                    body=e.response.text[:500],
                ) from e
        # Loop exited because retries exhausted on a retriable status
        log.error(
            "ClickUp %s returned %d after %d retries",
            path, response.status_code if response is not None else -1, MAX_RETRIES,
        )
        raise ClickUpError(
            f"ClickUp {path} returned {response.status_code if response is not None else 'no response'} after {MAX_RETRIES} retries",
            status_code=response.status_code if response is not None else None,
            body=response.text[:500] if response is not None else None,
        )

    async def get_workspaces(self) -> list[dict]:
        data = await self._get("/team")
        return data.get("teams", [])

    async def get_spaces(self, team_id: str) -> list[dict]:
        data = await self._get(f"/team/{team_id}/space", {"archived": "false"})
        return data.get("spaces", [])

    async def get_folders(self, space_id: str) -> list[dict]:
        data = await self._get(f"/space/{space_id}/folder")
        return data.get("folders", [])

    async def get_teams(self, workspace_id: str) -> list[dict]:
        data = await self._get("/group", {"team_id": workspace_id})
        return data.get("groups", [])

    async def get_folder_lists(self, folder_id: str) -> list[dict]:
        data = await self._get(f"/folder/{folder_id}/list")
        return data.get("lists", [])

    async def get_list_tasks(self, list_id: str, **_kwargs) -> list[dict]:
        """Get all tasks in a list, including tasks in multiple lists (TIML)."""
        all_tasks = []
        page = 0
        while True:
            data = await self._get(
                f"/list/{list_id}/task",
                {
                    "include_closed": "true",
                    "subtasks": "true",
                    "include_timl": "true",
                    "page": str(page),
                },
            )
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)
            if len(tasks) < 100:
                break
            page += 1
        # Filter out subtasks whose parent is also in this list (avoid double-counting)
        task_ids = {t["id"] for t in all_tasks}
        return [t for t in all_tasks if not t.get("parent") or t["parent"] not in task_ids]

    def extract_task_data(self, raw_task: dict) -> dict:
        assignees = raw_task.get("assignees", [])
        time_estimate = raw_task.get("time_estimate")
        time_by_user = raw_task.get("time_estimates_by_user", [])

        assignee_hours = []
        for entry in time_by_user:
            user = entry.get("user", {})
            ms = entry.get("time_estimate", 0) or 0
            assignee_hours.append({
                "name": user.get("username", "?"),
                "hours": round(ms / 3_600_000, 2),
            })

        # If no per-user breakdown, fall back to assignees with total split
        if not assignee_hours and assignees:
            total_h = round(time_estimate / 3_600_000, 2) if time_estimate else 0
            if len(assignees) == 1:
                assignee_hours = [{"name": assignees[0]["username"], "hours": total_h}]
            else:
                assignee_hours = [{"name": a["username"], "hours": 0} for a in assignees]

        return {
            "task_id": raw_task["id"],
            "task_name": raw_task["name"],
            "task_status": raw_task["status"]["status"],
            "assignee_name": ", ".join(a["username"] for a in assignees) if assignees else None,
            "assignee_hours": assignee_hours,
            "points": raw_task.get("points"),
            "hours": round(time_estimate / 3_600_000, 2) if time_estimate else None,
        }
```

### Step 2: Verify Python parses

```bash
.venv/bin/python -c "from src.clickup_client import ClickUpClient, ClickUpError; print('OK')"
```

Expected: `OK`. Else STOP.

### Step 3: Quick happy-path test against real ClickUp

The dev environment's `.env` should still have a valid CLICKUP_API_KEY. Run:

```bash
.venv/bin/python -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from src.clickup_client import ClickUpClient
async def main():
    c = ClickUpClient(os.getenv('CLICKUP_API_KEY'))
    teams = await c.get_workspaces()
    print(f'OK — got {len(teams)} workspace(s)')
asyncio.run(main())
"
```

Expected: `OK — got N workspace(s)` (some non-zero number). If `ClickUpError`, STOP and inspect — likely a real auth issue or environment problem.

### Step 4: Restart and verify no regressions

Run: `./stop.sh && ./start.sh`. Expected: app starts.

Open the browser, click `Sync from ClickUp` on `/teams/1/sprints` to trigger a real ClickUp call. Verify:
- The sync succeeds (no error toast)
- `tail -5 app.log` shows nothing new (because the sync was successful — only WARNING/ERROR would log)

### Step 5: Commit

```bash
git add src/clickup_client.py
git commit -m "$(cat <<'EOF'
feat(observability): retry + ClickUpError + module logger in ClickUp client

Adds explicit timeout (30s read, 10s connect), retry loop on
5xx/429/network errors with exponential backoff (1/2/4s), and a
custom ClickUpError class that carries status_code + truncated
body for downstream handlers.

4xx (non-429) errors are caller's fault — not retried, raised
immediately as ClickUpError.

Logs every retry attempt at WARNING; final failure at ERROR.

Refs spec: docs/superpowers/specs/2026-05-05-observability-resilience-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Task 3: Snapshot resilience + catch-up

**Files:**
- Modify: `app.py` — refactor `daily_snapshot_job`, add helpers, add catch-up trigger
- Modify: `src/services/snapshot_service.py` — add module logger
- Modify: `src/services/sprint_service.py` — add module logger

### Step 1: Add module logger to `src/services/snapshot_service.py`

Read current top of file:

```bash
head -10 src/services/snapshot_service.py
```

Use `Edit` to add `import logging` + `log = logging.getLogger(__name__)` at the top (after existing imports). Find the first import block:

```bash
sed -n '1,10p' src/services/snapshot_service.py
```

Then `Edit` to insert `import logging` + `log = logging.getLogger(__name__)` after the imports. Concrete edit (assuming first 5 lines are existing imports):

If you read these first 5 lines:
```python
import json
from datetime import datetime, date
from src.database import get_connection
from src.config import DB_PATH
```

Use `Edit`:

old_string:
```
import json
from datetime import datetime, date
from src.database import get_connection
from src.config import DB_PATH
```

new_string:
```
import json
import logging
from datetime import datetime, date
from src.database import get_connection
from src.config import DB_PATH

log = logging.getLogger(__name__)
```

(If your file doesn't match exactly, read the actual first 10 lines and craft the edit to add `import logging` next to other imports and `log = logging.getLogger(__name__)` after them.)

### Step 2: Add module logger to `src/services/sprint_service.py`

Same as Step 1 but for `src/services/sprint_service.py`. Read current imports:

```bash
sed -n '1,10p' src/services/sprint_service.py
```

Add `import logging` and `log = logging.getLogger(__name__)` near the top, in the same shape as snapshot_service.

### Step 3: Replace `app.py`'s daily_snapshot_job and add helpers

Use `Edit` to replace the existing `daily_snapshot_job` and `run_daily_snapshot` with the resilient version + helpers.

old_string:
```
async def daily_snapshot_job():
    from datetime import date
    from src.config import DB_PATH
    from src.services.sprint_service import close_sprint as do_close_sprint
    from src.services.snapshot_service import save_forecast_snapshot, get_forecast_snapshot, save_final_snapshot
    conn = get_connection(DB_PATH)
    sprints = conn.execute(
        "SELECT * FROM sprints WHERE forecast_closed_at IS NOT NULL AND closed_at IS NULL"
    ).fetchall()
    conn.close()

    client = ClickUpClient(get_clickup_api_key())
    for sprint in sprints:
        sprint = dict(sprint)
        from src.services.team_service import get_team
        team = get_team(sprint["team_id"])
        raw_tasks = await client.get_list_tasks(sprint["clickup_list_id"], space_id=team["clickup_space_id"], workspace_id=team.get("clickup_workspace_id"))
        tasks = [client.extract_task_data(t) for t in raw_tasks]
        detect_scope_changes(sprint["id"], tasks, sprint_start_date=sprint.get("start_date"))
        completed = sum(1 for t in tasks if t["task_status"] in ("complete", "closed"))
        total_points = sum(t["points"] or 0 for t in tasks)
        completed_points = sum(t["points"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
        total_hours = sum(t["hours"] or 0 for t in tasks)
        completed_hours = sum(t["hours"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
        record_daily_progress(sprint["id"], len(tasks), completed, total_points, completed_points, total_hours, completed_hours)

        # Auto-close sprint if end_date has passed
        if sprint.get("end_date"):
            end = sprint["end_date"]
            if isinstance(end, str):
                end = date.fromisoformat(end)
            if date.today() > end:
                save_final_snapshot(sprint["id"], tasks)
                snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint["id"])}
                added_tasks = [t for t in tasks if t["task_id"] not in snapshot_ids]
                if added_tasks:
                    save_forecast_snapshot(sprint["id"], added_tasks)
                do_close_sprint(sprint["id"])

def run_daily_snapshot():
    asyncio.run(daily_snapshot_job())
```

new_string:
```
async def _snapshot_one_sprint(sprint: dict, client: ClickUpClient) -> None:
    """Capture daily progress + scope changes for a single sprint.
    Auto-closes the sprint if its end_date has passed.
    Caller must wrap in try/except — this raises on any failure."""
    from datetime import date
    from src.services.sprint_service import close_sprint as do_close_sprint
    from src.services.snapshot_service import save_forecast_snapshot, get_forecast_snapshot, save_final_snapshot
    from src.services.team_service import get_team

    team = get_team(sprint["team_id"])
    raw_tasks = await client.get_list_tasks(
        sprint["clickup_list_id"],
        space_id=team["clickup_space_id"],
        workspace_id=team.get("clickup_workspace_id"),
    )
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    detect_scope_changes(sprint["id"], tasks, sprint_start_date=sprint.get("start_date"))
    completed = sum(1 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_points = sum(t["points"] or 0 for t in tasks)
    completed_points = sum(t["points"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    total_hours = sum(t["hours"] or 0 for t in tasks)
    completed_hours = sum(t["hours"] or 0 for t in tasks if t["task_status"] in ("complete", "closed"))
    record_daily_progress(sprint["id"], len(tasks), completed, total_points, completed_points, total_hours, completed_hours)
    log.info("Snapshot captured for sprint id=%s (%d tasks, %d completed)",
             sprint["id"], len(tasks), completed)

    # Auto-close sprint if end_date has passed
    if sprint.get("end_date"):
        end = sprint["end_date"]
        if isinstance(end, str):
            end = date.fromisoformat(end)
        if date.today() > end:
            save_final_snapshot(sprint["id"], tasks)
            snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint["id"])}
            added_tasks = [t for t in tasks if t["task_id"] not in snapshot_ids]
            if added_tasks:
                save_forecast_snapshot(sprint["id"], added_tasks)
            do_close_sprint(sprint["id"])
            log.info("Auto-closed sprint id=%s (end_date %s passed)", sprint["id"], end)


async def daily_snapshot_job():
    log.info("Daily snapshot job starting")
    conn = get_connection(DB_PATH)
    sprints = conn.execute(
        "SELECT * FROM sprints WHERE forecast_closed_at IS NOT NULL AND closed_at IS NULL"
    ).fetchall()
    conn.close()

    client = ClickUpClient(get_clickup_api_key())
    success = 0
    failed = 0
    for raw_sprint in sprints:
        sprint = dict(raw_sprint)
        try:
            await _snapshot_one_sprint(sprint, client)
            success += 1
        except Exception:
            log.exception("Daily snapshot failed for sprint id=%s name=%s",
                          sprint.get("id"), sprint.get("name"))
            failed += 1
            continue

    log.info("Daily snapshot job done — %d succeeded, %d failed", success, failed)
    if success > 0:
        _record_last_snapshot_run()


def _record_last_snapshot_run() -> None:
    from src.database import set_setting
    from datetime import datetime
    set_setting(DB_PATH, "last_snapshot_run", datetime.utcnow().isoformat())


def _should_catch_up_snapshot() -> bool:
    """Return True if last_snapshot_run is missing or older than 24 hours."""
    from src.database import get_setting
    from datetime import datetime, timedelta
    last = get_setting(DB_PATH, "last_snapshot_run")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        log.warning("last_snapshot_run has invalid ISO format: %r — triggering catch-up", last)
        return True
    return datetime.utcnow() - last_dt > timedelta(hours=24)


def run_daily_snapshot():
    asyncio.run(daily_snapshot_job())
```

### Step 4: Update `lifespan` to fire catch-up

Use `Edit`:

old_string:
```
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    configure_logging()
    log.info("App startup")
    init_db(DB_PATH)
    scheduler.start()
    yield
    # shutdown
    log.info("App shutdown")
    scheduler.shutdown()
```

new_string:
```
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    configure_logging()
    log.info("App startup")
    init_db(DB_PATH)
    if _should_catch_up_snapshot():
        log.info("Last snapshot run was >24h ago (or never); firing catch-up job")
        # Hold the task ref on app.state so Python's GC doesn't collect it mid-run.
        app.state.catchup_task = asyncio.create_task(daily_snapshot_job())
    scheduler.start()
    yield
    # shutdown
    log.info("App shutdown")
    scheduler.shutdown()
```

### Step 5: Verify Python compiles

Run: `.venv/bin/python -c "import app; print('OK')"`
Expected: `OK`. Else STOP.

### Step 6: Restart and observe catch-up

Run: `./stop.sh && ./start.sh`

Expected (`tail -20 app.log`):
- `[...] [INFO] [app] App startup`
- `[...] [INFO] [app] Last snapshot run was >24h ago (or never); firing catch-up job` (this fires on first restart since last_snapshot_run doesn't exist yet)
- A few seconds later: `[...] [INFO] [app] Daily snapshot job starting`
- Per-sprint: `[...] [INFO] [snapshot_service] Snapshot captured for sprint id=X ...` OR `[...] [ERROR] [app] Daily snapshot failed for sprint id=X ...`
- `[...] [INFO] [app] Daily snapshot job done — N succeeded, M failed`

### Step 7: Verify last_snapshot_run was recorded

```bash
sqlite3 sprint_data.db "SELECT * FROM app_settings WHERE key = 'last_snapshot_run';"
```

Expected: a row like `last_snapshot_run|2026-05-05T14:30:12.345678`.

### Step 8: Verify a second restart does NOT trigger catch-up

Restart again: `./stop.sh && ./start.sh`. Wait 2 seconds, then `tail -10 app.log`.
Expected: `App startup` followed by `App shutdown`/normal logs — NOT `Last snapshot run was >24h ago` (because we just ran).

### Step 9: Verify per-sprint isolation works

Manually trigger a controlled failure to confirm the per-sprint `try/except` path. In a Python REPL:

```bash
.venv/bin/python -c "
import asyncio
from app import _snapshot_one_sprint
# Simulating: pass a sprint with a bogus list_id should raise inside _get
class FakeClient:
    async def get_list_tasks(self, *a, **kw):
        raise RuntimeError('simulated')
    def extract_task_data(self, t): return t

async def main():
    try:
        await _snapshot_one_sprint({'id': 999, 'team_id': 1, 'clickup_list_id': 'fake', 'name': 'fake'}, FakeClient())
        print('WRONG — should have raised')
    except Exception as e:
        print(f'OK — raised {type(e).__name__}: {e}')

asyncio.run(main())
"
```

Expected: `OK — raised RuntimeError: simulated`. Confirms `_snapshot_one_sprint` raises (and so the caller's try/except is what isolates).

### Step 10: Commit

```bash
git add app.py src/services/snapshot_service.py src/services/sprint_service.py
git commit -m "$(cat <<'EOF'
feat(observability): snapshot resilience + catch-up + per-module loggers

- Refactors daily_snapshot_job: extracts per-sprint logic into
  _snapshot_one_sprint(); wraps each sprint in try/except so one
  failure (network, ClickUp 5xx, malformed data) doesn't stop the
  loop. Logs success/fail counters at INFO.
- Adds _should_catch_up_snapshot() and _record_last_snapshot_run()
  using existing app_settings k/v table. last_snapshot_run is the
  ISO timestamp of the most recent successful run.
- lifespan startup fires daily_snapshot_job in the background via
  asyncio.create_task if last_snapshot_run is missing or >24h old.
  Task ref stored on app.state.catchup_task so Python's GC doesn't
  collect it mid-run.
- snapshot_service and sprint_service get module loggers.

Refs spec: docs/superpowers/specs/2026-05-05-observability-resilience-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Self-Review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| Part 1: Logging foundation | Task 1 — new file + lifespan call + module logger import in app.py |
| Part 1: Module loggers in snapshot_service / sprint_service | Task 3 steps 1-2 |
| Part 2: ClickUp retry + ClickUpError | Task 2 |
| Part 2: 30s timeout + 5xx/429/network retries with backoff | Task 2 step 1 (full _get rewrite) |
| Part 2: 4xx non-429 raises ClickUpError immediately | Task 2 step 1 |
| Part 3: Per-sprint try/except in daily_snapshot_job | Task 3 step 3 (refactor + new daily_snapshot_job loop) |
| Part 3: _record_last_snapshot_run | Task 3 step 3 |
| Part 3: _should_catch_up_snapshot | Task 3 step 3 |
| Part 3: Catch-up trigger via asyncio.create_task on app.state | Task 3 step 4 |
| app_settings.last_snapshot_run | Task 3 step 7 verification |
| Edge case: first-ever boot triggers catch-up | Task 3 step 6 (the actual first-restart observation) |
| Edge case: invalid ISO in last_snapshot_run | Task 3 step 3 (`_should_catch_up_snapshot` ValueError handler) |

**Placeholder scan:** No "TBD", "TODO", "implement later", "appropriate error handling", "similar to Task N". Every step has concrete code or commands.

**Type/name consistency:**
- `configure_logging` — same name in `logging_config.py` and `app.py`
- `ClickUpError` — defined in `clickup_client.py`, no other module references it directly yet (callers can import when needed)
- `_snapshot_one_sprint`, `_record_last_snapshot_run`, `_should_catch_up_snapshot` — all in `app.py`, all referenced consistently
- `last_snapshot_run` — same key in `_record_last_snapshot_run` and `_should_catch_up_snapshot`
- `app.state.catchup_task` — only set in `lifespan`; nothing else references it (intentional — just keeping the ref alive)
