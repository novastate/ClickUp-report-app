import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import HOST, PORT, DB_PATH
from src.database import init_db
from src.routes import teams, sprints, clickup_proxy, pages
import os

app = FastAPI(title="Sprint Reporter")

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

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
