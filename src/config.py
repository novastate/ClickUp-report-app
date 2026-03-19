import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = os.getenv("DB_PATH", "./sprint_data.db")
DAILY_SNAPSHOT_TIME = os.getenv("DAILY_SNAPSHOT_TIME", "06:00")

def get_clickup_api_key() -> str:
    """Get API key from .env first, then from DB settings."""
    env_key = os.getenv("CLICKUP_API_KEY", "")
    if env_key:
        return env_key
    try:
        from src.database import get_setting
        return get_setting(DB_PATH, "clickup_api_key") or ""
    except Exception:
        return ""
