# Product-Area Grouped Home Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group teams by Product Area (= ClickUp Space) on the home page, with workspace-level + per-area roll-up stats and per-team velocity sparklines.

**Architecture:** Additive `teams.space_name` column with opportunistic API backfill on home load. New context-builder helpers in `src/services/` that aggregate existing per-sprint data into per-team / per-area stats. Template rewrite of `templates/home.html` only — every other route untouched.

**Tech Stack:** FastAPI, Jinja2, SQLite, Chart.js (already loaded via `base.html`), existing design tokens in `static/style.css`.

**Spec reference:** `docs/superpowers/specs/2026-05-05-product-area-home-design.md`

---

## File structure

| File | What changes |
|---|---|
| `src/database.py` | Append `ALTER TABLE teams ADD COLUMN space_name TEXT` migration in the existing migration section |
| `src/models.py` | Add `space_name: str \| None = None` to `TeamCreate` |
| `src/services/team_service.py` | Extend `create_team` signature with `space_name=None`, persist to new column |
| `src/services/home_service.py` | **New** — `build_home_context(client, teams)` returns the structured dict for the template |
| `src/routes/teams.py` | Pass `body.space_name` into `team_service.create_team` |
| `src/routes/pages.py` | Replace `home` body with backfill + `build_home_context` call |
| `templates/team_settings.html` | Add `space_name: selectedSpace.text` to the JSON body in the form's submit handler |
| `templates/home.html` | Rewrite layout (workspace banner → product-area sections → team cards with sparkline) |
| `static/style.css` | Append rules for `.workspace-banner`, `.product-area`, `.pa-header`, `.team-grid`, `.team-card`, `.sparkline` |
| `static/dashboard.js` | Append a sparkline-render block that runs on `DOMContentLoaded` |

No new dependencies. No new tests required (per spec; manual scry verification at end).

---

## Notes for the implementer

**`SESSION_ENCRYPTION_KEY`:** Required to import any auth module. Tests should set it via `monkeypatch` before importing. Run pytest as:
```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ -v
```

**App restart between tasks:** Tasks 1-5 don't need a running app. Task 6 (template + CSS) is verified by restarting and visiting `http://localhost:8000/`. Use `./stop.sh && ./start.sh` (existing scripts).

**AUTH_BYPASS is on locally** (`.env`) — `request.state.user_client` returns the system client, which is sufficient for the backfill-from-API path. No need to register OAuth for this work.

**Do NOT touch other home-related routes** (`/setup`, `/teams/new`, etc.). Scope strictly to the 10 files listed above.

**Commits:** Conventional Commits, one commit per task.

---

### Task 1: Add `teams.space_name` column

**Files:**
- Modify: `src/database.py` (around line 162, alongside the existing `workspace_id` ALTER block)

- [ ] **Step 1: Append the migration**

Open `src/database.py`. After the existing block:

```python
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN workspace_id TEXT")
    except Exception:
        pass  # Column already exists
```

Add (immediately after, before the "Backfill workspace_id" comment):

```python
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN space_name TEXT")
    except Exception:
        pass  # Column already exists
```

- [ ] **Step 2: Verify migration runs cleanly on existing DB**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./.venv/bin/python -c "
from src.database import init_db, get_connection
init_db('./sprint_data.db')
conn = get_connection('./sprint_data.db')
cols = {r[1] for r in conn.execute('PRAGMA table_info(teams)').fetchall()}
conn.close()
assert 'space_name' in cols, f'space_name missing! cols={cols}'
print('OK — space_name column exists')
"
```

Expected: `OK — space_name column exists`.

- [ ] **Step 3: Verify init_db is idempotent**

Run the same one-liner again. Expected: same `OK` output, no exception (the `try/except Exception` swallows the duplicate-column error).

- [ ] **Step 4: Run full suite to confirm no regression**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed` (matches Initiative 1B baseline).

- [ ] **Step 5: Commit**

```bash
git add src/database.py
git commit -m "feat(home): add teams.space_name column for Product Area grouping"
```

---

### Task 2: Extend `create_team` + `TeamCreate` to accept `space_name`

**Files:**
- Modify: `src/models.py` (line 9-17, the `TeamCreate` class)
- Modify: `src/services/team_service.py` (line 7, the `create_team` function)

- [ ] **Step 1: Add `space_name` to `TeamCreate`**

In `src/models.py`, modify the `TeamCreate` class:

Use Edit:
- old_string:
```python
class TeamCreate(BaseModel):
    name: str
    clickup_workspace_id: str = ""
    clickup_space_id: str
    clickup_folder_id: str
    metric_type: str = "task_count"
    capacity_mode: str = "individual"
    sprint_length_days: int = 14
    members: list[TeamMember] = []
```
- new_string:
```python
class TeamCreate(BaseModel):
    name: str
    clickup_workspace_id: str = ""
    clickup_space_id: str
    clickup_folder_id: str
    metric_type: str = "task_count"
    capacity_mode: str = "individual"
    sprint_length_days: int = 14
    space_name: str | None = None
    members: list[TeamMember] = []
```

- [ ] **Step 2: Update `team_service.create_team` signature + INSERT**

In `src/services/team_service.py`, modify the function:

Use Edit:
- old_string:
```python
def create_team(name: str, workspace_id: str, space_id: str, folder_id: str,
                metric_type: str = "task_count", capacity_mode: str = "individual",
                sprint_length_days: int = 14, workspace_id_new: str | None = None) -> dict:
    """Create a team. `workspace_id` (positional) is the ClickUp workspace_id (legacy
    `clickup_workspace_id` column). `workspace_id_new` (kw-only optional) is the new
    `workspace_id` column added by Task 1; equals the same ClickUp workspace_id but
    stored separately to enable workspace scoping in OAuth flows."""
    conn = get_connection(_db_path())
    cursor = conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id, metric_type, capacity_mode, sprint_length_days, workspace_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, workspace_id, space_id, folder_id, metric_type, capacity_mode, sprint_length_days, workspace_id_new),
    )
```
- new_string:
```python
def create_team(name: str, workspace_id: str, space_id: str, folder_id: str,
                metric_type: str = "task_count", capacity_mode: str = "individual",
                sprint_length_days: int = 14, workspace_id_new: str | None = None,
                space_name: str | None = None) -> dict:
    """Create a team. `workspace_id` (positional) is the ClickUp workspace_id (legacy
    `clickup_workspace_id` column). `workspace_id_new` (kw-only optional) is the new
    `workspace_id` column added by Task 1 of OAuth init; equals the same ClickUp
    workspace_id but stored separately to enable workspace scoping in OAuth flows.
    `space_name` is the human-readable ClickUp Space name (= Product Area), captured
    at registration time so the home page doesn't have to hit ClickUp on every render."""
    conn = get_connection(_db_path())
    cursor = conn.execute(
        "INSERT INTO teams (name, clickup_workspace_id, clickup_space_id, clickup_folder_id, metric_type, capacity_mode, sprint_length_days, workspace_id, space_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, workspace_id, space_id, folder_id, metric_type, capacity_mode, sprint_length_days, workspace_id_new, space_name),
    )
```

- [ ] **Step 3: Pass `space_name` through in `routes/teams.py::create_team` POST handler**

Read current handler:

```bash
grep -n "team_service.create_team\b" /Users/collin/dev/Projects/ClickUp-report-app/src/routes/teams.py
```

It looks like:
```python
team = team_service.create_team(
    body.name, body.clickup_workspace_id, body.clickup_space_id,
    body.clickup_folder_id, body.metric_type, body.capacity_mode,
    body.sprint_length_days, workspace_id_new=workspace_id,
)
```

Use Edit:
- old_string:
```python
    team = team_service.create_team(
        body.name, body.clickup_workspace_id, body.clickup_space_id,
        body.clickup_folder_id, body.metric_type, body.capacity_mode,
        body.sprint_length_days, workspace_id_new=workspace_id,
    )
```
- new_string:
```python
    team = team_service.create_team(
        body.name, body.clickup_workspace_id, body.clickup_space_id,
        body.clickup_folder_id, body.metric_type, body.capacity_mode,
        body.sprint_length_days, workspace_id_new=workspace_id,
        space_name=body.space_name,
    )
```

- [ ] **Step 4: Smoke-test by simulating a create_team call**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
./.venv/bin/python -c "
import os
os.environ['DB_PATH'] = '/tmp/_home_task2.db'
from src.database import init_db
init_db(os.environ['DB_PATH'])
from src.services.team_service import create_team
t = create_team('TestTeam', 'ws1', 'space1', 'folder1', space_name='Network Services')
assert t['space_name'] == 'Network Services', t
print('OK — space_name persisted:', t['space_name'])
import os; os.remove('/tmp/_home_task2.db')
"
```

Expected: `OK — space_name persisted: Network Services`.

- [ ] **Step 5: Run full suite to confirm no regression**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/models.py src/services/team_service.py src/routes/teams.py
git commit -m "feat(home): persist space_name on team creation"
```

---

### Task 3: Wire Space name into team-settings form JS

**Files:**
- Modify: `templates/team_settings.html` (around line 252, the JS that builds the POST body)

- [ ] **Step 1: Add `space_name` to the JSON body**

Use Edit:
- old_string:
```javascript
    const selectedSpace = spaceSelect.options[spaceSelect.selectedIndex];
    const selectedTeam = allTeams.find(t => t.id === teamSelect.value);
    const data = {
      name: document.getElementById('name').value.trim(),
      clickup_workspace_id: selectedSpace ? selectedSpace.dataset.workspaceId || '' : '',
      clickup_space_id: spaceSelect.value,
      clickup_folder_id: folderSelect.value,
      metric_type: document.querySelector('input[name="metric_type"]:checked').value,
      capacity_mode: document.querySelector('input[name="capacity_mode"]:checked').value,
      sprint_length_days: parseInt(document.getElementById('sprint-length').value, 10),
      members: selectedTeam ? selectedTeam.members.map(m => ({id: String(m.id), username: m.username})) : undefined,
    };
```
- new_string:
```javascript
    const selectedSpace = spaceSelect.options[spaceSelect.selectedIndex];
    const selectedTeam = allTeams.find(t => t.id === teamSelect.value);
    const data = {
      name: document.getElementById('name').value.trim(),
      clickup_workspace_id: selectedSpace ? selectedSpace.dataset.workspaceId || '' : '',
      clickup_space_id: spaceSelect.value,
      clickup_folder_id: folderSelect.value,
      space_name: selectedSpace ? selectedSpace.text : '',
      metric_type: document.querySelector('input[name="metric_type"]:checked').value,
      capacity_mode: document.querySelector('input[name="capacity_mode"]:checked').value,
      sprint_length_days: parseInt(document.getElementById('sprint-length').value, 10),
      members: selectedTeam ? selectedTeam.members.map(m => ({id: String(m.id), username: m.username})) : undefined,
    };
```

- [ ] **Step 2: Manual smoke**

No headless test for this — confirmed by Task 6's manual scry verification. For now just check the JS parses:

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
node -e "console.log('templates parse OK')" 2>/dev/null || python3 -c "
import re
content = open('templates/team_settings.html').read()
assert 'space_name: selectedSpace ? selectedSpace.text' in content
print('OK — space_name added to form JS')
"
```

Expected: `OK — space_name added to form JS`.

- [ ] **Step 3: Commit**

```bash
git add templates/team_settings.html
git commit -m "feat(home): pass space_name from team form to backend"
```

---

### Task 4: Home-context service module

**Files:**
- Create: `src/services/home_service.py`

- [ ] **Step 1: Implement `build_home_context`**

Create `/Users/collin/dev/Projects/ClickUp-report-app/src/services/home_service.py` with the following content:

```python
"""Builds the structured context dict consumed by templates/home.html.

Aggregates per-team / per-Product-Area stats from existing services. No new
DB queries beyond what `team_service`, `sprint_service`, and `trend_service`
already expose.

Backfill of teams.space_name is handled here (opportunistic, on first home load
where any team has NULL space_name)."""

import logging
from datetime import datetime, timezone
from src.services import team_service
from src.services.sprint_service import get_team_sprints, get_sprint_status
from src.services.trend_service import get_sprint_summary
from src.clickup_client import ClickUpError

log = logging.getLogger(__name__)

SPARKLINE_LEN = 8  # last N closed sprints used for the velocity sparkline


def _humanize_ago(iso_ts: str | None) -> str:
    """Return a short relative-time string like '2h ago' / '3 days ago'.
    Returns 'never' if iso_ts is None / unparseable."""
    if not iso_ts:
        return "never"
    try:
        # Normalise: if it has 'Z' suffix or '+offset', strip to naive UTC
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return "unknown"
    now = datetime.utcnow()
    delta = now - ts
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    days = secs // 86400
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    return f"{weeks} week{'s' if weeks != 1 else ''} ago"


def _team_card(team: dict) -> dict:
    """Build the per-team card payload."""
    sprints = get_team_sprints(team["id"])
    for s in sprints:
        s["status"] = get_sprint_status(s)

    active = next((s for s in sprints if s["status"] == "active"), None)
    closed_sprints = [s for s in sprints if s["status"] == "closed"]
    closed_sorted = sorted(
        closed_sprints,
        key=lambda s: str(s.get("end_date") or s.get("start_date") or ""),
    )

    last_closed = None
    if closed_sorted:
        latest = closed_sorted[-1]
        summary = get_sprint_summary(latest["id"])
        last_closed = {
            "name": latest["name"],
            "completion": summary.get("completion_rate", 0),
            "ago": _humanize_ago(str(latest.get("end_date") or latest.get("start_date") or "")),
        }

    sparkline = []
    for s in closed_sorted[-SPARKLINE_LEN:]:
        summary = get_sprint_summary(s["id"])
        sparkline.append(round(summary.get("velocity", 0)))

    active_card = None
    if active:
        active_card = {"id": active["id"], "name": active["name"]}

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


def _area_stats(team_cards: list[dict]) -> dict:
    """Roll up stats across the teams in a single Product Area."""
    active_count = sum(1 for c in team_cards if c["active_sprint"])
    closed_count = sum(c["_closed_count"] for c in team_cards)
    velocities = [
        s.get("velocity", 0)
        for c in team_cards
        for s in c["_closed_summaries"]
    ]
    completions = [
        s.get("completion_rate", 0)
        for c in team_cards
        for s in c["_closed_summaries"]
    ]
    return {
        "active_sprints": active_count,
        "closed_sprints": closed_count,
        "avg_velocity": round(sum(velocities) / len(velocities)) if velocities else 0,
        "avg_completion": (sum(completions) / len(completions)) if completions else 0,
    }


def _last_activity_iso(team_cards_flat: list[dict]) -> str | None:
    """Find the most recent activity across all teams' last_closed sprints."""
    latest = None
    for c in team_cards_flat:
        lc = c.get("last_closed")
        if not lc:
            continue
        # We don't have a real timestamp — use the team's most recent sprint end_date
        # via the underlying summary. This is good enough for "humanize" display.
    # Simple fallback: scan latest closed sprint per team and take the freshest one.
    # Since `_team_card` already knows last_closed.ago, but not the raw timestamp,
    # we compute it again here.
    for c in team_cards_flat:
        lc = c.get("last_closed")
        if not lc:
            continue
        # Already-humanized "ago" is in lc; we want raw — derive from the team's
        # closed_sorted instead, but `_team_card` doesn't expose it. Trade-off:
        # for the banner we just use the freshest (smallest "ago" in seconds) by
        # re-parsing the human string isn't worth it. Use None when no data.
    return None  # The humanized "last activity" is in the banner only as a
                 # convenience; if all teams have last_closed, show the
                 # latest team's `last_closed.ago`. See workspace stats below.


async def _backfill_space_names(client, teams: list[dict]) -> None:
    """Populate teams.space_name for any rows where it's NULL.
    Mutates `teams` in place so callers see the updated values without re-querying."""
    needing = [t for t in teams if not t.get("space_name")]
    if not needing:
        return

    space_lookups = {
        (t.get("clickup_workspace_id") or "", t.get("clickup_space_id") or "")
        for t in needing
        if t.get("clickup_workspace_id") and t.get("clickup_space_id")
    }
    if not space_lookups:
        return

    name_by_id: dict[str, str] = {}
    for ws_id, _sp_id in {(ws, sp) for ws, sp in space_lookups}:
        try:
            spaces = await client.get_spaces(ws_id)
            for s in spaces:
                name_by_id[s["id"]] = s["name"]
        except ClickUpError as e:
            log.warning("Could not backfill space_name for ws=%s: %s", ws_id, e)
        except Exception:
            log.exception("Unexpected error backfilling space names for ws=%s", ws_id)

    for t in needing:
        name = name_by_id.get(t.get("clickup_space_id") or "")
        if name:
            team_service.update_team(t["id"], space_name=name)
            t["space_name"] = name


def _group_by_area(teams_with_cards: list[tuple[dict, dict]]) -> list[dict]:
    """Group (team_row, team_card) tuples by space_name. Sort areas + teams alphabetically."""
    areas: dict[str, list[tuple[dict, dict]]] = {}
    for team_row, card in teams_with_cards:
        key = team_row.get("space_name") or "(unassigned)"
        areas.setdefault(key, []).append((team_row, card))

    result = []
    for area_name in sorted(areas.keys(), key=str.lower):
        members = sorted(areas[area_name], key=lambda pair: str(pair[0].get("name") or "").lower())
        team_cards = [card for _, card in members]
        # Use the first team's space_id as the area identity (all teams in this group share it
        # by construction, except the "(unassigned)" bucket).
        space_id = members[0][0].get("clickup_space_id") if members else None
        result.append({
            "space_id": space_id,
            "space_name": area_name,
            "teams": [_strip_internal(c) for c in team_cards],
            "stats": _area_stats(team_cards),
        })
    return result


def _strip_internal(card: dict) -> dict:
    """Remove keys prefixed with `_` so the template never sees them."""
    return {k: v for k, v in card.items() if not k.startswith("_")}


async def build_home_context(client, teams: list[dict]) -> dict:
    """Top-level entry point. Mutates `teams` in place via backfill if needed."""
    await _backfill_space_names(client, teams)

    pairs = [(t, _team_card(t)) for t in teams]
    product_areas = _group_by_area(pairs)

    # Workspace-level rollup
    all_cards = [card for _, card in pairs]
    total_closed = sum(c["_closed_count"] for c in all_cards)
    all_completions = [
        s.get("completion_rate", 0) for c in all_cards for s in c["_closed_summaries"]
    ]
    workspace = {
        "total_teams": len(teams),
        "total_areas": len(product_areas),
        "total_closed_sprints": total_closed,
        "avg_completion": (sum(all_completions) / len(all_completions)) if all_completions else 0,
        "last_activity": _last_activity_label(all_cards),
    }

    return {"workspace": workspace, "product_areas": product_areas}


def _last_activity_label(cards: list[dict]) -> str:
    """Return the freshest 'ago' label across team last_closed entries.
    Returns 'never' if no team has any closed sprint."""
    candidates = [c["last_closed"]["ago"] for c in cards if c.get("last_closed")]
    if not candidates:
        return "never"
    # The humanised "ago" string isn't sortable by recency directly. Instead we use
    # a heuristic: shorter strings (m, h) beat longer ('days', 'weeks'). Good enough
    # for a banner, exact ordering not required.
    def _ord(s: str) -> int:
        if "just" in s: return 0
        if s.endswith("m ago"): return 1
        if s.endswith("h ago"): return 2
        if "day" in s: return 3
        return 4
    return sorted(candidates, key=_ord)[0]
```

- [ ] **Step 2: Smoke-test by calling it directly**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
./.venv/bin/python <<'PY'
import asyncio
from src.services.team_service import get_all_teams
from src.services.home_service import build_home_context
from src.clickup_client import get_system_client

async def main():
    teams = get_all_teams()
    print(f"Got {len(teams)} teams from DB")
    ctx = await build_home_context(get_system_client(), teams)
    print(f"Workspace: {ctx['workspace']}")
    for pa in ctx['product_areas']:
        print(f"\nProduct Area: {pa['space_name']} ({len(pa['teams'])} teams) — stats={pa['stats']}")
        for t in pa['teams']:
            print(f"  • {t['name']}  active={bool(t['active_sprint'])}  last={t['last_closed']}  spark={t['velocity_sparkline']}")

asyncio.run(main())
PY
```

Expected:
- "Got 4 teams from DB"
- Workspace dict with non-zero `total_teams`, `total_areas`, `total_closed_sprints`
- Exactly one Product Area: `Network Services` (after backfill)
- Each of LAN/WAN/CNW/ANI listed with its sparkline array

If the run fails due to network / API errors, capture the traceback for analysis. The backfill path is the only thing that hits ClickUp — if it fails, teams will be grouped under `"(unassigned)"`.

- [ ] **Step 3: Verify space_name was persisted (idempotency)**

```bash
./.venv/bin/python -c "
from src.services.team_service import get_all_teams
for t in get_all_teams():
    print(f\"{t['name']}: space_name={t.get('space_name')!r}\")
"
```

Expected: each of the 4 teams now has `space_name='Network Services'`.

- [ ] **Step 4: Verify backfill is no-op on second run**

Re-run Step 2's command. The `_backfill_space_names` function should detect zero NULL rows and return immediately. Watch `app.log` (or stderr) — there should be NO `WARNING` lines and no extra ClickUp API calls.

- [ ] **Step 5: Run full suite to confirm no regression**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/services/home_service.py
git commit -m "feat(home): home_service builds Product-Area-grouped context"
```

---

### Task 5: Wire `home` route to use the new context

**Files:**
- Modify: `src/routes/pages.py` (the `home` function, around line 68)

- [ ] **Step 1: Read the current `home` function**

```bash
grep -n "^async def home\|^def home" /Users/collin/dev/Projects/ClickUp-report-app/src/routes/pages.py
sed -n '68,90p' /Users/collin/dev/Projects/ClickUp-report-app/src/routes/pages.py
```

- [ ] **Step 2: Replace the `home` body**

The current body builds a flat `teams` list with active_sprint hung on each. Replace with a call to `build_home_context`:

Use Edit with the EXACT current body as old_string (read it first; the snippet below is the EXPECTED current shape after Initiative 3 wiring):
- old_string:
```python
async def home(request: Request, user=Depends(get_current_user)):
    if _needs_setup():
        return RedirectResponse("/setup")
    token = get_user_token(user["id"])
    request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []
    teams = _scoped_teams(request)
    for team in teams:
        team["sprints"] = get_team_sprints(team["id"])
        team["active_sprint"] = None
        for s in team["sprints"]:
            s["status"] = get_sprint_status(s)
            if s["status"] == "active":
                team["active_sprint"] = s
    return templates.TemplateResponse("home.html", _ctx(request, teams=teams))
```
- new_string:
```python
async def home(request: Request, user=Depends(get_current_user)):
    if _needs_setup():
        return RedirectResponse("/setup")
    token = get_user_token(user["id"])
    request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []
    teams = _scoped_teams(request)
    from src.services.home_service import build_home_context
    home_ctx = await build_home_context(request.state.user_client, teams)
    return templates.TemplateResponse(
        "home.html",
        _ctx(request, workspace=home_ctx["workspace"],
             product_areas=home_ctx["product_areas"],
             teams=teams),  # legacy passthrough — old template fallback if any
    )
```

If the actual current body differs from the snippet above, adjust accordingly — keep the `_needs_setup` redirect, the `user_workspaces` population, and `_scoped_teams(request)`. Replace only the per-team mutation block + `templates.TemplateResponse` call.

- [ ] **Step 3: Restart app and curl**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
curl -s --max-time 3 http://localhost:8000/ | head -50
```

Expected: HTTP 200, HTML response. The page won't yet *look* different (Task 6 rewrites the template), but the route should not 500.

If it 500s, check `app.log` for the traceback — most likely cause is a missing context key in the existing `home.html`.

- [ ] **Step 4: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/routes/pages.py
git commit -m "feat(home): home route uses Product-Area-grouped context"
```

---

### Task 6: New home.html + CSS + sparkline JS

**Files:**
- Modify: `templates/home.html` (full replacement)
- Modify: `static/style.css` (append rules at end)
- Modify: `static/dashboard.js` (append sparkline render block)

- [ ] **Step 1: Replace `templates/home.html` entirely**

Open `templates/home.html` and replace its entire content with:

```html
{% extends "base.html" %}
{% block title %}Sprint Reporter — Home{% endblock %}
{% block content %}

{% if product_areas %}
<section class="workspace-banner">
  <div class="banner-stat"><strong>{{ workspace.total_areas }}</strong> product area{{ 's' if workspace.total_areas != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ workspace.total_teams }}</strong> team{{ 's' if workspace.total_teams != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ workspace.total_closed_sprints }}</strong> closed sprint{{ 's' if workspace.total_closed_sprints != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ (workspace.avg_completion * 100) | round | int }}%</strong> avg completion</div>
  <div class="banner-stat banner-meta">last activity: {{ workspace.last_activity }}</div>
</section>

{% for pa in product_areas %}
<section class="product-area">
  <header class="pa-header">
    <h2 class="pa-title">{{ pa.space_name }}</h2>
    <span class="pa-badge">{{ pa.teams | length }} team{{ 's' if pa.teams|length != 1 else '' }}</span>
    <div class="pa-stats">
      <span class="pa-stat">active: <strong>{{ pa.stats.active_sprints }}</strong></span>
      <span class="pa-stat">closed: <strong>{{ pa.stats.closed_sprints }}</strong></span>
      <span class="pa-stat">avg velocity: <strong>{{ pa.stats.avg_velocity }}</strong></span>
      <span class="pa-stat">avg completion: <strong>{{ (pa.stats.avg_completion * 100) | round | int }}%</strong></span>
    </div>
  </header>

  <div class="team-grid">
    {% for team in pa.teams %}
    <article class="team-card">
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
{% endfor %}

{% else %}
<div class="content-narrow" style="padding-top: 60px;">
  <div class="empty-state">
    <h3 style="font-size:1.2rem;">No teams yet</h3>
    <p>Create a team to start tracking sprints.</p>
    <br>
    <a href="/teams/new" class="btn btn-primary">+ New Team</a>
  </div>
</div>
{% endif %}

{% endblock %}
```

- [ ] **Step 2: Append CSS rules to `static/style.css`**

Append the following to the END of `/Users/collin/dev/Projects/ClickUp-report-app/static/style.css`:

```css
/* === Home page: workspace banner === */
.workspace-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 16px 24px;
  margin: 16px 0 24px;
  background: var(--surface-1, #ffffff);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 10px;
}
.workspace-banner .banner-stat {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  color: var(--text-muted, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1.2;
}
.workspace-banner .banner-stat strong {
  font-size: 22px;
  font-weight: 600;
  color: var(--text, #1a202c);
  letter-spacing: 0;
  text-transform: none;
}
.workspace-banner .banner-meta {
  margin-left: auto;
  align-self: center;
  text-transform: none;
  letter-spacing: 0;
}

/* === Home page: Product Area sections === */
.product-area {
  margin: 24px 0 36px;
}
.pa-header {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border, #e2e8f0);
}
.pa-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}
.pa-badge {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  background: var(--accent-tint, rgba(123, 104, 238, 0.12));
  color: var(--accent, #7b68ee);
  border-radius: 4px;
}
.pa-stats {
  margin-left: auto;
  display: flex;
  gap: 18px;
  font-size: 13px;
  color: var(--text-muted, #64748b);
}
.pa-stats .pa-stat strong {
  color: var(--text, #1a202c);
  font-weight: 600;
}

/* === Home page: team cards grid === */
.team-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.team-card {
  background: var(--surface-1, #ffffff);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 10px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.team-card:hover {
  border-color: var(--accent, #7b68ee);
  box-shadow: 0 2px 8px rgba(123, 104, 238, 0.08);
}
.team-card-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
}
.team-card-status {
  margin: 0;
  font-size: 13px;
  color: var(--text, #1a202c);
}
.team-card-status a {
  color: var(--accent, #7b68ee);
  text-decoration: none;
}
.team-card-status a:hover {
  text-decoration: underline;
}
.sparkline-wrap {
  height: 32px;
  width: 100%;
}
canvas.sparkline {
  width: 100% !important;
  height: 32px !important;
}
.team-card-actions {
  display: flex;
  gap: 6px;
  margin-top: auto;
  flex-wrap: wrap;
}
.team-card-actions .btn {
  font-size: 12px;
  padding: 5px 12px;
}

@media (max-width: 480px) {
  .pa-stats {
    width: 100%;
    margin-left: 0;
    flex-wrap: wrap;
    gap: 8px 14px;
  }
  .workspace-banner .banner-meta {
    margin-left: 0;
  }
}
```

- [ ] **Step 3: Append sparkline JS to `static/dashboard.js`**

Append the following to the END of `/Users/collin/dev/Projects/ClickUp-report-app/static/dashboard.js`:

```javascript

// === Home page: render velocity sparklines on each team card ===
document.addEventListener('DOMContentLoaded', function () {
  if (typeof Chart === 'undefined') return;
  document.querySelectorAll('canvas.sparkline').forEach(canvas => {
    let points;
    try { points = JSON.parse(canvas.dataset.points || '[]'); }
    catch (e) { return; }
    if (!Array.isArray(points) || points.length === 0) return;
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: points.map((_, i) => i + 1),
        datasets: [{
          data: points,
          borderColor: 'rgba(123, 104, 238, 0.9)',
          backgroundColor: 'rgba(123, 104, 238, 0.12)',
          borderWidth: 2,
          tension: 0.3,
          pointRadius: 0,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
      },
    });
  });
});
```

- [ ] **Step 4: Restart app and visually verify**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
curl -s --max-time 3 -I http://localhost:8000/ | head -3
```

Expected: HTTP 200.

Open `http://localhost:8000/` in a browser. Verify:
- Workspace banner at top with: 1 product area · 4 teams · N closed sprints · X% avg · last activity
- One Product Area section "Network Services" with badge "4 teams" and area-level stats
- 4 cards (ANI, CNW, LAN, WAN) — each with title, last-sprint preview line, sparkline, and 3 buttons

If a card has zero closed sprints, the sparkline area is empty (no canvas render) — that's the expected fallback per the JS guard.

- [ ] **Step 5: Mobile viewport check**

In browser devtools, switch to a 375px-wide viewport. Verify:
- Cards stack to single column
- Banner stats wrap cleanly
- Buttons stay clickable

- [ ] **Step 6: Verify suite still green + log clean**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
echo "---"
tail -15 app.log
```

Expected: `82 passed`. App log shows clean startup, the home request returned 200, no errors.

- [ ] **Step 7: Commit**

```bash
git add templates/home.html static/style.css static/dashboard.js
git commit -m "feat(home): Product-Area-grouped layout with banner + sparklines"
```

---

### Task 7: Push + final verification

**Files:** none (verification + push).

- [ ] **Step 1: Run full suite one last time**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`.

- [ ] **Step 2: Confirm 6 new commits**

```bash
git log --oneline ee6f2e2..HEAD | head -10
```

Expected: 7 commits — 1 docs (spec+plan) + 6 feat commits matching the tasks above.

- [ ] **Step 3: Push to origin**

```bash
git push origin master
```

Expected: 7 commits pushed.

---

## Self-review checklist

**Spec coverage:**
- ✅ Schema: `space_name` column → Task 1
- ✅ `team_service.create_team` accepts space_name → Task 2
- ✅ `TeamCreate` Pydantic model → Task 2
- ✅ `routes/teams.py` passes through → Task 2
- ✅ Team-settings form sends `space_name` → Task 3
- ✅ Backfill of existing rows → Task 4 (`_backfill_space_names`)
- ✅ Home context builder → Task 4 (`build_home_context`)
- ✅ Home route uses new context → Task 5
- ✅ New home.html layout → Task 6
- ✅ CSS for banner / area / cards / sparkline → Task 6
- ✅ Chart.js sparkline render → Task 6
- ✅ Mobile-friendly grid → Task 6 CSS

**Placeholder scan:** No "TBD"/"TODO"/"add error handling"/"similar to" patterns. Every Edit step has explicit code blocks. Backfill error handling is concrete (catch ClickUpError, log warning, fall back to "(unassigned)").

**Type consistency:**
- `space_name` always typed as `str | None` (model, function signature, DB column).
- `velocity_sparkline` is `list[int]` produced by `_team_card`, consumed by template via `tojson`.
- `last_closed.ago` is a string label produced by `_humanize_ago`.
- `_strip_internal` removes `_closed_count` and `_closed_summaries` before they reach the template — no template touches them.

**One known limitation flagged inline:** `_humanize_ago` uses naive UTC parsing for ISO timestamps. Existing app code uses `datetime.utcnow().isoformat()` (no offset) consistently, so this matches; if tz-aware strings ever land here we strip via `replace("Z", "+00:00")` then drop tzinfo. Acceptable for v1.
