# ClickUp OAuth Login (Initiative 3)

## Context

Today the app uses a single ClickUp API key stored in `.env` (or `app_settings`) for *all* ClickUp calls. There are no users, no logins, no per-person access. Anyone with the URL can use the app. This was fine for a single-user dev tool but blocks rolling it out to colleagues:

1. Every colleague would share the same API key, so we can't tell who did what.
2. The key gives full access to everything that key's owner has in ClickUp — there's no per-user scoping.
3. There's no logout, no revocation, no audit trail.

This initiative adds proper authentication by letting each user sign in with their own ClickUp account via OAuth 2.0. The app authenticates them, scopes their access to a workspace they choose, and uses *their* token for ClickUp API calls in the UI. The background snapshot job continues to use a dedicated service key (impersonal cron job).

## Problem

Three concrete things colleagues can't do today:

1. **Sign in.** No login screen. The app is open to anyone who can reach the URL.
2. **Use their own ClickUp permissions.** All API calls go through one shared key. If the key's owner can see private projects, anyone using the app sees them too.
3. **Have their access revoked.** When someone leaves the team, the only way to cut off access is to rotate the shared API key — which logs out everyone.

## Goal

After this initiative:

1. Anyone visiting the app gets redirected to a ClickUp OAuth login screen. After authorizing, they pick a workspace (if they're in multiple) and land on the dashboard.
2. UI requests use the signed-in user's OAuth token. They see only what their ClickUp account can see in the chosen workspace.
3. The background daily-snapshot job keeps running on a dedicated service API key (no human required).
4. Users can sign out. Their session is revoked immediately. If they revoke the app in ClickUp settings, the next API call fails cleanly and they're forced to re-login.
5. Visibility within the app is open — any authenticated user can view all data in their selected workspace. Per-user edit RBAC is **out of scope** (deferred to a future initiative).

## Non-Goals

- **No per-user RBAC.** All authenticated users see and edit the same data. A future initiative may add `users.role` for edit gating; we design the schema so that's a column-add, not a refactor.
- **No SSO beyond ClickUp.** No Google/Microsoft login. ClickUp OAuth only.
- **No token refresh logic.** ClickUp access tokens currently don't expire. If that changes, we add refresh later.
- **No CSRF tokens on POST forms.** The OAuth `state` parameter covers the auth flow. Same-origin POSTs from authenticated sessions are protected by `SameSite=Lax` cookies. Form-level CSRF tokens are deferred unless we open up cross-origin scenarios.
- **No multi-tenant isolation across organizations.** This is a tool for one company's internal use. We support workspace selection (option 2 from brainstorm), not hard tenancy.
- **No password fallback.** No "forgot password", no local accounts. ClickUp is the identity provider.
- **No audit log.** Logins are logged via the existing `logging` config from Initiative 1A. A dedicated audit table is out of scope.

## Design

### Part 1: OAuth flow

Standard OAuth 2.0 Authorization Code grant with PKCE.

**Endpoints we add:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/auth/login` | Generate state + PKCE verifier, persist to `oauth_state`, redirect to ClickUp authorize URL |
| GET | `/auth/callback` | Verify state, exchange code for token, fetch user+workspaces, create session, redirect |
| GET | `/auth/workspace` | Workspace picker page (only shown if user is in >1 workspace) |
| POST | `/auth/workspace` | Set `sessions.active_workspace_id`, redirect home |
| POST | `/auth/logout` | Delete session row, clear cookie, redirect to `/auth/login` |

**ClickUp endpoints we call:**

- `https://app.clickup.com/api?client_id=...&redirect_uri=...&state=...` — authorize (browser redirect)
- `POST https://api.clickup.com/api/v2/oauth/token` with `client_id`, `client_secret`, `code` — exchange
- `GET https://api.clickup.com/api/v2/user` — fetch authenticated user
- `GET https://api.clickup.com/api/v2/team` — fetch user's workspaces (ClickUp calls them "teams" but that's their workspace concept)

**Flow narrative:**

1. Unauthenticated user hits `/`. Middleware sees no valid session cookie → 302 to `/auth/login`.
2. `/auth/login` generates random `state` (32-byte hex), random `code_verifier`, computes `code_challenge = base64url(sha256(verifier))`. Stores `(state, code_verifier, created_at)` in `oauth_state`. Redirects to ClickUp's authorize URL with `client_id`, `redirect_uri`, `state` (PKCE for the upcoming code exchange).
3. User authorizes in ClickUp. ClickUp redirects to our `/auth/callback?code=...&state=...`.
4. Callback looks up `state` in `oauth_state` (rejects if missing or >10min old). Pops the verifier. Calls token endpoint with `code` + `client_secret` + `code_verifier`.
5. With the access token, calls `/user` (get user_id, email, name, avatar) and `/team` (get list of workspaces).
6. Upserts `users` row, encrypts and stores token in `user_tokens`, creates a `sessions` row, sets cookie.
7. If exactly one workspace → set `active_workspace_id` and redirect to `/`. If multiple → redirect to `/auth/workspace`.
8. User picks workspace → POST sets `active_workspace_id` → redirect to `/`.

**`oauth_state` cleanup:** On every `/auth/login` we also delete rows older than 10 minutes. No background job needed.

### Part 2: Session management

Sessions are server-side rows. The cookie just holds an opaque `session_id`.

**Cookie:**
- Name: `sprint_reporter_session`
- Value: `session_id` (32-byte random hex)
- Flags: `HttpOnly`, `SameSite=Lax`, `Secure` (controlled by env var `COOKIE_SECURE`, default `true`; set to `false` for `localhost` HTTP dev)
- Max-Age: 30 days (matches `expires_at`)

**Rolling expiry:** On every authenticated request, middleware updates `sessions.expires_at = now + 30 days` and `sessions.last_seen = now`. So as long as the user comes back within 30 days, they stay logged in indefinitely.

**Session lookup happens in middleware (FastAPI dependency `get_current_user`):**

```python
async def get_current_user(request: Request) -> User:
    session_id = request.cookies.get("sprint_reporter_session")
    if not session_id:
        raise HTTPException(status_code=401, detail="not_authenticated")
    row = db.execute(
        "SELECT * FROM sessions WHERE session_id = ? AND expires_at > ?",
        (session_id, now_iso()),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="session_expired")
    # roll
    db.execute(
        "UPDATE sessions SET expires_at = ?, last_seen = ? WHERE session_id = ?",
        (iso(now + 30 days), now_iso(), session_id),
    )
    user = load_user(row["user_id"])
    request.state.user = user
    request.state.active_workspace_id = row["active_workspace_id"]
    request.state.user_client = ClickUpClient(decrypt_token(load_token(user.id)))
    return user
```

Routes that need auth declare `user: User = Depends(get_current_user)`. Public routes (`/auth/login`, `/auth/callback`, `/static/*`, `/health`) don't.

A 401 response on browser navigation gets caught by a small handler that converts it to a redirect to `/auth/login`. 401 on JSON/AJAX requests (the dashboard's fetch calls) returns a JSON error so the JS toast layer can show "Session utgången, logga in igen".

### Part 3: Token storage & encryption

Tokens never go in cookies. They live in `user_tokens.encrypted_access_token` encrypted with Fernet (symmetric AES-128-CBC + HMAC-SHA256, from `cryptography` package — already part of FastAPI's transitive deps).

```python
from cryptography.fernet import Fernet

_fernet = Fernet(os.environ["SESSION_ENCRYPTION_KEY"].encode())

def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()

def decrypt_token(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
```

**Key generation:** One-time:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Result goes in `.env` as `SESSION_ENCRYPTION_KEY=...`. If this key is rotated, all stored tokens become unreadable → next API call returns "decryption failed" → user is logged out and must re-login. That's acceptable; the key shouldn't rotate often.

### Part 4: ClickUp client refactor

`src/clickup_client.py` currently builds the auth header from a single env-derived API key. We split into two factory functions:

```python
def get_system_client() -> ClickUpClient:
    """For background jobs (cron). Uses CLICKUP_SERVICE_API_KEY."""
    key = os.environ.get("CLICKUP_SERVICE_API_KEY") or get_clickup_api_key()  # legacy fallback
    return ClickUpClient(api_key=key)

def get_user_client(token: str) -> ClickUpClient:
    """For UI requests. Uses the signed-in user's OAuth token.
    OAuth tokens go in the same Authorization header — same wire format."""
    return ClickUpClient(api_key=token)
```

`ClickUpClient.__init__` is unchanged — it just stores whatever string it gets in `self.headers["Authorization"]`. ClickUp accepts both API keys and OAuth bearer tokens with the same header (no `Bearer` prefix needed for ClickUp specifically).

**Routes are updated to use `request.state.user_client` instead of constructing a fresh client.** This means any existing route handler that does:

```python
client = ClickUpClient(api_key=get_clickup_api_key())
```

becomes:

```python
client = request.state.user_client
```

The daily snapshot job (and any other cron) keeps using `get_system_client()`.

### Part 5: Workspace scoping

Each `teams` row gets a `workspace_id` column. UI queries filter by `active_workspace_id`:

```sql
SELECT * FROM teams WHERE workspace_id = ?
```

The team list page shows only teams in the selected workspace. The "Sync from ClickUp" button creates new teams with `workspace_id = active_workspace_id`. If a user switches workspace (we don't expose UI for this in v1, but we will via a workspace picker in the header for future flexibility), they see a different set of teams.

**Workspace switcher** is rendered in the header bar when `len(user.workspaces) > 1`. It's a simple `<select>` that POSTs to `/auth/workspace` and reloads. v1 ships this but minimally styled.

### `app_settings` schema

No changes from Initiative 1A. New tables and columns are independent.

## Files changed

| File | Action |
|---|---|
| `src/auth/__init__.py` | Create — package init |
| `src/auth/oauth.py` | Create — `build_authorize_url()`, `exchange_code()`, `fetch_user()`, `fetch_workspaces()` |
| `src/auth/session.py` | Create — `create_session()`, `get_session()`, `delete_session()`, `roll_session()` |
| `src/auth/encryption.py` | Create — Fernet wrapper |
| `src/auth/middleware.py` | Create — `get_current_user` FastAPI dependency, 401-to-redirect handler |
| `src/routes/auth_routes.py` | Create — `/auth/login`, `/auth/callback`, `/auth/workspace`, `/auth/logout` |
| `src/clickup_client.py` | Modify — split into `get_system_client()` and `get_user_client(token)` |
| `src/db.py` | Modify — add migrations for `users`, `user_tokens`, `sessions`, `oauth_state`, `teams.workspace_id` |
| `app.py` | Modify — register auth router, install middleware, update existing routes to use `request.state.user_client`, register 401 redirect handler |
| `templates/auth/login.html` | Create — landing page with "Sign in with ClickUp" button |
| `templates/auth/workspace.html` | Create — workspace picker (when user has >1) |
| `templates/base.html` | Modify — add user identity to header (name, avatar, logout button), workspace switcher when applicable |
| `requirements.txt` | Modify — pin `cryptography>=42` (likely already transitive but make it explicit) |
| `.env.example` | Modify — document new vars |

## Edge cases

- **First-ever login on a fresh DB.** No existing teams, no existing snapshots. User logs in, picks workspace, lands on dashboard with empty state and "Sync from ClickUp" CTA. Same as today's empty-state path, just behind auth.
- **Existing teams from pre-OAuth deployment.** On first migration, `teams.workspace_id` is NULL for existing rows. Migration backfills by hitting service-API `/team/{team_id}` for each existing team, populating the workspace_id. If migration can't reach ClickUp at boot, it logs an error and leaves rows NULL — those teams won't show in any workspace until a manual re-sync. Better than crashing the boot.
- **Token revoked by user in ClickUp settings.** Next API call returns 401. The retry logic from Initiative 1A doesn't retry 401s (4xx is caller's fault). Caught by an exception handler in middleware that detects ClickUpError with status 401, deletes the user's `user_tokens` and `sessions` rows, returns 401 to the browser, redirect to login.
- **User in 0 workspaces.** Defensive: ClickUp doesn't really let this happen, but if `/team` returns empty, redirect to a friendly "no_workspaces" error page with a sign-out link.
- **Concurrent logins from multiple devices.** Multiple `sessions` rows for the same `user_id`. Each has its own session_id and expiry. Logging out on one device doesn't log out the others. Acceptable.
- **Server restart.** Sessions are DB-backed → survive restart. `oauth_state` rows older than 10 minutes are stale-but-harmless (next `/auth/login` call cleans them).
- **Two users authorize from the same browser back-to-back.** Each gets their own `oauth_state` row keyed by random state. Each `/auth/callback` looks up by its own state. No collision.
- **Cookie cleared in browser.** User loses session-id reference. The `sessions` row stays in DB until expired. No security impact (session_id is the bearer; without it nobody can use the row). Cleaned up by the natural 30-day expiry. We could add a periodic cleanup task; not required.
- **`SESSION_ENCRYPTION_KEY` rotated.** All `user_tokens` ciphertext becomes unreadable. The decrypt call raises → middleware catches → forces re-login. Existing `sessions` rows still work for routes that don't need a token (login/logout), but any ClickUp API call fails until re-login. Acceptable; rotate during a planned re-login event.
- **OAuth callback receives error from ClickUp** (`?error=access_denied`). User clicked "Deny" on the consent screen. Show a friendly error page with a "Try again" link to `/auth/login`.
- **`OAUTH_REDIRECT_URI` mismatch with ClickUp app config.** ClickUp returns an error before redirecting back. User sees ClickUp's error page, not ours. Hard to mitigate from our side except documentation.
- **Background snapshot job during user-token rollout.** Cron uses `CLICKUP_SERVICE_API_KEY` from env. If that's missing, fall back to legacy `get_clickup_api_key()` which reads `app_settings`. Logs a warning to remind us to migrate.

## Verification

Manual + scry-driven on the dev Mac:

1. **Login flow** — open `http://localhost:8000`, expect 302 to `/auth/login`. Click "Sign in with ClickUp", authorize in ClickUp's UI, expect callback to land on workspace picker (if >1) or dashboard. Verify `users`, `user_tokens`, `sessions` rows exist in DB.
2. **Token usage** — load a sprint page, watch `app.log` for the request. Verify the `Authorization` header in the outgoing httpx request matches the OAuth token (not the service key) — log this at DEBUG temporarily.
3. **Logout** — click "Sign out". Verify session row is deleted, cookie is cleared, browser bounces to `/auth/login`. Refresh: still on login (no zombie session).
4. **Token revocation** — go to ClickUp settings → revoke the app. Reload dashboard. Verify clean redirect to `/auth/login` and the user's `user_tokens` and `sessions` rows are gone.
5. **Workspace switch** — for a user with multiple workspaces, switch via the header dropdown. Verify dashboard now shows that workspace's teams (initially empty if first time).
6. **Concurrent login** — log in on two browsers as same user. Verify both sessions work. Logout on one. Verify other still works.
7. **Background snapshot** — restart app. Verify `Daily snapshot job done` log line uses service key (logging metadata: `using service client` log line we'll add). Verify it works even with no users logged in.
8. **Encryption** — open `app.db` with `sqlite3`, check `user_tokens.encrypted_access_token` looks like `gAAAAA...` Fernet ciphertext, not a plain `pk_...` token.

## Distribution

Standard deploy bundle from Initiative 1A's process. **One-time deploy steps on live Mac:**

1. Stop app.
2. Add new env vars to `.env` (see `.env.example`).
3. Generate `SESSION_ENCRYPTION_KEY` (one command).
4. Generate ClickUp OAuth app via ClickUp UI; copy `client_id` and `client_secret` to `.env`.
5. Configure `OAUTH_REDIRECT_URI` to match your hosting URL (later: Azure URL; now: localhost or Tailscale).
6. Rename `CLICKUP_API_KEY` → `CLICKUP_SERVICE_API_KEY` in `.env` (or leave both during transition; legacy code path falls back).
7. Start app. First boot runs migrations. Backfills `teams.workspace_id`. Logs progress.
8. First user (you) signs in. Verify everything works. Roll out URL to colleagues.

No DB rollback required — all schema changes are additive (new tables, new column with NULL default).
