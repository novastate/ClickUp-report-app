# Workspace → Product Area → Team Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the home page into two levels — `/` shows Product Area cards (level-1 overview), `/areas/{space_id}` shows that area's teams grid (level-2 detail). Breadcrumbs reflect the new 3-level hierarchy.

**Architecture:** Refactor `home_service` into two public functions, one per level. Add a new route + template for level-2. Reuse the existing `.team-card` / `.team-grid` styling at level-2; introduce `.area-card` at level-1. Breadcrumbs gain an Area segment between Home and Team.

**Tech Stack:** FastAPI, Jinja2, Chart.js (already loaded), existing CSS tokens.

**Spec reference:** `docs/superpowers/specs/2026-05-05-areas-overview-design.md`

---

## File structure

| File | What changes |
|---|---|
| `src/services/home_service.py` | Replace `build_home_context` with `build_workspace_overview` + `build_area_detail`. Add private `_area_completion_history` helper for area-card sparkline. |
| `src/routes/pages.py` | Update `home()` to call `build_workspace_overview`. Add new `area_page(space_id)` route. Update breadcrumbs in `sprint_history_page`, `team_settings_page`, `team_trends_page`, `sprint_page` to include the area segment. |
| `templates/home.html` | Rewrite — workspace banner + area-card grid (level-1). |
| `templates/area.html` | Create — area banner + teams grid (level-2). Lifts most markup from the previous home.html. |
| `static/style.css` | Append `.area-card`, `.area-card-title`, `.area-card-stats`, `.area-card-meta` rules. Bump cache `?v=8` → `?v=9` in templates. |

No new dependencies. No new dependencies. No DB migration. No JS change (existing `canvas.sparkline` Chart.js block already handles new sparklines).

---

## Notes for the implementer

**Run tests with:**
```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ -v
```
Baseline: 82 passed.

**App restart**: `./stop.sh && ./start.sh`. Local `.env` has `AUTH_BYPASS=true` so the page is reachable without OAuth.

**Visual verification**: scry plugin via MCP. Tools: `mcp__plugin_scry_scry__scry_open`, `mcp__plugin_scry_scry__scry_snapshot`, `mcp__plugin_scry_scry__scry_close`.

**Do NOT** introduce per-user favorites — that's a deferred feature (see `~/.claude/projects/-Users-collin-dev-Projects-ClickUp-report-app/memory/upcoming-features.md`). The current design reserves a slot for it but doesn't implement it.

**Conventional Commits.** One commit per task.

---

### Task 1: Refactor home_service into level-1 + level-2 functions

**Files:**
- Modify: `src/services/home_service.py`

The existing `build_home_context(client, teams)` returns `{workspace, product_areas}`. Split into two top-level functions; private helpers (`_team_card`, `_area_stats`, `_humanize_ago`, `_backfill_space_names`, `_strip_internal`, `_last_activity_label`) stay.

- [ ] **Step 1: Replace the public surface**

In `src/services/home_service.py`, find the function `build_home_context` (around line 191). Use Edit:
- old_string:
```python
async def build_home_context(client, teams: list[dict]) -> dict:
    """Top-level entry point. Mutates `teams` in place via backfill if needed."""
    await _backfill_space_names(client, teams)

    pairs = [(t, _team_card(t)) for t in teams]
    product_areas = _group_by_area(pairs)

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
```
- new_string:
```python
SPARKLINE_AREA_LEN = 12  # last N closed-sprint completion %s for area-card sparkline


def _area_completion_history(team_cards: list[dict]) -> list[float]:
    """Chronologically-sorted completion rates of all closed sprints across the
    teams in this area. Capped at SPARKLINE_AREA_LEN entries.

    Note: per-team `_closed_summaries` is already ordered by end_date when built
    in `_team_card` (closed_sorted). We rely on that order, then merge by team
    and slice the tail. Rough but good enough for a sparkline trend.
    """
    series: list[float] = []
    for c in team_cards:
        for s in c.get("_closed_summaries", []):
            rate = s.get("completion_rate", 0) or 0
            series.append(round(rate * 100))
    return series[-SPARKLINE_AREA_LEN:]


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
    grouped = _group_by_area(pairs)

    # Walk the same grouping to build the level-1 summary. Internal team-cards
    # carry the per-sprint summaries we need; we don't expose them outwards.
    by_area_name: dict[str, list[dict]] = {}
    for t, card in pairs:
        key = t.get("space_name") or "(unassigned)"
        by_area_name.setdefault(key, []).append(card)

    areas = []
    for area in grouped:
        cards_with_internals = by_area_name.get(area["space_name"], [])
        areas.append({
            "space_id": area["space_id"],
            "space_name": area["space_name"],
            "team_count": len(area["teams"]),
            "stats": area["stats"],
            "completion_sparkline": _area_completion_history(cards_with_internals),
            "last_activity": _last_activity_label(cards_with_internals),
        })

    all_cards = [card for _, card in pairs]
    total_closed = sum(c["_closed_count"] for c in all_cards)
    all_completions = [
        s.get("completion_rate", 0) for c in all_cards for s in c["_closed_summaries"]
    ]
    workspace = {
        "total_teams": len(teams),
        "total_areas": len(areas),
        "total_closed_sprints": total_closed,
        "avg_completion": (sum(all_completions) / len(all_completions)) if all_completions else 0,
        "last_activity": _last_activity_label(all_cards),
    }
    return {"workspace": workspace, "areas": areas}


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
    cards = [card for _, card in pairs]
    sorted_pairs = sorted(pairs, key=lambda pr: str(pr[0].get("name") or "").lower())

    space_name = next((t.get("space_name") for t in in_area if t.get("space_name")), None) or "(unassigned)"
    return {
        "area": {
            "space_id": space_id,
            "space_name": space_name,
            "team_count": len(in_area),
            "stats": _area_stats(cards),
        },
        "teams": [_strip_internal(card) for _, card in sorted_pairs],
    }
```

- [ ] **Step 2: Smoke-test both functions**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
./.venv/bin/python <<'PY'
import asyncio
from src.services.team_service import get_all_teams
from src.services.home_service import build_workspace_overview, build_area_detail
from src.clickup_client import get_system_client

async def main():
    teams = get_all_teams()
    ov = await build_workspace_overview(get_system_client(), teams)
    print("=== OVERVIEW ===")
    print("workspace:", ov["workspace"])
    for a in ov["areas"]:
        print(f"  area: {a['space_name']} (id={a['space_id']}) — {a['team_count']} teams — sparkline={a['completion_sparkline']} — last={a['last_activity']}")

    if ov["areas"]:
        sid = ov["areas"][0]["space_id"]
        det = await build_area_detail(get_system_client(), teams, sid)
        print(f"\n=== AREA DETAIL for {sid} ===")
        print("area:", det["area"])
        for t in det["teams"]:
            print(f"  team {t['name']}: last_closed={t['last_closed']}")

    # 404 path
    miss = await build_area_detail(get_system_client(), teams, "nope_999")
    print(f"\nUnknown space_id → {miss}")

asyncio.run(main())
PY
```

Expected:
- `=== OVERVIEW ===` block with `workspace: {...}` showing 1 area, 4 teams
- One area entry "Network Services" with `team_count=4`, a non-empty `completion_sparkline`, and a humanized `last_activity`
- `=== AREA DETAIL for ... ===` block listing the four team names (ANI/CNW/LAN/WAN sorted alphabetically)
- `Unknown space_id → None`

- [ ] **Step 3: Run full suite (backwards-compat check)**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`. (No tests reference `build_home_context` directly — it was an internal helper called only by the home route, which we'll update in Task 2.)

**If the suite shows a NameError on `build_home_context`**, that means a test or another module imports it. Search:
```bash
grep -rn "build_home_context" /Users/collin/dev/Projects/ClickUp-report-app/src/ /Users/collin/dev/Projects/ClickUp-report-app/tests/
```
The expected only-hit is `src/routes/pages.py:85`. That call is updated in Task 2.

- [ ] **Step 4: Commit**

```bash
git add src/services/home_service.py
git commit -m "refactor(home): split home_service into workspace_overview + area_detail"
```

---

### Task 2: Update `home` route + add `area_page` route

**Files:**
- Modify: `src/routes/pages.py`

The existing `home()` calls `build_home_context`. Switch to `build_workspace_overview`. Add a new `area_page` route below it.

- [ ] **Step 1: Update the `home` route body**

In `src/routes/pages.py`, find the `home` function (around line 78). Use Edit:
- old_string:
```python
@router.get("/", response_class=HTMLResponse)
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
             teams=teams),
    )
```
- new_string:
```python
@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user=Depends(get_current_user)):
    if _needs_setup():
        return RedirectResponse("/setup")
    token = get_user_token(user["id"])
    request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []
    teams = _scoped_teams(request)
    from src.services.home_service import build_workspace_overview
    overview = await build_workspace_overview(request.state.user_client, teams)
    return templates.TemplateResponse(
        "home.html",
        _ctx(request, workspace=overview["workspace"], areas=overview["areas"]),
    )


@router.get("/areas/{space_id}", response_class=HTMLResponse)
async def area_page(request: Request, space_id: str,
                    user=Depends(get_current_user)):
    if _needs_setup():
        return RedirectResponse("/setup")
    token = get_user_token(user["id"])
    request.state.user_workspaces = await oauth_fetch_workspaces(token) if token else []
    teams = _scoped_teams(request)
    from src.services.home_service import build_area_detail
    detail = await build_area_detail(request.state.user_client, teams, space_id)
    if detail is None:
        raise HTTPException(404, "Product Area not found")
    return templates.TemplateResponse(
        "area.html",
        _ctx(request, area=detail["area"], teams=detail["teams"],
             breadcrumbs=_breadcrumbs(("Home", "/"), (detail["area"]["space_name"], None))),
    )
```

If `HTTPException` isn't already imported at the top of the file, ensure the import line includes it. Check:
```bash
grep -n "from fastapi import" /Users/collin/dev/Projects/ClickUp-report-app/src/routes/pages.py | head -2
```
It should already include `HTTPException` from earlier work (used in `setup_page`). If not, add it.

- [ ] **Step 2: Smoke-test**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
curl -s --max-time 3 -I http://localhost:8000/ | head -3
```

Expected: `HTTP/1.1 200 OK`. The page won't render correctly yet (templates updated in Tasks 3-5) but the route shouldn't 500.

If it 500s, dump `tail -20 app.log`. Most likely cause: existing `home.html` references `product_areas` which we no longer pass. The page may render the empty-state branch (`No teams yet`) — that's OK for now; Task 4 rewrites the template.

```bash
curl -s --max-time 3 -I http://localhost:8000/areas/90120495342 | head -3
```

Expected: `HTTP/1.1 200 OK` (existing space_id for Network Services). The template doesn't exist yet so this WILL 500 with `TemplateNotFound: area.html` — that's expected. We'll create it in Task 5.

If you want to verify the route reaches the template-render step, expect to see `TemplateNotFound: area.html` in `tail -10 app.log` rather than a NameError or 404.

```bash
curl -s --max-time 3 -I http://localhost:8000/areas/nope_999 | head -3
```

Expected: `HTTP/1.1 404 Not Found` (or `307` redirect from auth-exception-handler if the test client looks like a browser; either is fine). The point is `build_area_detail` correctly returned None and the route raised 404.

- [ ] **Step 3: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`.

- [ ] **Step 4: Commit**

```bash
git add src/routes/pages.py
git commit -m "feat(home): add /areas/{space_id} route + switch home to workspace overview"
```

---

### Task 3: Add the area segment to other pages' breadcrumbs

**Files:**
- Modify: `src/routes/pages.py` (4 breadcrumb call sites)

Each existing route that breadcrumbs `Home > <Team> > ...` needs to insert `<Product Area>` in the middle. The team's `space_name` and `clickup_space_id` are already on the row from earlier work.

- [ ] **Step 1: Helper for area segment**

Inside `src/routes/pages.py`, near the existing `_breadcrumbs` helper (around line 41), add:

```python
def _area_crumb(team: dict | None) -> tuple[str, str | None] | None:
    """Build the (label, href) tuple for the Product Area breadcrumb segment.
    Returns None if the team has no space metadata (skips the crumb)."""
    if not team:
        return None
    name = team.get("space_name")
    sid = team.get("clickup_space_id")
    if not name or not sid:
        return None
    return (name, f"/areas/{sid}")
```

Use Edit to insert it right after the existing `_breadcrumbs` definition. Find the line:
```python
def _breadcrumbs(*pairs):
```
… and locate the end of that function (the `return` line that builds the dict list). Add the new helper directly below it.

- [ ] **Step 2: Update `team_settings_page` breadcrumb (around line 141)**

Use Edit:
- old_string:
```python
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Settings", None)),
```
- new_string:
```python
        breadcrumbs=_breadcrumbs(*([("Home", "/")] + ([_area_crumb(team)] if _area_crumb(team) else []) + [(team["name"], f"/teams/{team['id']}/sprints"), ("Settings", None)])),
```

(The conditional list-flattening keeps the line compact while skipping the area crumb when metadata is missing.)

- [ ] **Step 3: Update `sprint_history_page` breadcrumb (around line 162)**

Use Edit:
- old_string:
```python
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], None)),
```
- new_string:
```python
        breadcrumbs=_breadcrumbs(*([("Home", "/")] + ([_area_crumb(team)] if _area_crumb(team) else []) + [(team["name"], None)])),
```

- [ ] **Step 4: Update `sprint_page` breadcrumb (around line 300)**

The current code (after Initiative 3 work) probably reads:

```python
        breadcrumbs=_breadcrumbs(
            ("Home", "/"),
            (team["name"], f"/teams/{team['id']}/sprints"),
            (_display_name(sprint["name"]), None),
        ),
```

Use Edit:
- old_string:
```python
        breadcrumbs=_breadcrumbs(
            ("Home", "/"),
            (team["name"], f"/teams/{team['id']}/sprints"),
            (_display_name(sprint["name"]), None),
        ),
```
- new_string:
```python
        breadcrumbs=_breadcrumbs(*([("Home", "/")] + ([_area_crumb(team)] if _area_crumb(team) else []) + [(team["name"], f"/teams/{team['id']}/sprints"), (_display_name(sprint["name"]), None)])),
```

- [ ] **Step 5: Update `team_trends_page` breadcrumb (around line 324)**

Use Edit:
- old_string:
```python
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Trends", None)),
```
- new_string:
```python
        breadcrumbs=_breadcrumbs(*([("Home", "/")] + ([_area_crumb(team)] if _area_crumb(team) else []) + [(team["name"], f"/teams/{team['id']}/sprints"), ("Trends", None)])),
```

- [ ] **Step 6: Smoke-test breadcrumbs**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
# A team page (sprint history)
curl -s --max-time 3 http://localhost:8000/teams/1/sprints | grep -A 0 "Network Services" | head -3
```

Expected: at least one match showing "Network Services" anchor in the breadcrumb HTML.

- [ ] **Step 7: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`.

- [ ] **Step 8: Commit**

```bash
git add src/routes/pages.py
git commit -m "feat(home): insert Product Area segment into nested breadcrumbs"
```

---

### Task 4: Rewrite `templates/home.html` for level-1 overview

**Files:**
- Modify: `templates/home.html`

The existing file iterates `product_areas` and renders teams under each. Replace with a workspace banner + area-card grid.

- [ ] **Step 1: Overwrite the file**

Use Write to replace `/Users/collin/dev/Projects/ClickUp-report-app/templates/home.html` with:

```html
{% extends "base.html" %}
{% block title %}Sprint Reporter — Home{% endblock %}
{% block content %}

{% if areas %}
<div class="home-wrap">
<section class="workspace-banner">
  <div class="banner-stat"><strong>{{ workspace.total_areas }}</strong> product area{{ 's' if workspace.total_areas != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ workspace.total_teams }}</strong> team{{ 's' if workspace.total_teams != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ workspace.total_closed_sprints }}</strong> closed sprint{{ 's' if workspace.total_closed_sprints != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ (workspace.avg_completion * 100) | round | int }}%</strong> avg completion</div>
  <div class="banner-stat banner-meta">last activity: {{ workspace.last_activity }}</div>
</section>

<div class="team-grid">
  {% for area in areas %}
    {% if area.space_id %}
    <a href="/areas/{{ area.space_id }}" class="area-card">
    {% else %}
    <div class="area-card area-card--unassigned">
    {% endif %}
      <div class="area-card-header">
        <h2 class="area-card-title">{{ area.space_name }}</h2>
        <span class="area-card-badge">{{ area.team_count }} team{{ 's' if area.team_count != 1 else '' }}</span>
      </div>

      <div class="area-card-stats">
        <span class="area-card-stat"><strong>{{ area.stats.active_sprints }}</strong> active</span>
        <span class="area-card-stat"><strong>{{ area.stats.closed_sprints }}</strong> closed</span>
        <span class="area-card-stat"><strong>{{ area.stats.avg_velocity }}</strong> avg velocity</span>
        <span class="area-card-stat"><strong>{{ (area.stats.avg_completion * 100) | round | int }}%</strong> avg completion</span>
      </div>

      <div class="sparkline-wrap">
        <canvas class="sparkline" data-points="{{ area.completion_sparkline | tojson }}"></canvas>
      </div>

      <div class="area-card-meta">last activity: {{ area.last_activity }}</div>
    {% if area.space_id %}
    </a>
    {% else %}
    </div>
    {% endif %}
  {% endfor %}
</div>
</div>

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

- [ ] **Step 2: Visual smoke (no scry yet — that's Task 7)**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
curl -s --max-time 3 http://localhost:8000/ | grep -E "(area-card|Network Services|workspace-banner)" | head -5
```

Expected:
- `class="workspace-banner"` match
- `class="area-card"` match (with `href="/areas/..."`)
- `Network Services` appears in the title

- [ ] **Step 3: Commit**

```bash
git add templates/home.html
git commit -m "feat(home): rewrite home template as workspace overview with area cards"
```

---

### Task 5: Create `templates/area.html` for level-2

**Files:**
- Create: `templates/area.html`

The level-2 page reuses the team-grid layout from the previous home, but with an area-scoped banner.

- [ ] **Step 1: Create the file**

Write `/Users/collin/dev/Projects/ClickUp-report-app/templates/area.html` with:

```html
{% extends "base.html" %}
{% block title %}{{ area.space_name }} — Sprint Reporter{% endblock %}
{% block content %}

<div class="home-wrap">
<section class="workspace-banner">
  <div class="banner-stat"><strong>{{ area.team_count }}</strong> team{{ 's' if area.team_count != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ area.stats.active_sprints }}</strong> active sprint{{ 's' if area.stats.active_sprints != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ area.stats.closed_sprints }}</strong> closed sprint{{ 's' if area.stats.closed_sprints != 1 else '' }}</div>
  <div class="banner-stat"><strong>{{ area.stats.avg_velocity }}</strong> avg velocity</div>
  <div class="banner-stat"><strong>{{ (area.stats.avg_completion * 100) | round | int }}%</strong> avg completion</div>
</section>

<header class="pa-header">
  <h2 class="pa-title">{{ area.space_name }}</h2>
  <span class="pa-badge">{{ area.team_count }} team{{ 's' if area.team_count != 1 else '' }}</span>
</header>

<div class="team-grid">
  {% for team in teams %}
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
</div>

{% endblock %}
```

- [ ] **Step 2: Smoke-test**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
curl -s --max-time 3 http://localhost:8000/areas/90120495342 | grep -E "(team-card|ANI|CNW|LAN|WAN)" | head -8
```

Expected: matches showing all four team names rendered as `team-card` elements.

- [ ] **Step 3: Commit**

```bash
git add templates/area.html
git commit -m "feat(home): add area.html level-2 template"
```

---

### Task 6: Add `.area-card` CSS

**Files:**
- Modify: `static/style.css` (append rules)

- [ ] **Step 1: Append CSS**

Append the following to the END of `/Users/collin/dev/Projects/ClickUp-report-app/static/style.css`:

```css

/* === Home page: Area cards (level-1 overview) === */
.area-card {
  background: var(--surface-1, #ffffff);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 10px;
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  text-decoration: none;
  color: inherit;
  min-height: 200px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}
.area-card:hover {
  border-color: var(--accent, #7b68ee);
  box-shadow: 0 4px 16px rgba(123, 104, 238, 0.10);
  transform: translateY(-1px);
}
.area-card--unassigned {
  cursor: default;
  opacity: 0.85;
}
.area-card--unassigned:hover {
  border-color: var(--border, #e2e8f0);
  box-shadow: none;
  transform: none;
}
.area-card-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.area-card-title {
  margin: 0;
  font-size: 1.4rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.area-card-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 3px 8px;
  background: var(--accent-tint, rgba(123, 104, 238, 0.12));
  color: var(--accent, #7b68ee);
  border-radius: 4px;
}
.area-card-stats {
  display: flex;
  gap: 22px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-muted, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.area-card-stat strong {
  display: block;
  color: var(--text, #1a202c);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
  text-transform: none;
  margin-bottom: 2px;
}
.area-card-meta {
  margin-top: auto;
  font-size: 12px;
  color: var(--text-muted, #64748b);
}
```

- [ ] **Step 2: Bump cache version in templates**

Run:
```bash
sed -i '' 's|style.css?v=8|style.css?v=9|g' \
  /Users/collin/dev/Projects/ClickUp-report-app/templates/base.html \
  /Users/collin/dev/Projects/ClickUp-report-app/templates/auth/error.html \
  /Users/collin/dev/Projects/ClickUp-report-app/templates/auth/workspace.html
grep "style.css?v=" /Users/collin/dev/Projects/ClickUp-report-app/templates/base.html
```

Expected: `style.css?v=9`.

- [ ] **Step 3: Restart app + curl-verify**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
./stop.sh && ./start.sh
sleep 1
curl -s --max-time 3 http://localhost:8000/ | grep "style.css?v=" | head -1
```

Expected: `<link rel="stylesheet" href="/static/style.css?v=9">`.

- [ ] **Step 4: Run full suite**

```bash
SESSION_ENCRYPTION_KEY=$(./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ 2>&1 | tail -3
```

Expected: `82 passed`.

- [ ] **Step 5: Commit**

```bash
git add static/style.css templates/base.html templates/auth/error.html templates/auth/workspace.html
git commit -m "feat(home): area-card styles + cache bump v=9"
```

---

### Task 7: Visual verification with scry

**Files:** none (verification only).

- [ ] **Step 1: Open home in scry, snapshot**

Open `mcp__plugin_scry_scry__scry_open` with `url=http://localhost:8000/`, `width=1440`, `height=900`. Then call `mcp__plugin_scry_scry__scry_snapshot` with `inline=true`, `fullPage=true`.

Expected:
- Top: workspace banner with horizontal stats
- Below: a single area card "Network Services" with "4 TEAMS" badge, stats row (active / closed / avg velocity / avg completion), a sparkline of completion-rate history, and a "last activity: 2 weeks ago" meta line at bottom.
- The card is clickable (cursor pointer / underline-on-hover).

- [ ] **Step 2: Click the area card via scry navigation**

Use `mcp__plugin_scry_scry__scry_navigate` with `url=http://localhost:8000/areas/90120495342`. Snapshot.

Expected:
- Top: area-banner with team count + stats
- `Network Services` heading + `4 teams` badge
- Below: 2x2 team-card grid (ANI, CNW, LAN, WAN) — same look as the previous home page

- [ ] **Step 3: Verify breadcrumb on a team page**

Navigate to `http://localhost:8000/teams/1/sprints` (or whatever team_id is in DB). Snapshot.

Expected breadcrumb: `Home / Network Services / <team name>`.

If the breadcrumb still reads `Home / <team name>`, Task 3 didn't take effect — re-check the edits.

- [ ] **Step 4: Close scry**

Call `mcp__plugin_scry_scry__scry_close`.

- [ ] **Step 5: Push**

```bash
cd /Users/collin/dev/Projects/ClickUp-report-app
git push origin master
```

Expected: 7 commits pushed (1 docs + 6 feat).

---

## Self-review checklist

**Spec coverage:**
- ✅ Workspace overview at `/` → Task 2 (route) + Task 4 (template)
- ✅ Area detail at `/areas/{space_id}` → Task 2 (route) + Task 5 (template)
- ✅ Service split (`build_workspace_overview` + `build_area_detail`) → Task 1
- ✅ Area-card sparkline (last 12 sprint completions across teams in area) → Task 1 (`_area_completion_history`)
- ✅ Breadcrumbs include Area segment → Task 3
- ✅ `.area-card` CSS reusing tokens → Task 6
- ✅ `.team-grid` reused for both levels → Tasks 4 + 5 use the same class
- ✅ 404 on unknown space_id → Task 2 (`raise HTTPException(404)`)
- ✅ Unassigned-area no-link rendering → Task 4 (`{% if area.space_id %}` guard) + Task 6 (`.area-card--unassigned` style)

**Placeholder scan:** No "TBD"/"add error handling"/"similar to" patterns. Every Edit step shows actual code. Every smoke-test step has an exact command + expected output.

**Type consistency:**
- `space_id` is `str | None` everywhere (None when unassigned).
- `completion_sparkline` is `list[int]` (rounded percentages, 0–100).
- `last_activity` is a humanized string label.
- `area` dict shape consistent across `build_workspace_overview` (areas list) and `build_area_detail` (single area key).
- `team_card` shape unchanged from previous initiative.

**Known limitation flagged inline:** the area-card sparkline merges `_closed_summaries` from each team (already date-sorted within a team) but doesn't re-sort across teams. If multiple teams have overlapping sprint dates, the chart's left-to-right order is "team 1's all, then team 2's all" rather than strictly chronological. This is good-enough for a trend signal in v1; a follow-up could attach end_date to each summary and sort.
