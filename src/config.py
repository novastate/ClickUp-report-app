import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = os.getenv("DB_PATH", "./sprint_data.db")
DAILY_SNAPSHOT_TIME = os.getenv("DAILY_SNAPSHOT_TIME", "06:00")

# OAuth
CLICKUP_OAUTH_CLIENT_ID = os.getenv("CLICKUP_OAUTH_CLIENT_ID", "")
CLICKUP_OAUTH_CLIENT_SECRET = os.getenv("CLICKUP_OAUTH_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "")

# Background job uses an impersonal "service account" API key.
# Falls back to legacy CLICKUP_API_KEY for backwards compat during rollout.
CLICKUP_SERVICE_API_KEY = os.getenv("CLICKUP_SERVICE_API_KEY", "")

# Cookie security: must be False for local HTTP dev, True everywhere else.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() != "false"


def get_service_api_key() -> str:
    """Service-account key for the daily snapshot job (impersonal cron).
    Prefers CLICKUP_SERVICE_API_KEY; falls back to legacy CLICKUP_API_KEY,
    then to DB-stored key (legacy app_settings)."""
    if CLICKUP_SERVICE_API_KEY:
        return CLICKUP_SERVICE_API_KEY
    legacy = os.getenv("CLICKUP_API_KEY", "")
    if legacy:
        return legacy
    try:
        from src.database import get_setting
        return get_setting(DB_PATH, "clickup_api_key") or ""
    except Exception:
        return ""


def get_clickup_api_key() -> str:
    """Deprecated. Kept temporarily for routes that haven't been migrated yet.
    Returns the same value as get_service_api_key()."""
    return get_service_api_key()
