import uvicorn
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

app = FastAPI(title="Sprint Reporter")

async def daily_snapshot_job():
    from src.config import DB_PATH
    conn = get_connection(DB_PATH)
    sprints = conn.execute(
        "SELECT * FROM sprints WHERE forecast_closed_at IS NOT NULL AND closed_at IS NULL"
    ).fetchall()
    conn.close()

    client = ClickUpClient(get_clickup_api_key())
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

scheduler = BackgroundScheduler()
hour, minute = DAILY_SNAPSHOT_TIME.split(":")
scheduler.add_job(run_daily_snapshot, "cron", hour=int(hour), minute=int(minute))

app.include_router(pages.router)
app.include_router(teams.router)
app.include_router(sprints.router)
app.include_router(clickup_proxy.router)

# Only mount static files if the directory exists
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def startup():
    init_db(DB_PATH)
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
