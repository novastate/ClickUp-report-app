# Observability & Resilience (Initiative 1A)

## Context

The app currently has zero application-level logging — only uvicorn's access logs reach `app.log`. ClickUp API calls have no timeout configured, no retry on transient failures, no graceful degradation when the API is unavailable. The daily snapshot job loops sprints sequentially with no error isolation: a single failure (network blip, ClickUp 5xx, malformed task) stops the entire job and silently leaves remaining sprints un-snapshotted. If the app is down when the cron fires at 06:00, the day is lost permanently — no catch-up.

This initiative makes the app stable enough to run unattended on the live Mac, with traceable errors and resilience to common failures.

## Problem

Three concrete failure modes the user could hit today:

1. **Silent crashes.** Background job (`run_daily_snapshot`) raises an exception. The exception goes to stderr, gets buffered to `app.log` mixed with uvicorn's access logs, then forgotten. No alert, no aggregation, no per-module attribution.
2. **Single-error cascades.** `daily_snapshot_job` calls `client.get_list_tasks(...)` for each sprint in sequence. If sprint #3 hits a network glitch (or ClickUp returns 503), the exception propagates out of the loop and sprints #4-N never run that day. Same for `Sync from ClickUp` — one bad list breaks the whole sync.
3. **Missed days.** APScheduler fires at the configured `DAILY_SNAPSHOT_TIME` (default 06:00). If the app is down at that minute, the job never runs. Next day at 06:00 it runs again — but yesterday is lost forever.

## Goal

After this initiative:

1. Every error has a timestamp, a module, a level, and persists in `app.log` (rotated). Live tail of `app.log` shows what the app is doing in real time.
2. ClickUp API calls survive transient failures (network hiccups, 5xx, 429 rate limits) via a small bounded retry loop with exponential backoff.
3. The daily snapshot job continues processing remaining sprints after a per-sprint failure. On app startup, if more than 24h have passed since the last successful run, the job fires immediately to catch up.

## Non-Goals

- **No external observability platform** (Datadog, Sentry, etc.). Local file + stdout is enough for this single-Mac deployment.
- **No JSON-structured logs.** Plain text with consistent format. Structured logs become valuable when you have aggregation tooling — we don't, yet.
- **No retroactive multi-day snapshots.** "Catch up" means "run once if we missed today". A 3-day outage produces one snapshot, not three.
- **No metrics or dashboards.** Just logs. Metrics is a separate initiative if/when needed.
- **No alerting.** User reads logs manually. Pager-style alerting is way out of scope for now.

## Design

### Part 1: Structured logging

`src/logging_config.py` (new file) sets up a module-level logger configuration once at app startup:

```python
import logging
import logging.handlers
from pathlib import Path

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

def configure_logging(log_path: str = "app.log", level: str = "INFO"):
    """Set up root logger with rotating file + stdout handlers. Idempotent."""
    root = logging.getLogger()
    if getattr(configure_logging, "_done", False):
        return
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    # Rotating file: 5MB per file, keep 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Stdout for `tail -f` and to keep uvicorn's pipe alive
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Tame chatty libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    configure_logging._done = True
```

Called once from `app.py`'s `lifespan` startup phase, before any other module logs.

Each module that wants to log uses:

```python
import logging
log = logging.getLogger(__name__)

log.info("Captured %d tasks for sprint %s", len(tasks), sprint["id"])
log.warning("ClickUp returned 503; will retry")
log.error("Failed to close sprint %s", sprint_id, exc_info=True)
```

Modules to add logging to in this initiative (limit blast radius):

- `src/clickup_client.py` — all API calls, retries, errors
- `src/services/snapshot_service.py` — record_daily_progress entries, scope-change detections
- `src/services/sprint_service.py` — sprint state changes (close_forecast, close_sprint)
- `app.py` — daily_snapshot_job lifecycle, catch-up trigger, errors per sprint

`uvicorn` access logs continue going to stdout naturally; we don't touch them.

### Part 2: ClickUp API retry + custom error

In `src/clickup_client.py`, replace the existing `_get` with:

```python
import asyncio
import httpx
import logging

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_BASE = 1.0   # seconds; doubles each retry: 1, 2, 4

class ClickUpError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body

class ClickUpClient:
    # ... existing __init__ ...

    async def _get(self, path: str, params: dict = None) -> dict:
        url = f"{BASE_URL}{path}"
        last_exc = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    response = await client.get(url, headers=self.headers, params=params)
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
                last_exc = e
                if attempt < MAX_RETRIES:
                    delay = BACKOFF_BASE * (2 ** attempt)
                    log.warning(
                        "ClickUp %s network error (%s); retrying in %.1fs (attempt %d/%d)",
                        path, type(e).__name__, delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ClickUpError(f"Network error after {MAX_RETRIES} retries: {e}") from e
            except httpx.HTTPStatusError as e:
                # 4xx (non-429) = caller's fault; don't retry
                raise ClickUpError(
                    f"ClickUp returned {e.response.status_code} for {path}",
                    status_code=e.response.status_code,
                    body=e.response.text[:500],
                ) from e
        # exhausted retries on a retriable status
        raise ClickUpError(
            f"ClickUp {path} returned {response.status_code} after {MAX_RETRIES} retries",
            status_code=response.status_code,
            body=response.text[:500] if response is not None else None,
        )
```

All public methods (`get_workspaces`, `get_spaces`, etc.) automatically benefit because they all funnel through `_get`. `get_list_tasks` (which has its own pagination loop) calls `_get` for each page — same retry behavior applies per page.

Callers that want to handle ClickUp errors gracefully can `except ClickUpError`. Callers that don't catch it will see a logged error and a clean exception bubble up rather than a raw httpx exception.

### Part 3: Daily snapshot resilience + catch-up

Two changes in `app.py`:

**3a — Per-sprint isolation:**

```python
async def daily_snapshot_job():
    log.info("Daily snapshot job starting")
    # ... existing setup (load sprints from DB) ...

    success = 0
    failed = 0
    for sprint in sprints:
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
```

`_snapshot_one_sprint(sprint, client)` is just the body of the existing for-loop refactored into a function. No logic change inside, just isolation.

`_record_last_snapshot_run()` writes the current ISO timestamp to `app_settings.last_snapshot_run`.

**3b — Catch-up on startup:**

In `lifespan`'s startup phase (after `init_db`, before `scheduler.start()`):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(DB_PATH)
    log.info("App startup")
    if _should_catch_up_snapshot():
        log.info("Last snapshot run was >24h ago; firing catch-up job")
        asyncio.create_task(daily_snapshot_job())
    scheduler.start()
    yield
    log.info("App shutdown")
    scheduler.shutdown()
```

`_should_catch_up_snapshot()` reads `app_settings.last_snapshot_run`. Returns `True` if missing or > 24 hours old.

`asyncio.create_task` runs the job in the background — startup completes immediately, snapshot job runs concurrently. If the catch-up itself fails (e.g. ClickUp totally down), errors are logged but app keeps running.

### `app_settings` schema

Already exists (created by `init_db`). One new key:

- `last_snapshot_run` — ISO timestamp string. Set at end of every successful daily_snapshot_job run.

No DB migration needed (`app_settings` is key/value).

## Edge cases

- **First-ever boot:** `last_snapshot_run` doesn't exist → catch-up fires. That's correct: we want to populate "today" immediately.
- **Two app instances:** one is starting catch-up, the other already running. APScheduler uses in-process job state, so each instance schedules its own. Theoretically they could both fire today's job simultaneously and write duplicate `daily_progress` rows. **Acceptable for single-Mac deployment** — there is only one running instance. Multi-instance is out of scope.
- **Catch-up failure:** logged, but app continues. User reads `app.log` and decides whether to manually re-trigger.
- **`asyncio.create_task` lifetime:** task ref is dropped → Python may GC. Workaround: store reference on `app.state` so it isn't collected:
  ```python
  app.state.catchup_task = asyncio.create_task(daily_snapshot_job())
  ```
- **httpx version:** existing `requirements.txt` pins 0.27.0. The `httpx.Timeout(...)` and `httpx.NetworkError` API exists there; no new dep.

## Verification

Manual + scry-driven on the dev Mac:

1. **Logs flow** — restart app, `tail -f app.log` in a terminal. Hit a few endpoints. Verify each one produces a structured line with timestamp/level/module/message.
2. **Retry visible** — temporarily make `BASE_URL` point at a non-existent host (e.g. `https://api.clickup.invalid/...`). Trigger Sync. Verify three `WARNING` retry lines in log followed by `ERROR` final failure. Restore BASE_URL.
3. **Per-sprint isolation** — temporarily inject a `raise Exception` in `_snapshot_one_sprint` for a specific sprint id. Run the job manually. Verify other sprints still get snapshotted. Remove the injection.
4. **Catch-up** — set `app_settings.last_snapshot_run` to 48h ago via sqlite cli. Restart app. Verify `Last snapshot run was >24h ago; firing catch-up job` log line and that the job actually ran.
5. **Log rotation** — manually inflate `app.log` to >5MB (e.g. cat a big file in). Trigger another log line. Verify rotation: `app.log.1` exists.

## Files changed

| File | Action |
|---|---|
| `src/logging_config.py` | Create — `configure_logging()` |
| `src/clickup_client.py` | Modify — replace `_get`, add `ClickUpError`, add module logger |
| `src/services/snapshot_service.py` | Modify — add module logger, log key events |
| `src/services/sprint_service.py` | Modify — add module logger, log state transitions |
| `app.py` | Modify — call `configure_logging()` in lifespan, refactor `daily_snapshot_job`, add catch-up trigger, add `_should_catch_up_snapshot()` and `_record_last_snapshot_run()` helpers |

No new dependencies. No DB migration.

## Distribution

Standard deploy bundle. `app.log` on live Mac will start populating immediately after deploy. The catch-up logic fires on first restart after deploy if `last_snapshot_run` happens to be old (likely on first deploy since the key won't exist yet).
