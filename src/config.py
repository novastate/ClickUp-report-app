import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY", "")
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = os.getenv("DB_PATH", "./sprint_data.db")
DAILY_SNAPSHOT_TIME = os.getenv("DAILY_SNAPSHOT_TIME", "06:00")
