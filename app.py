import uvicorn
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import HOST, PORT, DB_PATH
from src.database import init_db
from src.routes import teams, sprints, clickup_proxy, pages
from src.routes import auth as auth_routes
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
import os
from apscheduler.schedulers.background import BackgroundScheduler
from src.config import DAILY_SNAPSHOT_TIME
from src.services.snapshot_service import detect_scope_changes, record_daily_progress
from src.clickup_client import ClickUpClient, ClickUpError, get_system_client
from src.auth.middleware import handle_clickup_error
from src.database import get_connection
from src.logging_config import configure_logging
import asyncio

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    configure_logging()
    log.info("App startup")
    init_db(DB_PATH)
    if _should_catch_up_snapshot():
        log.info("Last snapshot run was >24h ago (or never); firing catch-up job")
        # Hold task ref on app.state so Python's GC doesn't collect it mid-run.
        app.state.catchup_task = asyncio.create_task(daily_snapshot_job())
    scheduler.start()
    yield
    # shutdown
    log.info("App shutdown")
    scheduler.shutdown()


app = FastAPI(title="Sprint Reporter", lifespan=lifespan)

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

    client = get_system_client()
    log.info("Daily snapshot job using service client")
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

scheduler = BackgroundScheduler()
hour, minute = DAILY_SNAPSHOT_TIME.split(":")
scheduler.add_job(run_daily_snapshot, "cron", hour=int(hour), minute=int(minute))

app.include_router(auth_routes.router)
app.include_router(pages.router)
app.include_router(teams.router)
app.include_router(sprints.router)
app.include_router(clickup_proxy.router)


@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    """Convert auth 401s to redirects for browser navigation; JSON for AJAX."""
    if exc.status_code != 401:
        # Default behavior for non-auth errors
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    accept = request.headers.get("accept", "")
    is_json_request = "application/json" in accept and "text/html" not in accept
    if is_json_request or request.url.path.startswith("/api"):
        return JSONResponse({"detail": exc.detail}, status_code=401)
    return RedirectResponse("/auth/login", status_code=302)


@app.exception_handler(ClickUpError)
async def clickup_error_handler(request: Request, exc: ClickUpError):
    return handle_clickup_error(request, exc)


# Only mount static files if the directory exists
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
