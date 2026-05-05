# Per-User Team Favorites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user team favorites with a ★ button on team cards and a "★ Your Favorites" section on the home page.

**Architecture:** New `user_favorites` table (FKs to `users` and `teams`, both CASCADE). New `favorites_service` exposes toggle + lookup. `home_service` accepts `user_id` and threads `is_favorite` into team cards plus a top-level `favorites` list. Frontend uses event delegation on `.favorite-btn` to POST and flip the icon.

**Tech Stack:** FastAPI, SQLite, Jinja2, vanilla JS (no new deps).

**Spec reference:** `docs/superpowers/specs/2026-05-05-team-favorites-design.md`

---

## File structure

| File | What changes |
|---|---|
| `src/database.py` | Add `user_favorites` CREATE TABLE + index inside `init_db` |
| `src/services/favorites_service.py` | Create — `toggle_favorite`, `get_favorite_team_ids`, `get_favorited_teams` |
| `src/routes/teams.py` | Add `POST /{team_id}/favorite` route |
| `src/services/home_service.py` | `_team_card` accepts `favorite_ids: set[int]`; `build_workspace_overview` and `build_area_detail` accept `user_id`; overview returns `favorites` |
| `src/routes/pages.py` | `home` and `area_page` pass `user["id"]` into home_service |
| `templates/area.html` | ★ button on each team card |
| `templates/home.html` | `{% if favorites %}` section above areas grid + ★ button on cards inside it |
| `static/style.css` | `.favorite-btn`, `.favorites-section`, `.favorites-header`, `.team-card` gains `position: relative` |
| `static/dashboard.js` | Append click delegator that POSTs and updates the icon |
| `templates/base.html`, `templates/auth/error.html`, `templates/auth/workspace.html` | Cache bump `v=9` → `v=10` |

No new dependencies.

---

## Notes for the implementer

**Run tests:**
```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ -v
```
Baseline: 82 passed.

**App restart:** `./stop.sh && ./start.sh`. Local `.env` has `AUTH_BYPASS=true`, so the synthetic `dev_bypass` user is what writes to `user_favorites` during local testing.

**Important:** the synthetic `dev_bypass` user is NOT in the `users` table. Tests for the favorites_service should NOT rely on a `users` row existing — but the FK constraint on `user_favorites.user_id` means an INSERT will fail without one. Solution: tests insert a `users` row in their fixture. The runtime AUTH_BYPASS path needs us to either (a) ensure `dev_bypass` exists as a `users` row, or (b) make `user_favorites.user_id` not enforce the FK. We pick (a) — Task 4 ensures the dev user is upserted at startup time when AUTH_BYPASS is on.

**Conventional Commits.** One commit per task.

---

### Task 1: Add `user_favorites` table to schema

**Files:**
- Modify: `src/database.py`
- Test: `tests/test_auth_database.py` (extend existing test file)

- [ ] **Step 1: Append the test**

Add to the END of `tests/test_auth_database.py`:

```python
def test_init_db_creates_user_favorites_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = get_connection(db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_favorites)").fetchall()}
    indexes = {r["name"] for r in conn.execute("PRAGMA index_list(user_favorites)").fetchall()}
    conn.close()
    assert cols == {"user_id", "team_id", "created_at"}
    # PRIMARY KEY composite + the named index = at least 2 indexes
    assert any("idx_user_favorites_user" in i for i in indexes)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/test_auth_database.py::test_init_db_creates_user_favorites_table -v
```

Expected: FAIL — table doesn't exist.

- [ ] **Step 3: Add the CREATE TABLE inside `init_db`**

In `src/database.py`, find the existing `executescript("""...""")` block (the big multi-table one). Add inside that block, alongside the other `CREATE TABLE IF NOT EXISTS` statements (e.g., right after the `oauth_state` table definition):

```sql
CREATE TABLE IF NOT EXISTS user_favorites (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_user_favorites_user ON user_favorites(user_id);
```

- [ ] **Step 4: Run tests to verify pass**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/test_auth_database.py -v
```

Expected: 8 PASSED (7 existing + 1 new).

Then run full suite:
```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `83 passed`.

- [ ] **Step 5: Verify migration runs cleanly on existing DB**

```bash
./.venv/bin/python -c "
from src.database import init_db, get_connection
init_db('./sprint_data.db')
conn = get_connection('./sprint_data.db')
cols = {r[1] for r in conn.execute('PRAGMA table_info(user_favorites)').fetchall()}
conn.close()
assert cols == {'user_id', 'team_id', 'created_at'}, cols
print('OK — user_favorites table exists on production-like DB')
"
```

Expected: `OK — user_favorites table exists on production-like DB`.

- [ ] **Step 6: Commit**

```bash
git add src/database.py tests/test_auth_database.py
git commit -m "feat(favorites): add user_favorites table"
```

---

### Task 2: Create `favorites_service` module

**Files:**
- Create: `src/services/favorites_service.py`
- Create: `tests/test_favorites_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_favorites_service.py`:

```python
import pytest
from datetime import datetime


@pytest.fixture(autouse=True)
def _setup(monkeypatch, tmp_path):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db)
    import importlib, src.config, src.services.favorites_service
    importlib.reload(src.config)
    importlib.reload(src.services.favorites_service)
    from src.database import init_db, get_connection
    init_db(db)
    # Insert prerequisite rows: a user and a team. The user_favorites FKs require both.
    conn = get_connection(db)
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO users (id, email, username, color, profile_picture, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("u1", "a@x.se", "anna", None, None, now, now),
    )
    conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id) "
        "VALUES (?, ?, ?, ?)",
        ("LAN", "ws1", "sp1", "fld1"),
    )
    conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id) "
        "VALUES (?, ?, ?, ?)",
        ("WAN", "ws1", "sp1", "fld2"),
    )
    conn.commit()
    conn.close()
    yield


def test_toggle_favorite_adds_then_removes():
    from src.services.favorites_service import toggle_favorite, get_favorite_team_ids
    assert get_favorite_team_ids("u1") == set()
    assert toggle_favorite("u1", 1) is True
    assert get_favorite_team_ids("u1") == {1}
    assert toggle_favorite("u1", 1) is False
    assert get_favorite_team_ids("u1") == set()


def test_toggle_favorite_independent_per_user():
    from src.services.favorites_service import toggle_favorite, get_favorite_team_ids
    from src.database import get_connection
    from src.config import DB_PATH
    from datetime import datetime
    conn = get_connection(DB_PATH)
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO users (id, email, username, color, profile_picture, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("u2", "b@x.se", "bjorn", None, None, now, now),
    )
    conn.commit()
    conn.close()
    toggle_favorite("u1", 1)
    toggle_favorite("u2", 2)
    assert get_favorite_team_ids("u1") == {1}
    assert get_favorite_team_ids("u2") == {2}


def test_get_favorited_teams_returns_full_team_rows():
    from src.services.favorites_service import toggle_favorite, get_favorited_teams
    toggle_favorite("u1", 1)
    toggle_favorite("u1", 2)
    teams = get_favorited_teams("u1")
    assert len(teams) == 2
    names = {t["name"] for t in teams}
    assert names == {"LAN", "WAN"}
    # Returned rows should look like team_service.get_all_teams() rows
    assert all("clickup_space_id" in t for t in teams)


def test_get_favorited_teams_empty_for_unknown_user():
    from src.services.favorites_service import get_favorited_teams
    assert get_favorited_teams("never_existed") == []


def test_team_delete_cascades_to_favorites():
    from src.services.favorites_service import toggle_favorite, get_favorite_team_ids
    from src.database import get_connection
    from src.config import DB_PATH
    toggle_favorite("u1", 1)
    assert get_favorite_team_ids("u1") == {1}
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM teams WHERE id = 1")
    conn.commit()
    conn.close()
    assert get_favorite_team_ids("u1") == set()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/test_favorites_service.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/services/favorites_service.py`**

```python
"""Per-user team favorites: toggle, lookup, and joined retrieval."""
from datetime import datetime
from src.config import DB_PATH
from src.database import get_connection


def _now() -> str:
    return datetime.utcnow().isoformat()


def toggle_favorite(user_id: str, team_id: int) -> bool:
    """Toggle favorite. Returns True if now favorited, False if just un-favorited."""
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT 1 FROM user_favorites WHERE user_id = ? AND team_id = ?",
        (user_id, team_id),
    ).fetchone()
    if row:
        conn.execute(
            "DELETE FROM user_favorites WHERE user_id = ? AND team_id = ?",
            (user_id, team_id),
        )
        result = False
    else:
        conn.execute(
            "INSERT INTO user_favorites (user_id, team_id, created_at) VALUES (?, ?, ?)",
            (user_id, team_id, _now()),
        )
        result = True
    conn.commit()
    conn.close()
    return result


def get_favorite_team_ids(user_id: str) -> set[int]:
    """Return the set of team IDs the given user has favorited.
    Empty set if user has no favorites or doesn't exist."""
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT team_id FROM user_favorites WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    return {r["team_id"] for r in rows}


def get_favorited_teams(user_id: str) -> list[dict]:
    """Return the user's favorited teams as full team rows, ordered by team name.
    Joined against the teams table; teams that no longer exist are excluded by INNER JOIN."""
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        """
        SELECT t.* FROM teams t
        INNER JOIN user_favorites f ON f.team_id = t.id
        WHERE f.user_id = ?
        ORDER BY LOWER(t.name)
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/test_favorites_service.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `88 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/services/favorites_service.py tests/test_favorites_service.py
git commit -m "feat(favorites): favorites_service module with toggle + lookups"
```

---

### Task 3: Add `POST /teams/{team_id}/favorite` route

**Files:**
- Modify: `src/routes/teams.py`

- [ ] **Step 1: Read current state of the file**

```bash
grep -n "team_service.get_team\|@router.delete\|@router.post" /Users/collin/dev/Projects/ClickUp-report-app/src/routes/teams.py | head -10
```

The new route goes near the bottom, after `sync_sprints`.

- [ ] **Step 2: Add the route**

Find the end of the `sync_sprints` function in `src/routes/teams.py` (around line 87, the line with `return {"synced": ..., "sprints": ...}`). Add the new route directly below.

Use Edit:
- old_string: `    return {"synced": len(synced), "sprints": synced}`
- new_string:
```python
    return {"synced": len(synced), "sprints": synced}


@router.post("/{team_id}/favorite")
def toggle_team_favorite(team_id: int, request: Request,
                         user=Depends(get_current_user)):
    """Toggle the current user's favorite status on this team.
    Returns {"favorited": bool}. 404 if the team is missing or not in the
    user's active workspace."""
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    active_ws = request.state.active_workspace_id
    # Workspace check: avoid leaking team existence across workspaces.
    if active_ws and team.get("workspace_id") and team["workspace_id"] != active_ws:
        raise HTTPException(404, "Team not found")
    from src.services.favorites_service import toggle_favorite
    favorited = toggle_favorite(user["id"], team_id)
    return {"favorited": favorited}
```

- [ ] **Step 3: Smoke-test**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
# Toggle on team 1 (LAN)
curl -s --max-time 3 -X POST http://localhost:8000/teams/1/favorite
# Toggle again (should flip)
curl -s --max-time 3 -X POST http://localhost:8000/teams/1/favorite
# Unknown team
curl -s --max-time 3 -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/teams/9999/favorite
```

Expected:
- First call: `{"favorited":true}`
- Second call: `{"favorited":false}`
- Unknown: `404`

If the first call returns 500 with FK violation on `user_id`, that means the `dev_bypass` user isn't in the `users` table. That's fixed in Task 4 — for now, manually upsert it:

```bash
./.venv/bin/python -c "
from src.auth.users import upsert_user
upsert_user(id='dev_bypass', email='dev@localhost', username='Dev (bypass)', color='#888888', profile_picture=None)
print('OK — dev_bypass user upserted')
"
```

Then re-run the curl tests.

- [ ] **Step 4: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `88 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/routes/teams.py
git commit -m "feat(favorites): POST /teams/{id}/favorite toggle route"
```

---

### Task 4: Auto-upsert dev_bypass user on startup

**Files:**
- Modify: `app.py`

The synthetic `dev_bypass` user from AUTH_BYPASS doesn't have a row in the `users` table — which breaks the FK on `user_favorites`. Ensure it exists at startup when AUTH_BYPASS is on.

- [ ] **Step 1: Add upsert in lifespan**

In `app.py`, find the `lifespan` function. The existing AUTH_BYPASS warning log line is around there. Use Edit:

- old_string:
```python
    from src.config import AUTH_BYPASS
    if AUTH_BYPASS:
        log.warning("AUTH_BYPASS is ON — every request is treated as 'Dev (bypass)' user. NEVER deploy to production with this on.")
    init_db(DB_PATH)
```
- new_string:
```python
    from src.config import AUTH_BYPASS
    if AUTH_BYPASS:
        log.warning("AUTH_BYPASS is ON — every request is treated as 'Dev (bypass)' user. NEVER deploy to production with this on.")
    init_db(DB_PATH)
    if AUTH_BYPASS:
        # The synthetic dev user must exist in the users table so foreign keys
        # (e.g., user_favorites.user_id) hold. Idempotent; safe across restarts.
        from src.auth.users import upsert_user
        upsert_user(id="dev_bypass", email="dev@localhost",
                    username="Dev (bypass)", color="#888888",
                    profile_picture=None)
```

- [ ] **Step 2: Restart and verify**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
./.venv/bin/python -c "
from src.auth.users import get_user
u = get_user('dev_bypass')
assert u is not None, 'dev_bypass not in users table!'
print('OK — dev_bypass user present:', u['username'])
"
```

Expected: `OK — dev_bypass user present: Dev (bypass)`.

Then re-run the toggle curl tests from Task 3:
```bash
curl -s --max-time 3 -X POST http://localhost:8000/teams/1/favorite
curl -s --max-time 3 -X POST http://localhost:8000/teams/1/favorite
```

Expected: `{"favorited":true}` then `{"favorited":false}`.

- [ ] **Step 3: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `88 passed`.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat(favorites): upsert dev_bypass user on startup so FK holds"
```

---

### Task 5: Thread `is_favorite` + `favorites` through `home_service`

**Files:**
- Modify: `src/services/home_service.py`

Add a `favorite_ids` parameter to `_team_card` and a `user_id` parameter to both public functions. `build_workspace_overview` returns a new top-level `favorites` list.

- [ ] **Step 1: Update `_team_card` to mark favorited teams**

In `src/services/home_service.py`, find `_team_card` (around line 50). Use Edit:
- old_string:
```python
def _team_card(team: dict) -> dict:
    """Build the per-team card payload."""
    sprints = get_team_sprints(team["id"])
```
- new_string:
```python
def _team_card(team: dict, favorite_ids: set[int] | None = None) -> dict:
    """Build the per-team card payload.
    `favorite_ids` is the set of team IDs the current user has favorited
    (used to render filled vs empty stars). Defaults to empty."""
    favorite_ids = favorite_ids or set()
    sprints = get_team_sprints(team["id"])
```

Then find the `return` block at the end of `_team_card`. Use Edit:
- old_string:
```python
    return {
        "id": team["id"],
        "name": team["name"],
        "metric_type": team.get("metric_type", "task_count"),
        "active_sprint": active_card,
        "last_closed": last_closed,
        "velocity_sparkline": sparkline,
        "_closed_count": len(closed_sprints),
        "_closed_summaries": [get_sprint_summary(s["id"]) for s in closed_sorted],
    }
```
- new_string:
```python
    return {
        "id": team["id"],
        "name": team["name"],
        "metric_type": team.get("metric_type", "task_count"),
        "active_sprint": active_card,
        "last_closed": last_closed,
        "velocity_sparkline": sparkline,
        "is_favorite": team["id"] in favorite_ids,
        "_closed_count": len(closed_sprints),
        "_closed_summaries": [get_sprint_summary(s["id"]) for s in closed_sorted],
    }
```

- [ ] **Step 2: Update `build_workspace_overview` to accept `user_id` and return `favorites`**

Find the `async def build_workspace_overview` (around line 210). Use Edit:
- old_string:
```python
async def build_workspace_overview(client, teams: list[dict]) -> dict:
    """Level-1 (home) context. Mutates `teams` in place via backfill if needed.

    Returns:
        {
          "workspace": {...},
          "areas": [
            {
              "space_id": str | None, "space_name": str,
              "team_count": int,
              "stats": {active_sprints, closed_sprints, avg_velocity, avg_completion},
              "completion_sparkline": [int...],  # last 12 sprint completion %s
              "last_activity": str,
            },
            ...
          ],
        }
    """
    await _backfill_space_names(client, teams)
    pairs = [(t, _team_card(t)) for t in teams]
```
- new_string:
```python
async def build_workspace_overview(client, teams: list[dict], user_id: str) -> dict:
    """Level-1 (home) context. Mutates `teams` in place via backfill if needed.

    Returns:
        {
          "workspace": {...},
          "favorites": [<team_card>, ...],  # may be empty
          "areas": [
            {
              "space_id": str | None, "space_name": str,
              "team_count": int,
              "stats": {active_sprints, closed_sprints, avg_velocity, avg_completion},
              "completion_sparkline": [int...],  # last 12 sprint completion %s
              "last_activity": str,
            },
            ...
          ],
        }
    """
    from src.services.favorites_service import get_favorite_team_ids
    favorite_ids = get_favorite_team_ids(user_id)
    await _backfill_space_names(client, teams)
    pairs = [(t, _team_card(t, favorite_ids)) for t in teams]
```

Then find the `return {"workspace": workspace, "areas": areas}` line at the end of `build_workspace_overview`. Use Edit:
- old_string:
```python
    return {"workspace": workspace, "areas": areas}
```
- new_string:
```python
    # Build the favorites list: only teams in scope (passed-in `teams`) AND favorited.
    teams_by_id = {t["id"]: t for t in teams}
    favorites_cards: list[dict] = []
    for fid in favorite_ids:
        if fid in teams_by_id:
            # Reuse the already-built card from `pairs` rather than re-computing.
            for t, card in pairs:
                if t["id"] == fid:
                    favorites_cards.append(_strip_internal(card))
                    break
    favorites_cards.sort(key=lambda c: str(c.get("name") or "").lower())

    return {"workspace": workspace, "favorites": favorites_cards, "areas": areas}
```

- [ ] **Step 3: Update `build_area_detail` to accept `user_id`**

Find `async def build_area_detail` (around line 266). Use Edit:
- old_string:
```python
async def build_area_detail(client, teams: list[dict], space_id: str) -> dict | None:
    """Level-2 (area page) context. Returns None if no team in the workspace
    matches `space_id`.

    Returns:
        {
          "area": {space_id, space_name, team_count, stats},
          "teams": [<team_card>, ...],
        }
    """
    await _backfill_space_names(client, teams)
    in_area = [t for t in teams if (t.get("clickup_space_id") or "") == space_id]
    if not in_area:
        return None

    pairs = [(t, _team_card(t)) for t in in_area]
```
- new_string:
```python
async def build_area_detail(client, teams: list[dict], space_id: str,
                            user_id: str) -> dict | None:
    """Level-2 (area page) context. Returns None if no team in the workspace
    matches `space_id`.

    Returns:
        {
          "area": {space_id, space_name, team_count, stats},
          "teams": [<team_card>, ...],
        }
    """
    from src.services.favorites_service import get_favorite_team_ids
    favorite_ids = get_favorite_team_ids(user_id)
    await _backfill_space_names(client, teams)
    in_area = [t for t in teams if (t.get("clickup_space_id") or "") == space_id]
    if not in_area:
        return None

    pairs = [(t, _team_card(t, favorite_ids)) for t in in_area]
```

- [ ] **Step 4: Smoke-test the service**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
./.venv/bin/python <<'PY'
import asyncio
from src.services.team_service import get_all_teams
from src.services.favorites_service import toggle_favorite, get_favorite_team_ids
from src.services.home_service import build_workspace_overview, build_area_detail
from src.clickup_client import get_system_client

async def main():
    teams = get_all_teams()
    # Clear existing favorites for clean test
    for tid in list(get_favorite_team_ids("dev_bypass")):
        toggle_favorite("dev_bypass", tid)
    # Favorite the first 2 teams
    toggle_favorite("dev_bypass", teams[0]["id"])
    toggle_favorite("dev_bypass", teams[1]["id"])

    ov = await build_workspace_overview(get_system_client(), teams, "dev_bypass")
    print(f"favorites count: {len(ov['favorites'])}")
    for f in ov["favorites"]:
        print(f"  fav: {f['name']} (is_favorite={f['is_favorite']})")
    print("areas count:", len(ov["areas"]))
    print("teams in first area, is_favorite flags:")
    for t in ov["areas"][0]["teams"] if ov["areas"] else []:
        print(f"  {t['name']}: is_favorite={t['is_favorite']}")

    # Cleanup
    for tid in list(get_favorite_team_ids("dev_bypass")):
        toggle_favorite("dev_bypass", tid)

asyncio.run(main())
PY
```

Expected:
- `favorites count: 2`
- Two `fav:` lines with `is_favorite=True`
- `teams in first area` block where the first 2 teams (alphabetically) have `is_favorite=True`, others False

- [ ] **Step 5: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `88 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/services/home_service.py
git commit -m "feat(favorites): thread is_favorite + favorites through home_service"
```

---

### Task 6: Update `pages.py` route handlers

**Files:**
- Modify: `src/routes/pages.py`

Both `home` and `area_page` now need to pass `user["id"]` into the home_service calls.

- [ ] **Step 1: Update `home` route**

Find the `home` function in `src/routes/pages.py`. Use Edit:
- old_string:
```python
    from src.services.home_service import build_workspace_overview
    overview = await build_workspace_overview(request.state.user_client, teams)
    return templates.TemplateResponse(
        "home.html",
        _ctx(request, workspace=overview["workspace"], areas=overview["areas"]),
    )
```
- new_string:
```python
    from src.services.home_service import build_workspace_overview
    overview = await build_workspace_overview(request.state.user_client, teams, user["id"])
    return templates.TemplateResponse(
        "home.html",
        _ctx(request, workspace=overview["workspace"],
             favorites=overview["favorites"], areas=overview["areas"]),
    )
```

- [ ] **Step 2: Update `area_page` route**

Use Edit:
- old_string:
```python
    from src.services.home_service import build_area_detail
    detail = await build_area_detail(request.state.user_client, teams, space_id)
```
- new_string:
```python
    from src.services.home_service import build_area_detail
    detail = await build_area_detail(request.state.user_client, teams, space_id, user["id"])
```

- [ ] **Step 3: Smoke-test routes**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
curl -s --max-time 3 -o /dev/null -w "home: %{http_code}\n" http://localhost:8000/
curl -s --max-time 3 -o /dev/null -w "area: %{http_code}\n" http://localhost:8000/areas/90120495342
```

Expected: both `200`.

- [ ] **Step 4: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `88 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/routes/pages.py
git commit -m "feat(favorites): pass user_id from routes into home_service"
```

---

### Task 7: Add ★ button to team cards + favorites section to home

**Files:**
- Modify: `templates/area.html`
- Modify: `templates/home.html`
- Modify: `static/style.css`
- Modify: `static/dashboard.js`
- Modify: `templates/base.html`, `templates/auth/error.html`, `templates/auth/workspace.html` (cache bump)

- [ ] **Step 1: Add ★ button markup to `templates/area.html`**

Find the `team-card-title` line in the area template. Use Edit:
- old_string:
```html
  <article class="team-card">
    <h3 class="team-card-title">{{ team.name }}</h3>
```
- new_string:
```html
  <article class="team-card">
    <button class="favorite-btn{% if team.is_favorite %} favorite-btn--on{% endif %}"
            data-team-id="{{ team.id }}"
            aria-label="{% if team.is_favorite %}Unfavorite{% else %}Favorite{% endif %} {{ team.name }}"
            title="{% if team.is_favorite %}Unfavorite{% else %}Favorite{% endif %}">
      {% if team.is_favorite %}★{% else %}☆{% endif %}
    </button>
    <h3 class="team-card-title">{{ team.name }}</h3>
```

- [ ] **Step 2: Add favorites section + ★ button to `templates/home.html`**

The current `home.html` jumps from `</section>` (workspace banner) directly into `<div class="team-grid">` (areas). Insert a favorites section between them.

Use Edit:
- old_string:
```html
  <div class="banner-stat banner-meta">last activity: {{ workspace.last_activity }}</div>
</section>

<div class="team-grid">
  {% for area in areas %}
```
- new_string:
```html
  <div class="banner-stat banner-meta">last activity: {{ workspace.last_activity }}</div>
</section>

{% if favorites %}
<section class="favorites-section">
  <header class="favorites-header">
    <h2 class="favorites-title">★ Your Favorites</h2>
    <span class="favorites-count">{{ favorites | length }} team{{ 's' if favorites|length != 1 else '' }}</span>
  </header>
  <div class="team-grid">
    {% for team in favorites %}
    <article class="team-card">
      <button class="favorite-btn favorite-btn--on"
              data-team-id="{{ team.id }}"
              aria-label="Unfavorite {{ team.name }}"
              title="Unfavorite">★</button>
      <h3 class="team-card-title">{{ team.name }}</h3>

      {% if team.active_sprint %}
      <p class="team-card-status">
        <span class="badge-active">ACTIVE</span>
        <a href="/sprint/{{ team.active_sprint.id }}">{{ team.active_sprint.name | display_name }}</a>
      </p>
      {% elif team.last_closed %}
      <p class="team-card-status">
        Last sprint: <strong>{{ team.last_closed.name | display_name }}</strong>
        · {{ (team.last_closed.completion * 100) | round | int }}%
        · <span class="text-muted">{{ team.last_closed.ago }}</span>
      </p>
      {% else %}
      <p class="team-card-status text-muted">No sprints yet</p>
      {% endif %}

      <div class="sparkline-wrap">
        <canvas class="sparkline" data-points="{{ team.velocity_sparkline | tojson }}"></canvas>
      </div>

      <div class="team-card-actions">
        <a class="btn btn-secondary" href="/teams/{{ team.id }}/sprints">Sprint History</a>
        <a class="btn btn-secondary" href="/teams/{{ team.id }}/trends">Trends</a>
        <a class="btn btn-secondary" href="/teams/{{ team.id }}/settings">Settings</a>
      </div>
    </article>
    {% endfor %}
  </div>
</section>
{% endif %}

<div class="team-grid">
  {% for area in areas %}
```

- [ ] **Step 3: Append CSS rules to `static/style.css`**

Append to the END of `static/style.css`:

```css

/* === Favorites: ★ button on team cards === */
.team-card {
  position: relative;
}
.favorite-btn {
  position: absolute;
  top: 12px;
  right: 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  color: var(--fg-subtle, #94a3b8);
  padding: 4px 6px;
  border-radius: 4px;
  transition: color 0.15s ease, background 0.15s ease;
}
.favorite-btn:hover {
  color: var(--accent, #7b68ee);
  background: var(--accent-tint, rgba(123, 104, 238, 0.10));
}
.favorite-btn--on {
  color: var(--accent, #7b68ee);
}
.favorite-btn--on:hover {
  color: var(--accent-hover, #6647f0);
}
.team-card-title {
  /* leave room for the absolutely-positioned star */
  padding-right: 30px;
}

/* === Favorites: home-page section === */
.favorites-section {
  margin: 0 0 28px;
}
.favorites-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border, #e2e8f0);
}
.favorites-title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--accent, #7b68ee);
}
.favorites-count {
  font-size: 12px;
  color: var(--text-muted, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
```

- [ ] **Step 4: Append click delegator to `static/dashboard.js`**

Append to the END of `static/dashboard.js`:

```javascript

// === Favorites: toggle ★ via fetch (event delegation) ===
document.addEventListener('click', async function (e) {
  const btn = e.target.closest('.favorite-btn');
  if (!btn) return;
  e.preventDefault();
  const teamId = btn.dataset.teamId;
  if (!teamId) return;
  try {
    const resp = await fetch(`/teams/${teamId}/favorite`, { method: 'POST' });
    if (!resp.ok) {
      showToast('Could not update favorite', 'error');
      return;
    }
    const { favorited } = await resp.json();
    btn.textContent = favorited ? '★' : '☆';
    btn.title = favorited ? 'Unfavorite' : 'Favorite';
    btn.classList.toggle('favorite-btn--on', !!favorited);
    btn.setAttribute('aria-label', (favorited ? 'Unfavorite' : 'Favorite'));
  } catch (err) {
    showToast('Could not update favorite: ' + err.message, 'error');
  }
});
```

- [ ] **Step 5: Bump cache version v=9 → v=10**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
sed -i '' 's|style.css?v=9|style.css?v=10|g' \
  templates/base.html \
  templates/auth/error.html \
  templates/auth/workspace.html
grep "style.css?v=" templates/base.html templates/auth/error.html templates/auth/workspace.html
```

Expected: all 3 lines show `?v=10`.

- [ ] **Step 6: Restart + curl-verify markup**

```bash
./stop.sh && ./start.sh
sleep 1
# Area page: should have ★ buttons on each card
curl -s --max-time 3 http://localhost:8000/areas/90120495342 | grep -c "favorite-btn"
# Home: no favorites yet (assuming clean DB), section should not appear
curl -s --max-time 3 http://localhost:8000/ | grep -c "favorites-section"
```

Expected:
- Area: `4` (one per team card)
- Home: `0` (section hidden when no favorites)

Then favorite a team and re-check:
```bash
curl -s --max-time 3 -X POST http://localhost:8000/teams/1/favorite
curl -s --max-time 3 http://localhost:8000/ | grep -c "favorites-section"
```

Expected: `1` (section now visible).

Clean up:
```bash
curl -s --max-time 3 -X POST http://localhost:8000/teams/1/favorite
```

- [ ] **Step 7: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `88 passed`.

- [ ] **Step 8: Commit**

```bash
git add templates/area.html templates/home.html templates/base.html templates/auth/error.html templates/auth/workspace.html static/style.css static/dashboard.js
git commit -m "feat(favorites): ★ button on team cards + Your Favorites home section"
```

---

### Task 8: Visual verification with scry + push

**Files:** none (verification + push).

- [ ] **Step 1: Open home in scry, verify no favorites section**

Open `mcp__plugin_scry_scry__scry_open` with `url=http://localhost:8000/`. Snapshot inline. Confirm: workspace banner + Network Services area card. NO "Your Favorites" section (zero favorites).

- [ ] **Step 2: Navigate to area, click ★ on a team**

Navigate to `http://localhost:8000/areas/90120495342`. Snapshot. Confirm: ★ buttons (☆ outline) in top-right of each card.

Use `mcp__plugin_scry_scry__scry_click` with `target="LAN"` … actually clicking the star requires more precise targeting. Use evaluate instead:
```javascript
document.querySelector('.team-card .favorite-btn').click();
```

Then snapshot. Confirm: the star on the first card flipped to filled (★ in purple).

- [ ] **Step 3: Navigate home, verify favorites section appears**

Navigate to `http://localhost:8000/`. Snapshot. Confirm:
- "★ Your Favorites" section header above the area grid
- One team card visible (the one we starred), with full layout (sparkline, last sprint, buttons), and a filled ★ in the top-right
- The Network Services area card still shown below

- [ ] **Step 4: Cleanup**

Click the ★ on the favorites-section card to un-favorite. Reload home — the section should be hidden again.

Close scry: `mcp__plugin_scry_scry__scry_close`.

- [ ] **Step 5: Push**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
git push origin master
```

Expected: 8 commits pushed.

---

## Self-review checklist

**Spec coverage:**
- ✅ `user_favorites` table → Task 1
- ✅ `favorites_service` (toggle, get_ids, get_teams) → Task 2
- ✅ `POST /teams/{id}/favorite` route → Task 3
- ✅ AUTH_BYPASS dev_bypass user existence → Task 4
- ✅ `is_favorite` flag in `_team_card` → Task 5
- ✅ `favorites` list in `build_workspace_overview` → Task 5
- ✅ `user_id` parameter on both home_service public functions → Task 5
- ✅ Routes pass `user["id"]` → Task 6
- ✅ ★ button markup on cards → Task 7
- ✅ "Your Favorites" home section, hidden when empty → Task 7
- ✅ CSS for button + section → Task 7
- ✅ JS event delegator → Task 7
- ✅ Cache bump v=10 → Task 7

**Placeholder scan:** No "TBD" / "add error handling" / "similar to" patterns. Every Edit step has explicit code. Workspace check uses concrete `team["workspace_id"] != active_ws` rather than abstract authz.

**Type consistency:**
- `user_id` is `str` everywhere (matches `users.id TEXT`).
- `team_id` is `int` everywhere (matches `teams.id INTEGER PRIMARY KEY AUTOINCREMENT`).
- `favorite_ids` is `set[int]`, threaded into `_team_card` and consumed via `team["id"] in favorite_ids`.
- `is_favorite` is `bool`, lives on the team-card payload.
- `favorites` (the home-level key) is `list[dict]` of stripped team-card payloads.

**Known limitation flagged inline:** clicking ★ on the home favorites section flips the icon but does NOT remove the card from the section dynamically. The user sees the now-empty card stay in the favorites section until next page load. This is intentional per spec ("avoiding the awkward 'card animates out from under your cursor' feel"); v2 can add fade-out if user testing surfaces friction.
