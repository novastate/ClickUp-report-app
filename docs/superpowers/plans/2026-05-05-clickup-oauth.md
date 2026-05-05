# ClickUp OAuth Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ClickUp OAuth login so each user signs in with their own ClickUp account, sees data scoped to a workspace they pick, and the daily snapshot job keeps running on a separate impersonal service key.

**Architecture:** A new `src/auth/` package owns OAuth + sessions + encryption + middleware. Auth routes live in `src/routes/auth.py`. A FastAPI dependency (`get_current_user`) protects existing routes and exposes `request.state.user_client` (a `ClickUpClient` built with the signed-in user's OAuth token). The background snapshot job keeps using `get_system_client()` which reads `CLICKUP_SERVICE_API_KEY` from `.env`. Sessions are server-side rows; the cookie holds an opaque random `session_id`. Tokens are encrypted at rest with Fernet.

**Tech Stack:** FastAPI, Jinja2, SQLite (existing), httpx (existing), `cryptography` (new dep, Fernet), `python-multipart` (existing — for form parsing).

**Spec reference:** `docs/superpowers/specs/2026-05-05-clickup-oauth-design.md`

---

## File structure (decisions locked here)

| File | Responsibility |
|---|---|
| `src/auth/__init__.py` | Empty package marker |
| `src/auth/encryption.py` | Fernet wrapper: `encrypt_token(s)` / `decrypt_token(s)` reading key from env |
| `src/auth/oauth.py` | ClickUp OAuth: build authorize URL, exchange code, fetch user, fetch workspaces |
| `src/auth/users.py` | DB ops on `users` and `user_tokens` tables |
| `src/auth/sessions.py` | DB ops on `sessions` table + cookie helpers |
| `src/auth/state.py` | DB ops on `oauth_state` table (state + cleanup) |
| `src/auth/middleware.py` | `get_current_user` FastAPI dependency, 401-to-redirect handler |
| `src/routes/auth.py` | Routes: `/auth/login`, `/auth/callback`, `/auth/workspace`, `/auth/logout` |
| `src/clickup_client.py` | **Modified** — add `get_system_client()` and `get_user_client(token)` factories |
| `src/database.py` | **Modified** — new tables and `teams.workspace_id` column |
| `src/config.py` | **Modified** — read OAuth env vars + service key + cookie flag |
| `app.py` | **Modified** — register auth router, install middleware, register 401 handler |
| `src/routes/pages.py` | **Modified** — use `request.state.user_client`, filter by workspace |
| `src/routes/teams.py` | **Modified** — use `request.state.user_client`, scope create/sync to workspace |
| `src/routes/sprints.py` | **Modified** — use `request.state.user_client` |
| `templates/auth/login.html` | Landing page with "Sign in with ClickUp" |
| `templates/auth/workspace.html` | Workspace picker (only when user has >1) |
| `templates/auth/error.html` | OAuth denial / state mismatch errors |
| `templates/base.html` | **Modified** — user identity in header, logout button, workspace switcher |
| `requirements.txt` | **Modified** — add `cryptography>=42` |
| `.env.example` | **Modified** — document new vars |

**Tests directory** mirrors source layout:
- `tests/test_auth_encryption.py`
- `tests/test_auth_oauth.py`
- `tests/test_auth_users.py`
- `tests/test_auth_sessions.py`
- `tests/test_auth_state.py`
- `tests/test_auth_middleware.py`
- `tests/test_auth_routes.py`

---

## Notes for the implementer

**ClickUp OAuth wire format (verified from developer.clickup.com):**
- Authorize URL: `https://app.clickup.com/api?client_id={id}&redirect_uri={uri}&state={state}`
- Token exchange: `POST https://api.clickup.com/api/v2/oauth/token` with form/query params `client_id`, `client_secret`, `code`. Returns `{"access_token": "..."}`.
- All API calls send `Authorization: <token>` header (no `Bearer` prefix). API keys (`pk_xxx`) and OAuth tokens both fit this format.
- Tokens currently don't expire (no `refresh_token` flow).

**PKCE NOT included.** ClickUp's OAuth implementation does not document PKCE support, and we have a confidential server-side client (`client_secret` is safe). The `state` parameter alone is sufficient CSRF protection. If ClickUp adds PKCE later, it's a small additive change.

**Datetimes:** Use `datetime.utcnow().isoformat()` everywhere — matches existing app code (e.g. `_record_last_snapshot_run`).

**TDD note:** Use `pytest`'s `monkeypatch` for env vars. Use `httpx.MockTransport` or `unittest.mock.patch("httpx.AsyncClient.post")` for ClickUp API mocking — same pattern as existing `tests/test_clickup_client.py`.

**Commit style:** Existing repo uses Conventional Commits with `feat:`, `fix:`, `refactor:`. Keep that.

---

### Task 1: DB schema — new tables + `teams.workspace_id`

**Files:**
- Modify: `src/database.py`
- Test: `tests/test_auth_database.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_database.py`:

```python
from src.database import init_db, get_connection


def test_init_db_creates_users_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    conn.close()
    assert cols == {"id", "email", "username", "color", "profile_picture",
                    "created_at", "updated_at"}


def test_init_db_creates_user_tokens_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_tokens)").fetchall()}
    conn.close()
    assert cols == {"user_id", "encrypted_access_token", "scopes", "granted_at"}


def test_init_db_creates_sessions_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    conn.close()
    assert cols == {"session_id", "user_id", "active_workspace_id",
                    "created_at", "expires_at", "last_seen"}


def test_init_db_creates_oauth_state_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(oauth_state)").fetchall()}
    conn.close()
    assert cols == {"state", "created_at"}


def test_init_db_adds_workspace_id_to_teams(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(teams)").fetchall()}
    conn.close()
    assert "workspace_id" in cols


def test_init_db_is_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    init_db(db)  # must not raise
    conn = get_connection(db)
    n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    conn.close()
    assert n == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_database.py -v`
Expected: FAIL — tables don't exist.

- [ ] **Step 3: Add tables to `init_db` in `src/database.py`**

Add inside the `executescript("""...""")` block (alongside existing `CREATE TABLE`s):

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    username TEXT,
    color TEXT,
    profile_picture TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_tokens (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    encrypted_access_token TEXT NOT NULL,
    scopes TEXT,
    granted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    active_workspace_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS oauth_state (
    state TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
```

Add **after** the existing `executescript` block, in the migrations section (alongside the existing `try/except ALTER TABLE` blocks):

```python
try:
    conn.execute("ALTER TABLE teams ADD COLUMN workspace_id TEXT")
except Exception:
    pass  # Column already exists
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_auth_database.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/database.py tests/test_auth_database.py
git commit -m "feat(auth): add users/sessions/tokens/oauth_state tables + teams.workspace_id"
```

---

### Task 2: Encryption module (Fernet wrapper)

**Files:**
- Create: `src/auth/__init__.py`
- Create: `src/auth/encryption.py`
- Test: `tests/test_auth_encryption.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add `cryptography` to requirements.txt**

Append to `requirements.txt`:

```
cryptography>=42.0.0
```

Install: `./.venv/bin/pip install -r requirements.txt`

- [ ] **Step 2: Create `src/auth/__init__.py`**

```python
"""Authentication and session management."""
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_auth_encryption.py`:

```python
import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def fixed_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", key)
    # Force module re-import so it picks up the new env var
    import importlib
    import src.auth.encryption as mod
    importlib.reload(mod)
    return mod


def test_roundtrip(fixed_key):
    plaintext = "pk_1234567890_OAUTHTOKEN"
    encrypted = fixed_key.encrypt_token(plaintext)
    assert encrypted != plaintext
    assert fixed_key.decrypt_token(encrypted) == plaintext


def test_different_ciphertexts_each_call(fixed_key):
    """Fernet uses random IV → encrypting same plaintext twice yields different ciphertext."""
    a = fixed_key.encrypt_token("same")
    b = fixed_key.encrypt_token("same")
    assert a != b
    assert fixed_key.decrypt_token(a) == "same"
    assert fixed_key.decrypt_token(b) == "same"


def test_decrypt_with_wrong_key_raises(monkeypatch):
    import importlib
    import src.auth.encryption as mod
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    importlib.reload(mod)
    encrypted = mod.encrypt_token("secret")

    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    importlib.reload(mod)
    with pytest.raises(Exception):  # cryptography.fernet.InvalidToken
        mod.decrypt_token(encrypted)


def test_missing_env_var_raises_at_import(monkeypatch):
    import importlib
    import src.auth.encryption as mod
    monkeypatch.delenv("SESSION_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_ENCRYPTION_KEY"):
        importlib.reload(mod)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_auth_encryption.py -v`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 5: Implement `src/auth/encryption.py`**

```python
"""Fernet-based symmetric encryption for OAuth tokens stored in the DB.

The master key is read from SESSION_ENCRYPTION_KEY env var at import time.
If the key is rotated, all existing tokens become unreadable and users
must re-login. Generate a key with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from cryptography.fernet import Fernet

_key = os.environ.get("SESSION_ENCRYPTION_KEY")
if not _key:
    raise RuntimeError(
        "SESSION_ENCRYPTION_KEY env var is required. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

_fernet = Fernet(_key.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 6: Run test to verify pass**

Run: `pytest tests/test_auth_encryption.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/auth/__init__.py src/auth/encryption.py tests/test_auth_encryption.py
git commit -m "feat(auth): Fernet-based token encryption module"
```

---

### Task 3: Config — new env vars

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import src.config as mod
    importlib.reload(mod)
    return mod


def test_oauth_env_vars_loaded(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        CLICKUP_OAUTH_CLIENT_ID="abc",
        CLICKUP_OAUTH_CLIENT_SECRET="def",
        OAUTH_REDIRECT_URI="http://localhost:8000/auth/callback",
        CLICKUP_SERVICE_API_KEY="pk_service_xyz",
    )
    assert cfg.CLICKUP_OAUTH_CLIENT_ID == "abc"
    assert cfg.CLICKUP_OAUTH_CLIENT_SECRET == "def"
    assert cfg.OAUTH_REDIRECT_URI == "http://localhost:8000/auth/callback"
    assert cfg.CLICKUP_SERVICE_API_KEY == "pk_service_xyz"


def test_cookie_secure_default_true(monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.COOKIE_SECURE is True


def test_cookie_secure_can_be_disabled(monkeypatch):
    cfg = _reload_config(monkeypatch, COOKIE_SECURE="false")
    assert cfg.COOKIE_SECURE is False


def test_get_service_api_key_prefers_new_var(monkeypatch):
    monkeypatch.setenv("CLICKUP_SERVICE_API_KEY", "pk_new")
    monkeypatch.setenv("CLICKUP_API_KEY", "pk_old")
    import src.config as mod
    importlib.reload(mod)
    assert mod.get_service_api_key() == "pk_new"


def test_get_service_api_key_falls_back_to_legacy(monkeypatch):
    monkeypatch.delenv("CLICKUP_SERVICE_API_KEY", raising=False)
    monkeypatch.setenv("CLICKUP_API_KEY", "pk_legacy")
    import src.config as mod
    importlib.reload(mod)
    assert mod.get_service_api_key() == "pk_legacy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — new attributes/functions missing.

- [ ] **Step 3: Update `src/config.py`**

Replace contents with:

```python
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(auth): add OAuth + service key + cookie env vars to config"
```

---

### Task 4: Users + tokens DB module

**Files:**
- Create: `src/auth/users.py`
- Test: `tests/test_auth_users.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_users.py`:

```python
import os
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib
    import src.config as cfg_mod
    importlib.reload(cfg_mod)
    import src.auth.encryption as enc_mod
    importlib.reload(enc_mod)
    import src.auth.users as users_mod
    importlib.reload(users_mod)
    from src.database import init_db
    init_db(db)
    yield


def test_upsert_creates_new_user():
    from src.auth.users import upsert_user, get_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color="#ff0000", profile_picture="http://i/a")
    u = get_user("u1")
    assert u["id"] == "u1"
    assert u["email"] == "a@x.se"
    assert u["username"] == "anna"


def test_upsert_updates_existing_user():
    from src.auth.users import upsert_user, get_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color="#ff0000", profile_picture=None)
    upsert_user(id="u1", email="a@x.se", username="anna2",
                color="#00ff00", profile_picture="http://i/a2")
    u = get_user("u1")
    assert u["username"] == "anna2"
    assert u["color"] == "#00ff00"


def test_get_user_returns_none_when_missing():
    from src.auth.users import get_user
    assert get_user("nope") is None


def test_save_and_get_token_roundtrip():
    from src.auth.users import upsert_user, save_user_token, get_user_token
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz_123", scopes="read")
    assert get_user_token("u1") == "oauth_xyz_123"


def test_save_token_replaces_existing():
    from src.auth.users import upsert_user, save_user_token, get_user_token
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="first", scopes=None)
    save_user_token(user_id="u1", access_token="second", scopes=None)
    assert get_user_token("u1") == "second"


def test_token_is_encrypted_in_db():
    """Verify the raw DB row holds ciphertext, not plaintext."""
    from src.auth.users import upsert_user, save_user_token
    from src.database import get_connection
    from src.config import DB_PATH
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="plain_token_value", scopes=None)
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT encrypted_access_token FROM user_tokens WHERE user_id = 'u1'").fetchone()
    conn.close()
    assert row["encrypted_access_token"] != "plain_token_value"
    assert row["encrypted_access_token"].startswith("gAAAAA")  # Fernet ciphertext prefix


def test_delete_user_token_removes_row():
    from src.auth.users import upsert_user, save_user_token, get_user_token, delete_user_token
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="t", scopes=None)
    delete_user_token("u1")
    assert get_user_token("u1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_users.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/auth/users.py`**

```python
"""DB ops for users and their encrypted OAuth tokens."""
from datetime import datetime
from src.config import DB_PATH
from src.database import get_connection
from src.auth.encryption import encrypt_token, decrypt_token


def _now() -> str:
    return datetime.utcnow().isoformat()


def upsert_user(id: str, email: str, username: str | None,
                color: str | None, profile_picture: str | None) -> None:
    conn = get_connection(DB_PATH)
    now = _now()
    conn.execute(
        """
        INSERT INTO users (id, email, username, color, profile_picture, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            email = excluded.email,
            username = excluded.username,
            color = excluded.color,
            profile_picture = excluded.profile_picture,
            updated_at = excluded.updated_at
        """,
        (id, email, username, color, profile_picture, now, now),
    )
    conn.commit()
    conn.close()


def get_user(user_id: str) -> dict | None:
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_user_token(user_id: str, access_token: str, scopes: str | None) -> None:
    conn = get_connection(DB_PATH)
    conn.execute(
        """
        INSERT INTO user_tokens (user_id, encrypted_access_token, scopes, granted_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            encrypted_access_token = excluded.encrypted_access_token,
            scopes = excluded.scopes,
            granted_at = excluded.granted_at
        """,
        (user_id, encrypt_token(access_token), scopes, _now()),
    )
    conn.commit()
    conn.close()


def get_user_token(user_id: str) -> str | None:
    """Return decrypted access token, or None if not found."""
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT encrypted_access_token FROM user_tokens WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return decrypt_token(row["encrypted_access_token"])


def delete_user_token(user_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM user_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_auth_users.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/auth/users.py tests/test_auth_users.py
git commit -m "feat(auth): users + encrypted user_tokens DB module"
```

---

### Task 5: Sessions DB module

**Files:**
- Create: `src/auth/sessions.py`
- Test: `tests/test_auth_sessions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_sessions.py`:

```python
import pytest
from datetime import datetime, timedelta
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, src.config, src.auth.encryption, src.auth.sessions, src.auth.users
    importlib.reload(src.config)
    importlib.reload(src.auth.encryption)
    importlib.reload(src.auth.users)
    importlib.reload(src.auth.sessions)
    from src.database import init_db
    init_db(db)
    from src.auth.users import upsert_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    yield


def test_create_session_returns_id_and_persists():
    from src.auth.sessions import create_session, get_session
    sid = create_session(user_id="u1", active_workspace_id="ws_42")
    assert sid and len(sid) >= 32
    s = get_session(sid)
    assert s["user_id"] == "u1"
    assert s["active_workspace_id"] == "ws_42"


def test_get_session_returns_none_for_unknown():
    from src.auth.sessions import get_session
    assert get_session("nope") is None


def test_get_session_returns_none_for_expired():
    from src.auth.sessions import create_session, get_session
    from src.database import get_connection
    from src.config import DB_PATH
    sid = create_session(user_id="u1", active_workspace_id=None)
    conn = get_connection(DB_PATH)
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (past, sid))
    conn.commit()
    conn.close()
    assert get_session(sid) is None


def test_roll_session_extends_expiry():
    from src.auth.sessions import create_session, roll_session, get_session
    from src.database import get_connection
    from src.config import DB_PATH
    sid = create_session(user_id="u1", active_workspace_id=None)
    # Squash expiry
    conn = get_connection(DB_PATH)
    near = (datetime.utcnow() + timedelta(minutes=1)).isoformat()
    conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (near, sid))
    conn.commit()
    conn.close()

    roll_session(sid)
    s = get_session(sid)
    new_exp = datetime.fromisoformat(s["expires_at"])
    assert new_exp > datetime.utcnow() + timedelta(days=29)


def test_set_active_workspace():
    from src.auth.sessions import create_session, set_active_workspace, get_session
    sid = create_session(user_id="u1", active_workspace_id=None)
    set_active_workspace(sid, "ws_99")
    assert get_session(sid)["active_workspace_id"] == "ws_99"


def test_delete_session():
    from src.auth.sessions import create_session, delete_session, get_session
    sid = create_session(user_id="u1", active_workspace_id=None)
    delete_session(sid)
    assert get_session(sid) is None


def test_delete_sessions_for_user_clears_all():
    from src.auth.sessions import create_session, delete_sessions_for_user, get_session
    sid_a = create_session(user_id="u1", active_workspace_id=None)
    sid_b = create_session(user_id="u1", active_workspace_id=None)
    delete_sessions_for_user("u1")
    assert get_session(sid_a) is None
    assert get_session(sid_b) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_sessions.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/auth/sessions.py`**

```python
"""DB-backed sessions. Cookie holds opaque session_id; everything else is server-side."""
import secrets
from datetime import datetime, timedelta
from src.config import DB_PATH
from src.database import get_connection

SESSION_LIFETIME = timedelta(days=30)


def _now() -> datetime:
    return datetime.utcnow()


def _new_id() -> str:
    return secrets.token_hex(32)  # 64-char hex


def create_session(user_id: str, active_workspace_id: str | None) -> str:
    sid = _new_id()
    now = _now()
    expires = now + SESSION_LIFETIME
    conn = get_connection(DB_PATH)
    conn.execute(
        """
        INSERT INTO sessions (session_id, user_id, active_workspace_id,
                              created_at, expires_at, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (sid, user_id, active_workspace_id, now.isoformat(),
         expires.isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()
    return sid


def get_session(session_id: str) -> dict | None:
    """Return session dict if it exists and hasn't expired."""
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT * FROM sessions WHERE session_id = ? AND expires_at > ?",
        (session_id, _now().isoformat()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def roll_session(session_id: str) -> None:
    """Update expires_at to now+30d and last_seen to now. Idempotent on missing row."""
    now = _now()
    expires = now + SESSION_LIFETIME
    conn = get_connection(DB_PATH)
    conn.execute(
        "UPDATE sessions SET expires_at = ?, last_seen = ? WHERE session_id = ?",
        (expires.isoformat(), now.isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def set_active_workspace(session_id: str, workspace_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute(
        "UPDATE sessions SET active_workspace_id = ? WHERE session_id = ?",
        (workspace_id, session_id),
    )
    conn.commit()
    conn.close()


def delete_session(session_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def delete_sessions_for_user(user_id: str) -> None:
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_auth_sessions.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/auth/sessions.py tests/test_auth_sessions.py
git commit -m "feat(auth): server-side sessions module with rolling expiry"
```

---

### Task 6: OAuth state DB module

**Files:**
- Create: `src/auth/state.py`
- Test: `tests/test_auth_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_state.py`:

```python
import pytest
from datetime import datetime, timedelta
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, src.config, src.auth.state
    importlib.reload(src.config)
    importlib.reload(src.auth.state)
    from src.database import init_db
    init_db(db)
    yield


def test_create_state_returns_random_string():
    from src.auth.state import create_state
    a = create_state()
    b = create_state()
    assert a != b
    assert len(a) >= 32


def test_consume_state_returns_true_for_valid():
    from src.auth.state import create_state, consume_state
    s = create_state()
    assert consume_state(s) is True


def test_consume_state_is_one_shot():
    """consume_state returns True the first time, False on the second call."""
    from src.auth.state import create_state, consume_state
    s = create_state()
    assert consume_state(s) is True
    assert consume_state(s) is False


def test_consume_unknown_state_returns_false():
    from src.auth.state import consume_state
    assert consume_state("never_existed") is False


def test_consume_expired_state_returns_false():
    from src.auth.state import create_state, consume_state
    from src.database import get_connection
    from src.config import DB_PATH
    s = create_state()
    old = (datetime.utcnow() - timedelta(minutes=11)).isoformat()
    conn = get_connection(DB_PATH)
    conn.execute("UPDATE oauth_state SET created_at = ? WHERE state = ?", (old, s))
    conn.commit()
    conn.close()
    assert consume_state(s) is False


def test_cleanup_old_states_removes_expired_only():
    from src.auth.state import create_state, cleanup_old_states
    from src.database import get_connection
    from src.config import DB_PATH
    fresh = create_state()
    stale = create_state()
    conn = get_connection(DB_PATH)
    old = (datetime.utcnow() - timedelta(minutes=11)).isoformat()
    conn.execute("UPDATE oauth_state SET created_at = ? WHERE state = ?", (old, stale))
    conn.commit()
    conn.close()
    cleanup_old_states()
    conn = get_connection(DB_PATH)
    rows = {r["state"] for r in conn.execute("SELECT state FROM oauth_state").fetchall()}
    conn.close()
    assert fresh in rows
    assert stale not in rows
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_state.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/auth/state.py`**

```python
"""Short-lived `state` parameters for OAuth CSRF protection.

A row exists for ~10 minutes between /auth/login (create) and /auth/callback
(consume). Stale rows are cleaned on every create."""
import secrets
from datetime import datetime, timedelta
from src.config import DB_PATH
from src.database import get_connection

STATE_TTL = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.utcnow()


def create_state() -> str:
    """Generate a random state, store with timestamp, return it.
    Also opportunistically cleans up old states."""
    cleanup_old_states()
    state = secrets.token_hex(32)
    conn = get_connection(DB_PATH)
    conn.execute(
        "INSERT INTO oauth_state (state, created_at) VALUES (?, ?)",
        (state, _now().isoformat()),
    )
    conn.commit()
    conn.close()
    return state


def consume_state(state: str) -> bool:
    """Look up state. If found and within TTL: delete and return True.
    If missing or expired: return False (don't delete to keep evidence)."""
    cutoff = (_now() - STATE_TTL).isoformat()
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT state FROM oauth_state WHERE state = ? AND created_at > ?",
        (state, cutoff),
    ).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("DELETE FROM oauth_state WHERE state = ?", (state,))
    conn.commit()
    conn.close()
    return True


def cleanup_old_states() -> None:
    cutoff = (_now() - STATE_TTL).isoformat()
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM oauth_state WHERE created_at <= ?", (cutoff,))
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_auth_state.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/auth/state.py tests/test_auth_state.py
git commit -m "feat(auth): oauth_state CSRF protection module"
```

---

### Task 7: ClickUp OAuth client

**Files:**
- Create: `src/auth/oauth.py`
- Test: `tests/test_auth_oauth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_oauth.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse, parse_qs


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_ID", "client_abc")
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_SECRET", "secret_def")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY",
                       "Lp4XU3p1LpC8e2iEmHjJqQqFvXW8eJMcS6P-5nJyqNg=")
    import importlib, src.config, src.auth.oauth
    importlib.reload(src.config)
    importlib.reload(src.auth.oauth)


def test_build_authorize_url_contains_required_params():
    from src.auth.oauth import build_authorize_url
    url = build_authorize_url(state="state_xyz")
    parsed = urlparse(url)
    assert parsed.netloc == "app.clickup.com"
    assert parsed.path == "/api"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["client_abc"]
    assert qs["redirect_uri"] == ["http://localhost:8000/auth/callback"]
    assert qs["state"] == ["state_xyz"]


@pytest.mark.asyncio
async def test_exchange_code_returns_access_token():
    from src.auth.oauth import exchange_code
    mock_response = AsyncMock()
    mock_response.json.return_value = {"access_token": "oauth_token_xyz"}
    mock_response.raise_for_status = lambda: None
    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        token = await exchange_code("the_code")
        assert token == "oauth_token_xyz"
        # verify call was made with correct params
        call = mock_post.call_args
        assert "oauth/token" in call.args[0]
        sent_params = call.kwargs.get("params") or call.kwargs.get("data") or {}
        assert sent_params["client_id"] == "client_abc"
        assert sent_params["client_secret"] == "secret_def"
        assert sent_params["code"] == "the_code"


@pytest.mark.asyncio
async def test_exchange_code_raises_on_error():
    from src.auth.oauth import exchange_code
    import httpx
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: (_ for _ in ()).throw(
        httpx.HTTPStatusError("bad", request=None, response=httpx.Response(401))
    )
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(Exception):
            await exchange_code("bad_code")


@pytest.mark.asyncio
async def test_fetch_user_returns_user_data():
    from src.auth.oauth import fetch_user
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "user": {
            "id": 12345,
            "email": "a@x.se",
            "username": "anna",
            "color": "#ff0000",
            "profile_picture": "http://i/a",
        }
    }
    mock_response.raise_for_status = lambda: None
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        u = await fetch_user("token_xyz")
        assert u["id"] == "12345"  # coerced to string
        assert u["email"] == "a@x.se"
        assert u["username"] == "anna"


@pytest.mark.asyncio
async def test_fetch_workspaces_returns_list():
    from src.auth.oauth import fetch_workspaces
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        "teams": [
            {"id": "ws1", "name": "Acme Co", "color": "#000"},
            {"id": "ws2", "name": "Side Project", "color": "#fff"},
        ]
    }
    mock_response.raise_for_status = lambda: None
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        ws = await fetch_workspaces("token_xyz")
        assert len(ws) == 2
        assert ws[0]["id"] == "ws1"
        assert ws[0]["name"] == "Acme Co"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_oauth.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/auth/oauth.py`**

```python
"""ClickUp OAuth client. Pure functions — no DB access here."""
import logging
from urllib.parse import urlencode
import httpx
from src.config import (
    CLICKUP_OAUTH_CLIENT_ID,
    CLICKUP_OAUTH_CLIENT_SECRET,
    OAUTH_REDIRECT_URI,
)

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://app.clickup.com/api"
TOKEN_URL = "https://api.clickup.com/api/v2/oauth/token"
API_BASE = "https://api.clickup.com/api/v2"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def build_authorize_url(state: str) -> str:
    """Return URL to redirect the user to for ClickUp authorization."""
    params = {
        "client_id": CLICKUP_OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Exchange the OAuth `code` for an access token. Returns the token string.
    Raises on non-2xx response."""
    params = {
        "client_id": CLICKUP_OAUTH_CLIENT_ID,
        "client_secret": CLICKUP_OAUTH_CLIENT_SECRET,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(TOKEN_URL, params=params)
    response.raise_for_status()
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"ClickUp /oauth/token response missing access_token: {data}")
    log.info("OAuth code exchange succeeded")
    return token


async def fetch_user(access_token: str) -> dict:
    """Get the authenticated user's profile.
    Returns: {"id": str, "email": str, "username": str, "color": str, "profile_picture": str}"""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{API_BASE}/user",
            headers={"Authorization": access_token},
        )
    response.raise_for_status()
    u = response.json().get("user", {})
    return {
        "id": str(u.get("id")),
        "email": u.get("email", ""),
        "username": u.get("username"),
        "color": u.get("color"),
        "profile_picture": u.get("profile_picture"),
    }


async def fetch_workspaces(access_token: str) -> list[dict]:
    """List the workspaces the authenticated user belongs to.
    ClickUp calls them 'teams' in the API but the UI calls them 'Workspaces'."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{API_BASE}/team",
            headers={"Authorization": access_token},
        )
    response.raise_for_status()
    return response.json().get("teams", [])
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_auth_oauth.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/auth/oauth.py tests/test_auth_oauth.py
git commit -m "feat(auth): ClickUp OAuth client (authorize URL, code exchange, user, workspaces)"
```

---

### Task 8: ClickUp client factory refactor

**Files:**
- Modify: `src/clickup_client.py`
- Test: `tests/test_clickup_client.py`

- [ ] **Step 1: Add tests for the new factory functions**

Append to `tests/test_clickup_client.py`:

```python
def test_get_system_client_uses_service_key(monkeypatch):
    monkeypatch.setenv("CLICKUP_SERVICE_API_KEY", "pk_service_key")
    monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
    import importlib
    import src.config as cfg
    import src.clickup_client as cu
    importlib.reload(cfg)
    importlib.reload(cu)
    client = cu.get_system_client()
    assert client.headers["Authorization"] == "pk_service_key"


def test_get_user_client_uses_passed_token():
    from src.clickup_client import get_user_client
    client = get_user_client("oauth_token_abc")
    assert client.headers["Authorization"] == "oauth_token_abc"
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest tests/test_clickup_client.py -v`
Expected: 2 new tests FAIL — factories don't exist yet.

- [ ] **Step 3: Add factories to `src/clickup_client.py`**

Append to the file (after the `ClickUpClient` class):

```python
def get_system_client() -> ClickUpClient:
    """Build a client for the impersonal background-job 'service account'.
    Reads CLICKUP_SERVICE_API_KEY (with legacy fallback to CLICKUP_API_KEY)."""
    from src.config import get_service_api_key
    return ClickUpClient(api_key=get_service_api_key())


def get_user_client(access_token: str) -> ClickUpClient:
    """Build a client for an authenticated user's request, using their OAuth token.
    The Authorization header format is identical to API keys for ClickUp."""
    return ClickUpClient(api_key=access_token)
```

- [ ] **Step 4: Run all clickup_client tests to verify pass**

Run: `pytest tests/test_clickup_client.py -v`
Expected: all 6 tests PASS (4 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/clickup_client.py tests/test_clickup_client.py
git commit -m "feat(auth): split ClickUp client into get_system_client / get_user_client factories"
```

---

### Task 9: Auth middleware

**Files:**
- Create: `src/auth/middleware.py`
- Test: `tests/test_auth_middleware.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_middleware.py`:

```python
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_ID", "x")
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_SECRET", "y")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://x/cb")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    import importlib, src.config, src.auth.encryption, src.auth.users, src.auth.sessions, src.auth.middleware
    importlib.reload(src.config)
    importlib.reload(src.auth.encryption)
    importlib.reload(src.auth.users)
    importlib.reload(src.auth.sessions)
    importlib.reload(src.auth.middleware)
    from src.database import init_db
    init_db(str(tmp_path / "test.db"))
    from src.auth.users import upsert_user, save_user_token
    from src.auth.middleware import get_current_user
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz", scopes=None)

    app = FastAPI()

    @app.get("/protected")
    def protected(user=Depends(get_current_user)):
        return {"user_id": user["id"], "username": user["username"]}

    return app


def test_no_cookie_returns_401(app):
    client = TestClient(app)
    r = client.get("/protected")
    assert r.status_code == 401


def test_invalid_cookie_returns_401(app):
    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", "totally_fake")
    r = client.get("/protected")
    assert r.status_code == 401


def test_valid_session_returns_user(app):
    from src.auth.sessions import create_session
    sid = create_session(user_id="u1", active_workspace_id="ws_1")
    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    r = client.get("/protected")
    assert r.status_code == 200
    assert r.json() == {"user_id": "u1", "username": "anna"}


def test_valid_session_rolls_expiry(app):
    from src.auth.sessions import create_session, get_session
    from src.database import get_connection
    from src.config import DB_PATH
    from datetime import datetime, timedelta
    sid = create_session(user_id="u1", active_workspace_id="ws_1")
    # Squash expiry to 1 hour from now
    near = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    conn = get_connection(DB_PATH)
    conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (near, sid))
    conn.commit()
    conn.close()

    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    client.get("/protected")

    s = get_session(sid)
    new_exp = datetime.fromisoformat(s["expires_at"])
    assert new_exp > datetime.utcnow() + timedelta(days=29)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_middleware.py -v`
Expected: FAIL — middleware doesn't exist.

- [ ] **Step 3: Implement `src/auth/middleware.py`**

```python
"""FastAPI dependency for auth-required routes.

Usage:
    from src.auth.middleware import get_current_user

    @router.get("/something")
    def handler(request: Request, user = Depends(get_current_user)):
        client = request.state.user_client  # ClickUpClient with user's token
        ...
"""
import logging
from fastapi import Request, HTTPException
from src.auth.sessions import get_session, roll_session
from src.auth.users import get_user, get_user_token
from src.clickup_client import get_user_client

log = logging.getLogger(__name__)
COOKIE_NAME = "sprint_reporter_session"


def get_current_user(request: Request) -> dict:
    """Look up the session cookie, validate it, populate request.state.

    On success, sets:
      request.state.user                  — dict from users table
      request.state.session_id            — the session_id
      request.state.active_workspace_id   — selected workspace, may be None
      request.state.user_client           — ClickUpClient with the user's OAuth token

    Raises HTTPException(401) on missing/expired/broken session.
    """
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="not_authenticated")

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="session_expired")

    user = get_user(session["user_id"])
    if not user:
        log.warning("Session %s references missing user %s", session_id, session["user_id"])
        raise HTTPException(status_code=401, detail="user_missing")

    token = get_user_token(user["id"])
    if not token:
        log.warning("User %s has session but no token (revoked?)", user["id"])
        raise HTTPException(status_code=401, detail="token_missing")

    # Roll expiry on every authenticated request
    roll_session(session_id)

    request.state.user = user
    request.state.session_id = session_id
    request.state.active_workspace_id = session.get("active_workspace_id")
    request.state.user_client = get_user_client(token)
    return user
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_auth_middleware.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/auth/middleware.py tests/test_auth_middleware.py
git commit -m "feat(auth): get_current_user FastAPI dependency with rolling sessions"
```

---

### Task 10: Auth routes — `/auth/login`

**Files:**
- Create: `src/routes/auth.py`
- Test: `tests/test_auth_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_routes.py`:

```python
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_ID", "client_abc")
    monkeypatch.setenv("CLICKUP_OAUTH_CLIENT_SECRET", "secret_def")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    import importlib, src.config, src.auth.encryption, src.auth.oauth
    import src.auth.users, src.auth.sessions, src.auth.state, src.auth.middleware
    import src.routes.auth
    for m in (src.config, src.auth.encryption, src.auth.oauth,
              src.auth.users, src.auth.sessions, src.auth.state,
              src.auth.middleware, src.routes.auth):
        importlib.reload(m)
    from src.database import init_db
    init_db(str(tmp_path / "test.db"))
    from fastapi.templating import Jinja2Templates
    app = FastAPI()
    app.include_router(src.routes.auth.router)
    return app


def test_login_redirects_to_clickup(app):
    client = TestClient(app)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 307 or r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("https://app.clickup.com/api?")
    assert "client_id=client_abc" in location
    assert "redirect_uri=" in location
    assert "state=" in location


def test_login_persists_state_to_db(app):
    from src.database import get_connection
    from src.config import DB_PATH
    client = TestClient(app)
    r = client.get("/auth/login", follow_redirects=False)
    location = r.headers["location"]
    # Extract the state param from the redirect
    from urllib.parse import urlparse, parse_qs
    state = parse_qs(urlparse(location).query)["state"][0]
    conn = get_connection(DB_PATH)
    row = conn.execute("SELECT * FROM oauth_state WHERE state = ?", (state,)).fetchone()
    conn.close()
    assert row is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_routes.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `src/routes/auth.py` with /auth/login**

```python
"""Auth routes: login, callback, workspace picker, logout."""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from src.auth.oauth import build_authorize_url
from src.auth.state import create_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("/login")
def login(request: Request):
    """Redirect to ClickUp's authorization page with a fresh state."""
    state = create_state()
    url = build_authorize_url(state=state)
    log.info("Redirecting to ClickUp authorize")
    return RedirectResponse(url, status_code=302)
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_auth_routes.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/routes/auth.py tests/test_auth_routes.py
git commit -m "feat(auth): /auth/login redirect to ClickUp authorize URL"
```

---

### Task 11: Auth route — `/auth/callback`

**Files:**
- Modify: `src/routes/auth.py`
- Modify: `tests/test_auth_routes.py`

- [ ] **Step 1: Append failing tests to `tests/test_auth_routes.py`**

```python
from unittest.mock import AsyncMock, patch


def test_callback_rejects_invalid_state(app):
    client = TestClient(app)
    r = client.get("/auth/callback?code=abc&state=fake_state", follow_redirects=False)
    assert r.status_code == 400


def test_callback_rejects_missing_code(app):
    from src.auth.state import create_state
    state = create_state()
    client = TestClient(app)
    r = client.get(f"/auth/callback?state={state}", follow_redirects=False)
    assert r.status_code == 400


def test_callback_handles_oauth_denial(app):
    from src.auth.state import create_state
    state = create_state()
    client = TestClient(app)
    r = client.get(f"/auth/callback?error=access_denied&state={state}",
                   follow_redirects=False)
    # Expect 200 with error template, not a 302
    assert r.status_code == 200
    assert "denied" in r.text.lower() or "avbruten" in r.text.lower() or "error" in r.text.lower()


def _mock_token_response(token):
    resp = AsyncMock()
    resp.json.return_value = {"access_token": token}
    resp.raise_for_status = lambda: None
    return resp


def _mock_user_response(uid, email, username):
    resp = AsyncMock()
    resp.json.return_value = {
        "user": {"id": uid, "email": email, "username": username,
                 "color": "#ccc", "profile_picture": None}
    }
    resp.raise_for_status = lambda: None
    return resp


def _mock_workspaces_response(workspaces):
    resp = AsyncMock()
    resp.json.return_value = {"teams": workspaces}
    resp.raise_for_status = lambda: None
    return resp


def test_callback_creates_user_token_session_and_redirects_when_one_workspace(app):
    from src.auth.state import create_state
    from src.auth.users import get_user, get_user_token
    state = create_state()

    with patch("httpx.AsyncClient.post",
               return_value=_mock_token_response("oauth_abc")), \
         patch("httpx.AsyncClient.get",
               side_effect=[
                   _mock_user_response(12345, "a@x.se", "anna"),
                   _mock_workspaces_response([{"id": "ws1", "name": "Acme"}]),
               ]):
        client = TestClient(app)
        r = client.get(f"/auth/callback?code=the_code&state={state}",
                       follow_redirects=False)

    assert r.status_code == 302
    assert r.headers["location"] == "/"
    assert "sprint_reporter_session" in r.cookies
    # User and token stored
    assert get_user("12345") is not None
    assert get_user_token("12345") == "oauth_abc"


def test_callback_redirects_to_workspace_picker_when_multiple_workspaces(app):
    from src.auth.state import create_state
    state = create_state()

    with patch("httpx.AsyncClient.post",
               return_value=_mock_token_response("oauth_abc")), \
         patch("httpx.AsyncClient.get",
               side_effect=[
                   _mock_user_response(12345, "a@x.se", "anna"),
                   _mock_workspaces_response([
                       {"id": "ws1", "name": "Acme"},
                       {"id": "ws2", "name": "Side"},
                   ]),
               ]):
        client = TestClient(app)
        r = client.get(f"/auth/callback?code=the_code&state={state}",
                       follow_redirects=False)

    assert r.status_code == 302
    assert r.headers["location"] == "/auth/workspace"


def test_callback_state_is_one_shot(app):
    """A state can only be consumed once — replay is rejected."""
    from src.auth.state import create_state
    state = create_state()

    with patch("httpx.AsyncClient.post",
               return_value=_mock_token_response("oauth_abc")), \
         patch("httpx.AsyncClient.get",
               side_effect=[
                   _mock_user_response(12345, "a@x.se", "anna"),
                   _mock_workspaces_response([{"id": "ws1", "name": "Acme"}]),
               ]):
        client = TestClient(app)
        r1 = client.get(f"/auth/callback?code=the_code&state={state}",
                        follow_redirects=False)
        assert r1.status_code == 302

    # Replay with same state
    client2 = TestClient(app)
    r2 = client2.get(f"/auth/callback?code=the_code&state={state}",
                     follow_redirects=False)
    assert r2.status_code == 400
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest tests/test_auth_routes.py -v`
Expected: 6 new tests FAIL — `/auth/callback` not implemented.

- [ ] **Step 3: Add `/auth/callback` to `src/routes/auth.py`**

Add the import block additions at the top of the file:

```python
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from src.auth.oauth import exchange_code, fetch_user, fetch_workspaces
from src.auth.state import consume_state
from src.auth.users import upsert_user, save_user_token
from src.auth.sessions import create_session
from src.config import COOKIE_SECURE
```

Then append:

```python
COOKIE_NAME = "sprint_reporter_session"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


@router.get("/callback")
async def callback(request: Request, code: str | None = None,
                   state: str | None = None, error: str | None = None):
    """Handle ClickUp's OAuth redirect.

    On success: exchange code, fetch user + workspaces, store, set cookie, redirect.
    On error: render the auth error template.
    On missing/invalid state: 400."""

    if not state or not consume_state(state):
        log.warning("OAuth callback rejected: invalid or missing state")
        raise HTTPException(status_code=400, detail="invalid_state")

    if error:
        log.info("OAuth callback received error=%s", error)
        return templates.TemplateResponse(
            "auth/error.html",
            {"request": request, "error": error},
        )

    if not code:
        log.warning("OAuth callback rejected: missing code")
        raise HTTPException(status_code=400, detail="missing_code")

    access_token = await exchange_code(code)
    user_data = await fetch_user(access_token)
    workspaces = await fetch_workspaces(access_token)

    upsert_user(
        id=user_data["id"],
        email=user_data["email"],
        username=user_data["username"],
        color=user_data["color"],
        profile_picture=user_data["profile_picture"],
    )
    save_user_token(user_id=user_data["id"], access_token=access_token, scopes=None)

    if len(workspaces) == 1:
        active_ws = workspaces[0]["id"]
        next_path = "/"
    else:
        active_ws = None
        next_path = "/auth/workspace"

    sid = create_session(user_id=user_data["id"], active_workspace_id=active_ws)
    log.info("Login successful for user=%s (%d workspace(s))",
             user_data["id"], len(workspaces))

    response = RedirectResponse(next_path, status_code=302)
    response.set_cookie(
        key=COOKIE_NAME, value=sid,
        max_age=COOKIE_MAX_AGE, httponly=True,
        samesite="lax", secure=COOKIE_SECURE,
    )
    return response
```

Also create the auth error template stub so the test doesn't 500. Create `templates/auth/error.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Login error — Sprint Reporter</title>
<link rel="stylesheet" href="/static/style.css?v=5"></head>
<body>
<div class="auth-card">
  <h1>Login error</h1>
  <p>Sign-in was {% if error == "access_denied" %}cancelled{% else %}rejected ({{ error }}){% endif %}.</p>
  <a class="btn btn-primary" href="/auth/login">Try again</a>
</div>
</body>
</html>
```

- [ ] **Step 4: Run all auth-route tests to verify pass**

Run: `pytest tests/test_auth_routes.py -v`
Expected: 8 tests PASS (2 from Task 10 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add src/routes/auth.py tests/test_auth_routes.py templates/auth/error.html
git commit -m "feat(auth): /auth/callback exchanges code, creates session, sets cookie"
```

---

### Task 12: Auth routes — `/auth/workspace` GET + POST

**Files:**
- Modify: `src/routes/auth.py`
- Modify: `tests/test_auth_routes.py`
- Create: `templates/auth/workspace.html`

- [ ] **Step 1: Append failing tests**

Add to `tests/test_auth_routes.py`:

```python
def test_workspace_get_unauthenticated_returns_401(app):
    client = TestClient(app)
    r = client.get("/auth/workspace", follow_redirects=False)
    assert r.status_code == 401


def test_workspace_get_lists_workspaces(app):
    """The picker fetches the user's workspaces fresh via their token."""
    from src.auth.users import upsert_user, save_user_token
    from src.auth.sessions import create_session
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz", scopes=None)
    sid = create_session(user_id="u1", active_workspace_id=None)

    with patch("httpx.AsyncClient.get",
               return_value=_mock_workspaces_response([
                   {"id": "ws1", "name": "Acme"},
                   {"id": "ws2", "name": "Side"},
               ])):
        client = TestClient(app)
        client.cookies.set("sprint_reporter_session", sid)
        r = client.get("/auth/workspace")

    assert r.status_code == 200
    assert "Acme" in r.text
    assert "Side" in r.text


def test_workspace_post_sets_active_and_redirects(app):
    from src.auth.users import upsert_user, save_user_token
    from src.auth.sessions import create_session, get_session
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz", scopes=None)
    sid = create_session(user_id="u1", active_workspace_id=None)

    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    r = client.post("/auth/workspace", data={"workspace_id": "ws_chosen"},
                    follow_redirects=False)

    assert r.status_code == 302
    assert r.headers["location"] == "/"
    assert get_session(sid)["active_workspace_id"] == "ws_chosen"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth_routes.py -v`
Expected: 3 new tests FAIL.

- [ ] **Step 3: Add `Form` import + workspace routes to `src/routes/auth.py`**

At the top of the file, add to imports:

```python
from fastapi import Form, Depends
from src.auth.oauth import fetch_workspaces
from src.auth.middleware import get_current_user
from src.auth.sessions import set_active_workspace
from src.auth.users import get_user_token
```

Append routes:

```python
@router.get("/workspace", response_class=HTMLResponse)
async def workspace_get(request: Request, user=Depends(get_current_user)):
    """Show the workspace picker. Fetches workspaces fresh from ClickUp."""
    token = get_user_token(user["id"])
    workspaces = await fetch_workspaces(token)
    return templates.TemplateResponse(
        "auth/workspace.html",
        {"request": request, "workspaces": workspaces, "user": user},
    )


@router.post("/workspace")
def workspace_post(request: Request, workspace_id: str = Form(...),
                   user=Depends(get_current_user)):
    """Save the selected workspace on the session."""
    set_active_workspace(request.state.session_id, workspace_id)
    log.info("User %s selected workspace %s", user["id"], workspace_id)
    return RedirectResponse("/", status_code=302)
```

- [ ] **Step 4: Create `templates/auth/workspace.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Select workspace — Sprint Reporter</title>
  <link rel="stylesheet" href="/static/style.css?v=5">
</head>
<body>
<div class="auth-card">
  <h1>Select workspace</h1>
  <p class="text-muted">You're signed in as <strong>{{ user.username or user.email }}</strong>.</p>
  <form method="post" action="/auth/workspace">
    <ul class="workspace-list">
      {% for ws in workspaces %}
      <li>
        <button type="submit" name="workspace_id" value="{{ ws.id }}" class="workspace-btn">
          <span class="workspace-name">{{ ws.name }}</span>
        </button>
      </li>
      {% endfor %}
    </ul>
  </form>
</div>
</body>
</html>
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_auth_routes.py -v`
Expected: 11 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/routes/auth.py templates/auth/workspace.html tests/test_auth_routes.py
git commit -m "feat(auth): workspace picker GET/POST routes"
```

---

### Task 13: Auth route — `/auth/logout`

**Files:**
- Modify: `src/routes/auth.py`
- Modify: `tests/test_auth_routes.py`

- [ ] **Step 1: Append failing test**

Add to `tests/test_auth_routes.py`:

```python
def test_logout_deletes_session_and_clears_cookie(app):
    from src.auth.users import upsert_user
    from src.auth.sessions import create_session, get_session
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    sid = create_session(user_id="u1", active_workspace_id=None)

    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    r = client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/login"
    # Session row gone
    assert get_session(sid) is None
    # Cookie was cleared (max-age=0 or similar)
    cookie_header = r.headers.get("set-cookie", "")
    assert "sprint_reporter_session" in cookie_header
    assert "Max-Age=0" in cookie_header or "max-age=0" in cookie_header.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_routes.py::test_logout_deletes_session_and_clears_cookie -v`
Expected: FAIL.

- [ ] **Step 3: Add `/auth/logout` to `src/routes/auth.py`**

Add to imports:

```python
from src.auth.sessions import delete_session
```

Append:

```python
@router.post("/logout")
def logout(request: Request):
    """Delete the session row, clear the cookie, redirect to login."""
    sid = request.cookies.get(COOKIE_NAME)
    if sid:
        delete_session(sid)
        log.info("Logged out session=%s", sid[:8])
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response
```

- [ ] **Step 4: Run all auth tests to verify pass**

Run: `pytest tests/test_auth_routes.py -v`
Expected: 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/routes/auth.py tests/test_auth_routes.py
git commit -m "feat(auth): /auth/logout deletes session and clears cookie"
```

---

### Task 14: Login template

**Files:**
- Create: `templates/auth/login.html`
- Modify: `src/routes/auth.py` (add `GET /auth/login` HTML page when redirect not desired)

Decision recap: per spec, `/auth/login` redirects directly to ClickUp. We don't need a separate landing page in this minimal v1 — the unauthenticated user clicking a link or visiting `/` lands on `/auth/login` which immediately bounces to ClickUp. **However**, we DO want a fallback page when login is the natural starting point (e.g., logged-out user clicked logout). The error template covers OAuth-denial, but we need a "Sign in to continue" landing page that the 401-redirect handler can use as a destination.

**Adjustment:** keep `/auth/login` as a direct redirect (already done). Add `/auth/welcome` as the unauth landing page that the 401 handler routes to. Actually simpler — keep the current behavior and skip the welcome page; the 401 handler can redirect directly to `/auth/login`, which immediately bounces to ClickUp. The user only ever sees the ClickUp consent screen, never our login page. **Cleaner.**

This task therefore reduces to: **no template needed**. We skip this task.

- [ ] **Step 1: No-op confirmation**

Document why we're not creating `templates/auth/login.html`. If a future iteration wants a branded landing page, add it then.

```bash
# No code changes for this task. Move on to Task 15.
```

---

### Task 15: User identity in base.html (header + logout + workspace switcher)

**Files:**
- Modify: `templates/base.html`
- Modify: `src/routes/pages.py` (only to surface user/active_workspace_id/workspaces to template context)

Defer the actual context wiring to Task 17 (where pages.py gets refactored). For this task, just add the markup that renders only when context vars are present.

- [ ] **Step 1: Modify `templates/base.html`**

Replace contents with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Sprint Reporter{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css?v=5">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
  <header class="identity-bar">
    <a href="/" class="brand">Sprint Reporter</a>
    <div class="identity-actions">
      {% if current_user %}
        {% if user_workspaces and user_workspaces|length > 1 %}
        <form method="post" action="/auth/workspace" class="workspace-switcher">
          <select name="workspace_id" onchange="this.form.submit()">
            {% for ws in user_workspaces %}
            <option value="{{ ws.id }}" {% if ws.id == active_workspace_id %}selected{% endif %}>{{ ws.name }}</option>
            {% endfor %}
          </select>
        </form>
        {% endif %}
        <span class="user-chip">{{ current_user.username or current_user.email }}</span>
        <form method="post" action="/auth/logout" class="logout-form">
          <button type="submit" class="btn btn-secondary">Sign out</button>
        </form>
      {% endif %}
      <a href="/teams/new" class="btn btn-primary new-team-btn">+ New Team</a>
    </div>
  </header>
  {% include "components/breadcrumbs.html" %}
  {% include "components/team_sub_nav.html" %}
  {% block content %}{% endblock %}
  <script src="/static/dashboard.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify no template render errors**

Run: `pytest tests/ -v`
Expected: same number of tests as before; no template rendering errors. (User context is not yet wired so the `if current_user` blocks render nothing.)

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat(auth): user identity, logout, and workspace switcher in header (markup only)"
```

---

### Task 16: Wire auth into app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the auth router and 401 redirect handler**

Modify `app.py`:

Add after existing imports:

```python
from src.routes import auth as auth_routes
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
```

Replace the section starting at `app.include_router(pages.router)` (around line 136) with:

```python
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
```

- [ ] **Step 2: Smoke-test app boot**

Run: `pytest tests/ -v`
Expected: all existing tests still pass.

Manual: `./.venv/bin/uvicorn app:app --port 8001` (or use start.sh), `curl -i http://localhost:8001/`. Expected: 302 to `/auth/login`. Then `curl -i http://localhost:8001/auth/login` → 302 to `app.clickup.com`.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat(auth): register auth router and 401-to-redirect handler"
```

---

### Task 17: Update `routes/pages.py` to use authenticated client + filter by workspace

**Files:**
- Modify: `src/routes/pages.py`

This task changes every protected page route to:
1. Require `Depends(get_current_user)`.
2. Use `request.state.user_client` instead of constructing a `ClickUpClient` from a global key.
3. Filter team queries by `request.state.active_workspace_id`.
4. Pass user / workspaces context into the template.

- [ ] **Step 1: Update `src/routes/pages.py`**

Add to imports at top:

```python
from fastapi import Depends
from src.auth.middleware import get_current_user
from src.auth.oauth import fetch_workspaces as oauth_fetch_workspaces
from src.auth.users import get_user_token
```

Update `_ctx` to include user identity:

```python
def _ctx(request, breadcrumbs=None, team_sub_nav_active=None, **kwargs):
    kwargs["request"] = request
    kwargs["nav_teams"] = _scoped_teams(request)
    kwargs["breadcrumbs"] = breadcrumbs or []
    kwargs["team_sub_nav_active"] = team_sub_nav_active
    kwargs["current_user"] = getattr(request.state, "user", None)
    kwargs["active_workspace_id"] = getattr(request.state, "active_workspace_id", None)
    kwargs["user_workspaces"] = getattr(request.state, "user_workspaces", [])
    return kwargs


def _scoped_teams(request):
    """Return teams filtered to the active workspace (if set)."""
    ws = getattr(request.state, "active_workspace_id", None)
    all_teams = get_all_teams()
    if not ws:
        return all_teams
    return [t for t in all_teams if t.get("workspace_id") in (ws, None)]
```

(Note: `workspace_id IS NULL` teams are temporarily included so backfill can complete; once Task 19 backfill runs, the `None` fallback can be removed in a follow-up.)

Replace `_needs_setup` with:

```python
def _needs_setup() -> bool:
    """Setup is needed only if no service key is configured anywhere.
    OAuth users don't trigger this; this is for the cron job."""
    from src.config import get_service_api_key
    return not get_service_api_key()
```

For each protected route handler, add `user=Depends(get_current_user)` and replace `ClickUpClient(get_clickup_api_key())` with `request.state.user_client`. Specifically:

- `home(request)` → `home(request, user=Depends(get_current_user))`. Replace `get_all_teams()` with `_scoped_teams(request)`.
- `setup_page(request)` → keep public for now (admin bootstrap); leave unchanged.
- `save_setup(request)` → keep public; leave unchanged.
- `new_team_page(request)` → add `user=Depends(get_current_user)`.
- `team_settings_page(request, team_id)` → add `user=Depends(get_current_user)`.
- `sprint_history_page(request, team_id)` → add `user=Depends(get_current_user)`.
- `sprint_page(request, sprint_id)` → add `user=Depends(get_current_user)`. Replace:
  ```python
  from src.clickup_client import ClickUpClient
  from src.config import get_clickup_api_key
  client = ClickUpClient(get_clickup_api_key())
  ```
  with:
  ```python
  client = request.state.user_client
  ```
- `team_trends_page(request, team_id, range)` → add `user=Depends(get_current_user)`.

Also wire `request.state.user_workspaces` so the template's switcher can render. Add in `home` after the dependency gate:

```python
async def home(request: Request, user=Depends(get_current_user)):
    if _needs_setup():
        return RedirectResponse("/setup")
    # Populate workspaces for the switcher
    token = get_user_token(user["id"])
    request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []
    teams = _scoped_teams(request)
    ...
```

(Apply the same `request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []` in any route where you want the switcher visible. For v1, just `home` and `sprint_history_page` is enough; the switcher hides itself when `user_workspaces` is empty.)

- [ ] **Step 2: Smoke-test**

Run: `pytest tests/ -v`
Expected: pre-existing tests for pages still pass. (We don't have route-level tests for pages.py; reliance on integration smoke later.)

Manual smoke:
```bash
./stop.sh; ./start.sh
# Visit http://localhost:8000 → expect redirect to /auth/login → ClickUp
```

- [ ] **Step 3: Commit**

```bash
git add src/routes/pages.py
git commit -m "feat(auth): pages routes require login, use user_client, filter by workspace"
```

---

### Task 18: Update `routes/teams.py` and `routes/sprints.py`

**Files:**
- Modify: `src/routes/teams.py`
- Modify: `src/routes/sprints.py`

- [ ] **Step 1: Update `src/routes/teams.py`**

Add to imports:

```python
from fastapi import Request, Depends
from src.auth.middleware import get_current_user
```

Modify the routes:

- All endpoints get `user=Depends(get_current_user)` and (where they call ClickUp) accept `request: Request`.
- `create_team` POST: scope new team to active workspace by writing `clickup_workspace_id = request.state.active_workspace_id` into the team. Existing call already passes `body.clickup_workspace_id`; we trust the body here since the team setup form fills it in. **No change needed for now.** But we DO add a `workspace_id` column write — patch `team_service.create_team` to also persist `workspace_id` (see below).
- `sync_sprints`: replace `ClickUpClient(get_clickup_api_key())` with `request.state.user_client`.

Replace `create_team`:

```python
@router.post("")
def create_team(body: TeamCreate, request: Request,
                user=Depends(get_current_user)):
    workspace_id = request.state.active_workspace_id
    team = team_service.create_team(
        body.name, body.clickup_workspace_id, body.clickup_space_id,
        body.clickup_folder_id, body.metric_type, body.capacity_mode,
        body.sprint_length_days, workspace_id=workspace_id,
    )
    if body.members:
        team_service.set_team_members(team["id"], [m.model_dump() for m in body.members])
    return team
```

Update `sync_sprints`:

```python
@router.post("/{team_id}/sync-sprints")
async def sync_sprints(team_id: int, request: Request,
                       user=Depends(get_current_user)):
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    client = request.state.user_client
    lists = await client.get_folder_lists(team["clickup_folder_id"])
    synced = []
    for lst in lists:
        start, end = parse_iteration_dates(lst["name"])
        if not start:
            continue
        sprint = create_sprint_from_list(team["id"], lst["id"], lst["name"])
        synced.append(sprint)
    return {"synced": len(synced), "sprints": synced}
```

Add `Depends(get_current_user)` to: `list_teams`, `get_team`, `update_team`, `delete_team`, `team_sprints`, `team_trends`.

- [ ] **Step 2: Update `src/services/team_service.create_team` to accept and persist `workspace_id`**

Read `src/services/team_service.py` to find `create_team`. Update its signature and INSERT to include `workspace_id`. (Engineer: open the file, add `workspace_id: str | None = None` parameter, append `workspace_id` to the INSERT column list and value tuple.)

- [ ] **Step 3: Update `src/routes/sprints.py`**

Add to imports:

```python
from fastapi import Request, Depends
from src.auth.middleware import get_current_user
```

Replace the helper:

```python
async def _fetch_tasks(sprint: dict, client):
    """Fetch tasks for a sprint using a caller-provided client."""
    team = get_team(sprint["team_id"])
    raw_tasks = await client.get_list_tasks(
        sprint["clickup_list_id"],
        space_id=team["clickup_space_id"],
        workspace_id=team.get("clickup_workspace_id"),
    )
    return raw_tasks
```

Then update each `_fetch_tasks(sprint)` call site to pass `request.state.user_client`:

```python
raw_tasks = await _fetch_tasks(sprint, request.state.user_client)
```

Add `request: Request, user=Depends(get_current_user)` to every route handler. Update `extract_task_data` callers — since `client` is no longer returned from the helper, instantiate it inline or use the user_client (it's the same object):

Replace existing pattern:

```python
client, raw_tasks = await _fetch_tasks(sprint)
tasks = [client.extract_task_data(t) for t in raw_tasks]
```

With:

```python
client = request.state.user_client
raw_tasks = await _fetch_tasks(sprint, client)
tasks = [client.extract_task_data(t) for t in raw_tasks]
```

Apply this pattern in `close_forecast_route`, `close_sprint_route`, `refresh_route`, `sprint_tasks`.

- [ ] **Step 4: Update `clickup_proxy.py` similarly**

Open `src/routes/clickup_proxy.py`. Add `Depends(get_current_user)` to every route. Replace any `ClickUpClient(get_clickup_api_key())` with `request.state.user_client`.

- [ ] **Step 5: Verify**

Run: `pytest tests/ -v`
Expected: existing tests still pass. Pre-existing test debt (Initiative 1B) doesn't get worse.

Manual smoke after restart:
```bash
./stop.sh && ./start.sh
# Log in. Visit dashboard. Click Sync. Verify tail of app.log shows requests with no errors.
tail -f app.log
```

- [ ] **Step 6: Commit**

```bash
git add src/routes/teams.py src/routes/sprints.py src/routes/clickup_proxy.py src/services/team_service.py
git commit -m "feat(auth): teams/sprints/proxy routes require login, use user_client"
```

---

### Task 19: Token revocation on 401 from ClickUp

**Files:**
- Modify: `src/auth/middleware.py` (or app.py exception handler)
- Modify: `tests/test_auth_middleware.py`

When a route uses `request.state.user_client` and the token has been revoked in ClickUp, the next call raises `ClickUpError(status_code=401)`. We catch it at the app level, delete the user's token + sessions, and force re-login.

- [ ] **Step 1: Append failing test to `tests/test_auth_middleware.py`**

```python
def test_clickup_401_clears_token_and_session(monkeypatch, tmp_path):
    """When the user_client gets 401 from ClickUp, the next request must require re-login."""
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("COOKIE_SECURE", "false")
    import importlib, src.config, src.auth.encryption, src.auth.users, src.auth.sessions
    import src.auth.middleware
    for m in (src.config, src.auth.encryption, src.auth.users,
              src.auth.sessions, src.auth.middleware):
        importlib.reload(m)
    from src.database import init_db
    init_db(str(tmp_path / "test.db"))
    from src.auth.users import upsert_user, save_user_token, get_user_token
    from src.auth.sessions import create_session, get_session
    upsert_user(id="u1", email="a@x.se", username="anna",
                color=None, profile_picture=None)
    save_user_token(user_id="u1", access_token="oauth_xyz", scopes=None)
    sid = create_session(user_id="u1", active_workspace_id="ws_1")

    from fastapi import FastAPI, Depends, Request
    from fastapi.testclient import TestClient
    from src.auth.middleware import get_current_user
    from src.clickup_client import ClickUpError
    from app import auth_exception_handler
    from fastapi import HTTPException

    app = FastAPI()
    app.add_exception_handler(HTTPException, auth_exception_handler)
    app.add_exception_handler(ClickUpError, lambda r, e: src.auth.middleware.handle_clickup_error(r, e))

    @app.get("/explodes")
    def boom(request: Request, user=Depends(get_current_user)):
        raise ClickUpError("token revoked", status_code=401)

    client = TestClient(app)
    client.cookies.set("sprint_reporter_session", sid)
    r = client.get("/explodes", follow_redirects=False)

    # Token + session cleared
    assert get_user_token("u1") is None
    assert get_session(sid) is None
    # Response should redirect
    assert r.status_code == 302
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_middleware.py::test_clickup_401_clears_token_and_session -v`
Expected: FAIL — handler doesn't exist.

- [ ] **Step 3: Add `handle_clickup_error` to `src/auth/middleware.py`**

Append:

```python
from fastapi.responses import RedirectResponse, JSONResponse
from src.auth.users import delete_user_token
from src.auth.sessions import delete_sessions_for_user, delete_session


def handle_clickup_error(request: Request, exc) -> RedirectResponse | JSONResponse:
    """Catch ClickUpError. On 401, treat as token revoked: delete token + sessions
    and redirect to login (or 401 JSON for AJAX)."""
    from src.clickup_client import ClickUpError
    if not isinstance(exc, ClickUpError) or exc.status_code != 401:
        # Re-raise non-401 ClickUp errors as 502
        return JSONResponse({"detail": str(exc)}, status_code=502)

    user = getattr(request.state, "user", None)
    sid = getattr(request.state, "session_id", None)
    if user:
        log.warning("ClickUp 401 for user %s — purging token and sessions", user["id"])
        delete_user_token(user["id"])
        delete_sessions_for_user(user["id"])
    elif sid:
        delete_session(sid)

    accept = request.headers.get("accept", "")
    is_json_request = "application/json" in accept and "text/html" not in accept
    if is_json_request or request.url.path.startswith("/api"):
        return JSONResponse({"detail": "session_expired"}, status_code=401)
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response
```

- [ ] **Step 4: Wire into `app.py`**

Add to `app.py` imports:

```python
from src.clickup_client import ClickUpError
from src.auth.middleware import handle_clickup_error
```

Add right after the existing `auth_exception_handler` registration:

```python
@app.exception_handler(ClickUpError)
async def clickup_error_handler(request: Request, exc: ClickUpError):
    return handle_clickup_error(request, exc)
```

- [ ] **Step 5: Run test to verify pass**

Run: `pytest tests/test_auth_middleware.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/auth/middleware.py app.py tests/test_auth_middleware.py
git commit -m "feat(auth): purge user token + sessions on ClickUp 401 (token revocation)"
```

---

### Task 20: Backfill `teams.workspace_id` migration

**Files:**
- Modify: `src/database.py` (add backfill helper) OR `app.py` (run on startup)

Decision: do the backfill in `app.py`'s lifespan startup, after `init_db`. We use the service-account client (no OAuth user available at boot) to look up each team's workspace_id via `/team/{team_id}` ClickUp endpoint... actually that's not the right endpoint. ClickUp's API doesn't have a single endpoint to "get workspace ID for a folder". Instead, the team already has `clickup_workspace_id` populated (the existing column from the original schema, line 17 of database.py: `clickup_workspace_id TEXT NOT NULL DEFAULT ''`).

**Re-using existing data:** the new `workspace_id` column duplicates the existing `clickup_workspace_id` — they're the same thing. The backfill is just: `UPDATE teams SET workspace_id = clickup_workspace_id WHERE workspace_id IS NULL AND clickup_workspace_id != ''`. No ClickUp API call needed.

- [ ] **Step 1: Add backfill to `init_db` in `src/database.py`**

After the existing `try: ALTER TABLE teams ADD COLUMN workspace_id TEXT` block, add:

```python
# Backfill workspace_id from the existing clickup_workspace_id column
conn.execute("""
    UPDATE teams
    SET workspace_id = clickup_workspace_id
    WHERE (workspace_id IS NULL OR workspace_id = '')
      AND clickup_workspace_id IS NOT NULL
      AND clickup_workspace_id != ''
""")
```

- [ ] **Step 2: Add a test**

Append to `tests/test_auth_database.py`:

```python
def test_workspace_id_backfilled_from_clickup_workspace_id(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    conn.execute("""
        INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id)
        VALUES ('Acme', 'ws_42', 'sp_1', 'fld_1')
    """)
    conn.commit()
    conn.close()
    # Now re-init to trigger the backfill
    init_db(db)
    conn = get_connection(db)
    row = conn.execute("SELECT workspace_id FROM teams WHERE name = 'Acme'").fetchone()
    conn.close()
    assert row["workspace_id"] == "ws_42"
```

- [ ] **Step 3: Run tests to verify pass**

Run: `pytest tests/test_auth_database.py -v`
Expected: 7 tests PASS (6 from Task 1 + 1 new).

- [ ] **Step 4: Commit**

```bash
git add src/database.py tests/test_auth_database.py
git commit -m "feat(auth): backfill teams.workspace_id from existing clickup_workspace_id"
```

---

### Task 21: `.env.example` + smoke test

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update `.env.example`**

Read current file:

```bash
cat /Users/collin/dev/Projects/ClickUp-report-app/.env.example
```

Replace contents with (preserving any existing custom vars; if file doesn't exist, create it):

```dotenv
# Server
HOST=0.0.0.0
PORT=8000
DB_PATH=./sprint_data.db

# Daily snapshot (cron)
DAILY_SNAPSHOT_TIME=06:00
# Service-account API key for the daily snapshot job (impersonal cron).
# Get one from a ClickUp account designated as the "Sprint Reporter Bot" service account.
CLICKUP_SERVICE_API_KEY=

# Legacy: read as fallback if CLICKUP_SERVICE_API_KEY isn't set. Will be removed later.
CLICKUP_API_KEY=

# OAuth (each colleague signs in with their own ClickUp account)
# Create an app at: https://app.clickup.com → Settings → Integrations → ClickUp API
# Add the redirect URI below to the app's allowed list.
CLICKUP_OAUTH_CLIENT_ID=
CLICKUP_OAUTH_CLIENT_SECRET=
OAUTH_REDIRECT_URI=http://localhost:8000/auth/callback

# Encrypts user OAuth tokens at rest. Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# If rotated, all users must re-login.
SESSION_ENCRYPTION_KEY=

# Cookie security: set to "false" only when running on localhost over plain HTTP.
COOKIE_SECURE=true
```

- [ ] **Step 2: Generate a real encryption key for local dev (DO NOT commit)**

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the printed key to your local `.env` as `SESSION_ENCRYPTION_KEY=...`. **Don't commit `.env`** — only `.env.example` is committed.

- [ ] **Step 3: Manual smoke test**

```bash
./stop.sh; ./start.sh
tail -f app.log &
```

- Open `http://localhost:8000/` → expect redirect to `/auth/login` → expect 302 to `app.clickup.com`.
- (If you have a registered ClickUp OAuth app:) click "Authorize" → expect redirect to `/auth/callback` → expect either `/` or `/auth/workspace`.
- (If not yet registered:) the ClickUp page will show "client_id invalid" — that's expected; the rest of the wiring is verified by the test suite.
- Check `app.log` shows: `App startup`, `Daily snapshot job starting/done`.
- Run all tests: `pytest tests/ -v`. Expected: green.

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "docs(auth): document new env vars in .env.example"
```

---

## Self-review checklist (run after writing this plan)

**Spec coverage:**
- ✅ Auth flow (login, callback, workspace pick, logout) → Tasks 10–13
- ✅ Sessions, encryption, oauth state → Tasks 2, 5, 6
- ✅ DB schema additions → Task 1
- ✅ ClickUp client refactor (system vs user) → Task 8
- ✅ Middleware (`get_current_user` + `request.state.user_client`) → Task 9
- ✅ Workspace scoping for teams → Task 17, 18
- ✅ Background job stays on service key → Task 8 + verified by Task 21 smoke
- ✅ Token revocation handling → Task 19
- ✅ Migration / backfill of teams.workspace_id → Task 20
- ✅ Cookie flags (HttpOnly, SameSite, Secure) → Task 11 + Task 3 (COOKIE_SECURE)
- ✅ User identity in header + workspace switcher → Task 15

**Placeholder scan:** No "TBD"/"TODO"/"appropriate error handling" patterns. Every code step has actual code.

**Type consistency:**
- `upsert_user(id, email, username, color, profile_picture)` — same signature in Task 4, 11, 12, etc.
- `create_session(user_id, active_workspace_id)` — same in Task 5, 11, 12.
- `get_user_token(user_id)` returns plaintext token — consistent in Tasks 4, 9, 12.
- Cookie name `sprint_reporter_session` — consistent across Tasks 9, 11, 13.

**Open question for human review:**
- ClickUp's exact OAuth wire format (POST body vs query params, header format for OAuth tokens) is asserted from documentation but not yet verified against a live OAuth app. Task 21 smoke test will verify; if any details need correction, they're isolated to `src/auth/oauth.py` (Task 7).
