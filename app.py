import uvicorn
from fastapi import FastAPI
from src.config import HOST, PORT

app = FastAPI(title="Sprint Reporter")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
