# Navigation & Breadcrumbs Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat single-row nav with a standard hierarchical pattern — identity bar + breadcrumbs + contextual team sub-nav — and add prev/next sprint navigation, fixing all 7 navigation issues from the audit in one coherent change.

**Architecture:** Two new Jinja partials (breadcrumbs, team sub-nav). `base.html` rewritten to use them. `_ctx()` helper extended to pass breadcrumbs + active sub-nav state. Each route handler builds its own breadcrumb list. Sprint detail handler additionally computes prev/next sprint by start_date within the same team.

**Tech Stack:** FastAPI + Jinja2 server rendering, vanilla CSS, no new JS.

**Spec:** `docs/superpowers/specs/2026-05-04-navigation-fix-design.md`

> **Verification note:** scry runs in the controller's MCP context. Implementer subagents commit code; the controller runs scry verification after each task's commit. Verification is part of acceptance.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `templates/components/breadcrumbs.html` | Create | Renders `breadcrumbs` list as anchor tags + `›` separators; last item is plain text. |
| `templates/components/team_sub_nav.html` | Create | Three tabs (Sprint History / Trends / Settings) with `active` state per `team_sub_nav_active`. |
| `templates/base.html` | Rewrite | Replace flat nav with identity-bar + breadcrumbs slot + team sub-nav slot. |
| `static/style.css` | Append | Styles for `.identity-bar`, `.breadcrumbs`, `.team-sub-nav`, `.team-sub-nav .tab[.active]`, `.sprint-nav`. |
| `src/routes/pages.py` | Modify | Extend `_ctx()` with `breadcrumbs` + `team_sub_nav_active`; add `_breadcrumbs()` helper; pass values from each route. Plus prev/next sprint computation in sprint detail handler. |
| `templates/sprint_report.html` | Modify | Replace `← Sprint History` button with prev/next sprint links. |
| `templates/sprint_live.html` | Modify | Add prev/next sprint links to the actions area (alongside existing refresh/close buttons). |
| `templates/home.html` | Modify | Remove the duplicate `+ New Team` button at line 39 (after team list). The empty-state one (line 48) stays since it's only shown when there are no teams. |

---

## Task 1: Foundation — components, base.html, CSS, `_ctx` extensions

**Files:**
- Create: `templates/components/breadcrumbs.html`
- Create: `templates/components/team_sub_nav.html`
- Modify: `templates/base.html` (full rewrite)
- Modify: `static/style.css` (append)
- Modify: `src/routes/pages.py:25-28` (extend `_ctx`)

### Step 1: Create `templates/components/breadcrumbs.html`

Use `Write` to create the file with this content:

```jinja
{% if breadcrumbs %}
<nav class="breadcrumbs" aria-label="breadcrumb">
  {% for crumb in breadcrumbs %}
    {% if not loop.last %}
      <a href="{{ crumb.href }}">{{ crumb.label }}</a>
      <span class="separator" aria-hidden="true">›</span>
    {% else %}
      <span class="current" aria-current="page">{{ crumb.label }}</span>
    {% endif %}
  {% endfor %}
</nav>
{% endif %}
```

### Step 2: Create `templates/components/team_sub_nav.html`

Use `Write` to create the file with this content:

```jinja
{% if team and team_sub_nav_active %}
<nav class="team-sub-nav" aria-label="team sections">
  <a href="/teams/{{ team.id }}/sprints" class="tab {% if team_sub_nav_active == 'sprints' %}active{% endif %}">Sprint History</a>
  <a href="/teams/{{ team.id }}/trends" class="tab {% if team_sub_nav_active == 'trends' %}active{% endif %}">Trends</a>
  <a href="/teams/{{ team.id }}/settings" class="tab {% if team_sub_nav_active == 'settings' %}active{% endif %}">Settings</a>
</nav>
{% endif %}
```

### Step 3: Rewrite `templates/base.html`

Use `Write` (full replacement) with this exact content:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Sprint Reporter{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css?v=4">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
  <header class="identity-bar">
    <a href="/" class="brand">Sprint Reporter</a>
    <a href="/teams/new" class="btn btn-primary new-team-btn">+ New Team</a>
  </header>
  {% include "components/breadcrumbs.html" %}
  {% include "components/team_sub_nav.html" %}
  {% block content %}{% endblock %}
  <script src="/static/dashboard.js"></script>
</body>
</html>
```

(The CSS bust v3→v4 forces browser to reload the stylesheet so the new selectors take effect.)

### Step 4: Append nav styles to `static/style.css`

Append this exact block to the end of the file:

```css

/* --- Identity bar / breadcrumbs / team sub-nav -------------------------- */
.identity-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 24px;
  background: #1a202c;
  color: #fff;
  border-bottom: 1px solid #2d3748;
}
.identity-bar .brand {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  text-decoration: none;
  letter-spacing: 0.2px;
}
.identity-bar .new-team-btn {
  font-size: 13px;
  padding: 6px 14px;
}

.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  background: #f7fafc;
  border-bottom: 1px solid #edf2f7;
  font-size: 13px;
  color: #4a5568;
  flex-wrap: wrap;
}
.breadcrumbs a {
  color: #4299e1;
  text-decoration: none;
}
.breadcrumbs a:hover { text-decoration: underline; }
.breadcrumbs .separator {
  color: #cbd5e0;
}
.breadcrumbs .current {
  color: #1a202c;
  font-weight: 500;
}

.team-sub-nav {
  display: flex;
  gap: 4px;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #edf2f7;
  overflow-x: auto;
  white-space: nowrap;
}
.team-sub-nav .tab {
  padding: 12px 16px;
  font-size: 14px;
  color: #718096;
  text-decoration: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.team-sub-nav .tab:hover {
  color: #2d3748;
}
.team-sub-nav .tab.active {
  color: #2d3748;
  font-weight: 600;
  border-bottom-color: #4299e1;
}

.sprint-nav {
  display: flex;
  gap: 8px;
  align-items: center;
}
.sprint-nav .btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

@media (max-width: 480px) {
  .identity-bar {
    padding: 8px 12px;
  }
  .identity-bar .new-team-btn {
    font-size: 0;          /* hide text */
    padding: 6px 10px;
  }
  .identity-bar .new-team-btn::before {
    content: "+";
    font-size: 16px;
  }
  .breadcrumbs {
    padding: 10px 12px;
  }
  .team-sub-nav {
    padding: 0 12px;
  }
  .team-sub-nav .tab {
    padding: 10px 12px;
    font-size: 13px;
  }
  .sprint-nav {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }
}
```

### Step 5: Extend `_ctx` in `src/routes/pages.py`

Use `Edit` to replace the existing `_ctx` (lines 25-28):

old_string:
```python
def _ctx(request, **kwargs):
    kwargs["request"] = request
    kwargs["nav_teams"] = get_all_teams()
    return kwargs
```

new_string:
```python
def _ctx(request, breadcrumbs=None, team_sub_nav_active=None, **kwargs):
    kwargs["request"] = request
    kwargs["nav_teams"] = get_all_teams()
    kwargs["breadcrumbs"] = breadcrumbs or []
    kwargs["team_sub_nav_active"] = team_sub_nav_active
    return kwargs


def _breadcrumbs(*pairs):
    """Build a breadcrumbs list. Each pair is (label, href). Pass None as href for the last entry."""
    return [{"label": label, "href": href} for label, href in pairs]
```

(The `_breadcrumbs` helper is added directly after `_ctx`. Existing routes that don't pass the new kwargs continue to work — they just won't render breadcrumbs/sub-nav.)

### Step 6: Verify everything still parses and renders

Run:
```bash
.venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
for tpl in ['base.html', 'components/breadcrumbs.html', 'components/team_sub_nav.html']:
    env.get_template(tpl)
print('OK — 3 templates parse')
"
```
Expected: `OK — 3 templates parse`.

Run:
```bash
.venv/bin/python -c "from src.routes.pages import _ctx, _breadcrumbs; b = _breadcrumbs(('Home', '/'), ('LAN', None)); print(b); print(_ctx(None, breadcrumbs=b, team_sub_nav_active='sprints'))"
```
Expected: prints a list with two dicts, then a dict containing `breadcrumbs` and `team_sub_nav_active='sprints'`.

If either fails, STOP and report BLOCKED.

### Step 7: Restart the app

Run: `./stop.sh && ./start.sh`
Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

If it fails, run `tail -30 app.log` and STOP.

### Step 8: Commit

```bash
git add templates/components/breadcrumbs.html templates/components/team_sub_nav.html templates/base.html static/style.css src/routes/pages.py
git commit -m "$(cat <<'EOF'
feat(nav): foundation — identity bar, breadcrumbs partial, team sub-nav

Replaces the flat top nav with a three-row top section:
- Identity bar: Sprint Reporter brand + New Team button
- Breadcrumbs partial (rendered when route passes breadcrumbs context)
- Team sub-nav partial (rendered when route passes team_sub_nav_active)

Adds _breadcrumbs(*pairs) helper and extends _ctx() with breadcrumbs +
team_sub_nav_active params (defaults preserve existing behavior). CSS
covers identity bar, breadcrumbs, sub-nav tabs, sprint nav, plus mobile
@480px adjustments.

Routes don't yet pass the new context — that's the next task. Pages
will render with the new identity bar but no breadcrumbs/sub-nav until
Task 2 lands.

Refs spec: docs/superpowers/specs/2026-05-04-navigation-fix-design.md
EOF
)"
```

---

## Task 2: Wire breadcrumbs + sub-nav into all routes

**Files:**
- Modify: `src/routes/pages.py` — every route handler that returns a TemplateResponse

### Step 1: Read the current list of routes

Run: `grep -n "_ctx(request" src/routes/pages.py`

Expected: see ~6 lines, one per route handler:
- line 47: `home`
- line 54: `setup_page`
- line 70: `team_settings_new`
- line 77: `team_settings_edit`
- line 90: `sprint_history_page`
- line 195+: sprint detail (`sprint_page`)
- line 218: `team_trends_page`

### Step 2: Add breadcrumbs + sub-nav to each route

For each route below, find the existing `templates.TemplateResponse(..., _ctx(request, ...))` call and add the indicated kwargs to `_ctx`. Use `Edit` for each.

**Route: `/` (home)** — line ~47

old_string:
```python
    return templates.TemplateResponse("home.html", _ctx(request, teams=teams))
```

new_string:
```python
    return templates.TemplateResponse("home.html", _ctx(request, teams=teams))
```

(No change. Home doesn't get breadcrumbs or sub-nav. The current line is correct as-is.)

**Route: `/setup`** — line ~54

(No change. Setup is special, doesn't fit the team hierarchy.)

**Route: `/teams/new`** — line ~70

old_string:
```python
    return templates.TemplateResponse("team_settings.html", _ctx(request, team=None))
```

new_string:
```python
    return templates.TemplateResponse("team_settings.html", _ctx(
        request,
        team=None,
        breadcrumbs=_breadcrumbs(("Home", "/"), ("New Team", None)),
    ))
```

**Route: `/teams/{team_id}/settings`** — line ~77

old_string:
```python
    return templates.TemplateResponse("team_settings.html", _ctx(request, team=team, current_members=members))
```

new_string:
```python
    return templates.TemplateResponse("team_settings.html", _ctx(
        request,
        team=team,
        current_members=members,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Settings", None)),
        team_sub_nav_active="settings",
    ))
```

**Route: `/teams/{team_id}/sprints`** — line ~90

old_string:
```python
    return templates.TemplateResponse("sprint_history.html", _ctx(request, team=team, sprints=sprint_data))
```

new_string:
```python
    return templates.TemplateResponse("sprint_history.html", _ctx(
        request,
        team=team,
        sprints=sprint_data,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], None)),
        team_sub_nav_active="sprints",
    ))
```

**Route: `/sprint/{sprint_id}`** — line ~195

The current call spans multiple lines:
```python
    return templates.TemplateResponse(template, _ctx(
        request,
        sprint=sprint,
        status=status,
        team=team,
        tasks=tasks,
        summary=summary,
        scope_changes=scope_changes,
        progress_history=progress,
        sprint_day=sprint_day,
        on_track=on_track,
        team_members=[m["username"] for m in get_team_members(team["id"])],
        capacity=get_sprint_capacity(sprint["id"]),
        workload=workload,
        final_snapshot=final_snapshot_data,
    ))
```

Replace with (adds two new kwargs at the end, plus uses display_name for the sprint label):

```python
    from src.routes.pages import _display_name as _disp
    return templates.TemplateResponse(template, _ctx(
        request,
        sprint=sprint,
        status=status,
        team=team,
        tasks=tasks,
        summary=summary,
        scope_changes=scope_changes,
        progress_history=progress,
        sprint_day=sprint_day,
        on_track=on_track,
        team_members=[m["username"] for m in get_team_members(team["id"])],
        capacity=get_sprint_capacity(sprint["id"]),
        workload=workload,
        final_snapshot=final_snapshot_data,
        breadcrumbs=_breadcrumbs(
            ("Home", "/"),
            (team["name"], f"/teams/{team['id']}/sprints"),
            (_disp(sprint["name"]), None),
        ),
        team_sub_nav_active="sprints",
    ))
```

Wait — `_display_name` is module-private (defined as `_display_name` in the same file). We can use it directly without re-importing. Simplify:

new_string (corrected):
```python
    return templates.TemplateResponse(template, _ctx(
        request,
        sprint=sprint,
        status=status,
        team=team,
        tasks=tasks,
        summary=summary,
        scope_changes=scope_changes,
        progress_history=progress,
        sprint_day=sprint_day,
        on_track=on_track,
        team_members=[m["username"] for m in get_team_members(team["id"])],
        capacity=get_sprint_capacity(sprint["id"]),
        workload=workload,
        final_snapshot=final_snapshot_data,
        breadcrumbs=_breadcrumbs(
            ("Home", "/"),
            (team["name"], f"/teams/{team['id']}/sprints"),
            (_display_name(sprint["name"]), None),
        ),
        team_sub_nav_active="sprints",
    ))
```

**Route: `/teams/{team_id}/trends`** — line ~218

old_string:
```python
    return templates.TemplateResponse("team_trends.html", _ctx(request, team=team, trends=trends, range=range))
```

new_string:
```python
    return templates.TemplateResponse("team_trends.html", _ctx(
        request,
        team=team,
        trends=trends,
        range=range,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Trends", None)),
        team_sub_nav_active="trends",
    ))
```

### Step 3: Verify Python syntax

Run: `.venv/bin/python -c "from src.routes import pages; print('OK')"`
Expected: `OK`. If `SyntaxError` or `ImportError`, STOP and report BLOCKED.

### Step 4: Restart the app

Run: `./stop.sh && ./start.sh`
Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

### Step 5: Commit

```bash
git add src/routes/pages.py
git commit -m "$(cat <<'EOF'
feat(nav): wire breadcrumbs + team sub-nav into all routes

Each route handler now passes a tailored breadcrumbs list and the
right team_sub_nav_active value via _ctx(). Examples:
- /teams/X/sprints -> Home > LAN, sub-nav active=sprints
- /teams/X/trends  -> Home > LAN > Trends, sub-nav active=trends
- /sprint/X        -> Home > LAN > Sprint 8, sub-nav active=sprints

Sprint detail uses _display_name() to strip parenthetical dates from
the breadcrumb label (consistent with the rest of the UI).

Refs spec: docs/superpowers/specs/2026-05-04-navigation-fix-design.md
EOF
)"
```

---

## Task 3: Sprint detail prev/next sprint navigation

**Files:**
- Modify: `src/routes/pages.py` — sprint detail handler (around line 93–195) — add prev_sprint and next_sprint computation
- Modify: `templates/sprint_report.html:10-13` — replace `← Sprint History` with prev/next
- Modify: `templates/sprint_live.html:10-19` — add prev/next alongside refresh/close

### Step 1: Add prev/next computation in sprint detail handler

In `src/routes/pages.py`, find the sprint detail handler (`@router.get("/sprint/{sprint_id}", ...)` around line 93). Just before the `return templates.TemplateResponse(...)` call (around line 195), add prev/next computation.

Read the file to find the exact line:
```bash
grep -n "return templates.TemplateResponse(template" src/routes/pages.py
```

This identifies the line. Use `Edit` to insert just BEFORE that return statement:

```python
    # Compute prev/next sprint for navigation (by start_date within the same team)
    from src.services.sprint_service import get_team_sprints
    team_sprints = sorted(
        [s for s in get_team_sprints(team["id"]) if s.get("start_date")],
        key=lambda s: str(s["start_date"]),
    )
    prev_sprint = None
    next_sprint = None
    for i, s in enumerate(team_sprints):
        if s["id"] == sprint["id"]:
            if i > 0:
                prev_sprint = team_sprints[i - 1]
            if i < len(team_sprints) - 1:
                next_sprint = team_sprints[i + 1]
            break

```

Then add `prev_sprint=prev_sprint` and `next_sprint=next_sprint` to the `_ctx(...)` call's kwargs (right next to where we added breadcrumbs in Task 2).

The final `_ctx(...)` call should now look like:

```python
    return templates.TemplateResponse(template, _ctx(
        request,
        sprint=sprint,
        status=status,
        team=team,
        tasks=tasks,
        summary=summary,
        scope_changes=scope_changes,
        progress_history=progress,
        sprint_day=sprint_day,
        on_track=on_track,
        team_members=[m["username"] for m in get_team_members(team["id"])],
        capacity=get_sprint_capacity(sprint["id"]),
        workload=workload,
        final_snapshot=final_snapshot_data,
        prev_sprint=prev_sprint,
        next_sprint=next_sprint,
        breadcrumbs=_breadcrumbs(
            ("Home", "/"),
            (team["name"], f"/teams/{team['id']}/sprints"),
            (_display_name(sprint["name"]), None),
        ),
        team_sub_nav_active="sprints",
    ))
```

### Step 2: Update `templates/sprint_report.html` — replace `← Sprint History` with prev/next

The current top-bar (line 4-13) ends with:
```html
  <div class="actions">
    <a href="/teams/{{ team.id }}/sprints" class="btn btn-secondary">← Sprint History</a>
  </div>
```

Use `Edit` to replace the inner `<a>` with:

old_string:
```
    <a href="/teams/{{ team.id }}/sprints" class="btn btn-secondary">← Sprint History</a>
```

new_string:
```
    <div class="sprint-nav">
      {% if prev_sprint %}
        <a href="/sprint/{{ prev_sprint.id }}" class="btn btn-secondary">← {{ prev_sprint.name|display_name }}</a>
      {% else %}
        <span class="btn btn-secondary disabled" aria-disabled="true">← Earlier</span>
      {% endif %}
      {% if next_sprint %}
        <a href="/sprint/{{ next_sprint.id }}" class="btn btn-secondary">{{ next_sprint.name|display_name }} →</a>
      {% else %}
        <span class="btn btn-secondary disabled" aria-disabled="true">Later →</span>
      {% endif %}
    </div>
```

### Step 3: Update `templates/sprint_live.html` — add prev/next alongside existing buttons

The current actions area (lines 10-18) is:
```html
  <div class="actions">
    {% if status == 'active' %}
    <button class="btn btn-secondary" id="refresh-btn" onclick="refreshSprint({{ sprint.id }})">🔄 Refresh Now</button>
    <button class="btn btn-danger" onclick="closeSprint({{ sprint.id }})">🔒 Close Sprint</button>
    {% elif status == 'planning' %}
    <button class="btn btn-secondary" id="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
    <button class="btn btn-success" onclick="showCloseForecastModal()">📋 Close Forecast</button>
    {% endif %}
  </div>
```

Use `Edit` to add a sprint-nav block at the START of the `<div class="actions">` (i.e., right after the opening tag, before the `{% if %}`):

old_string:
```
  <div class="actions">
    {% if status == 'active' %}
```

new_string:
```
  <div class="actions">
    <div class="sprint-nav">
      {% if prev_sprint %}
        <a href="/sprint/{{ prev_sprint.id }}" class="btn btn-secondary">← {{ prev_sprint.name|display_name }}</a>
      {% else %}
        <span class="btn btn-secondary disabled" aria-disabled="true">← Earlier</span>
      {% endif %}
      {% if next_sprint %}
        <a href="/sprint/{{ next_sprint.id }}" class="btn btn-secondary">{{ next_sprint.name|display_name }} →</a>
      {% else %}
        <span class="btn btn-secondary disabled" aria-disabled="true">Later →</span>
      {% endif %}
    </div>
    {% if status == 'active' %}
```

### Step 4: Verify Python and templates parse

Run:
```bash
.venv/bin/python -c "from src.routes import pages; print('OK')"
.venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
for tpl in ['sprint_report.html', 'sprint_live.html']:
    env.get_template(tpl)
print('OK — templates parse')
"
```
Both should print `OK ...`.

### Step 5: Restart the app

Run: `./stop.sh && ./start.sh`
Expected: app starts.

### Step 6: Commit

```bash
git add src/routes/pages.py templates/sprint_report.html templates/sprint_live.html
git commit -m "$(cat <<'EOF'
feat(nav): prev/next sprint navigation in sprint detail

Replaces the "← Sprint History" button (which lived in the upper-right
corner — opposite to the conventional left-side back placement) with
prev/next sprint links in both report and live views. Breadcrumb
serves as the back-to-history path now.

Sprint detail handler computes prev/next by start_date within the
same team. Disabled spans render at the boundaries (earliest sprint:
"← Earlier" disabled; latest sprint: "Later →" disabled).

Refs spec: docs/superpowers/specs/2026-05-04-navigation-fix-design.md
EOF
)"
```

---

## Task 4: Home dedup — remove second `+ New Team` button

**Files:**
- Modify: `templates/home.html:38-40`

### Step 1: Confirm baseline

Run: `grep -n "New Team" templates/home.html`

Expected: two matches:
- line 39: `<a href="/teams/new" class="btn btn-primary">+ New Team</a>` (inside the `{% if teams %}` block, after the team list)
- line 48: `<a href="/teams/new" class="btn btn-primary">+ New Team</a>` (inside the `{% else %}` empty-state block — keep this one)

### Step 2: Remove the duplicate (the one at line 38-40, after the team list)

Use `Edit` to remove the surrounding `<div>`:

old_string:
```
  <div style="text-align:center; padding-top:8px;">
    <a href="/teams/new" class="btn btn-primary">+ New Team</a>
  </div>
```

new_string:
```
```

(Replace with nothing — empty string.)

### Step 3: Verify only one `+ New Team` link remains in home.html

Run: `grep -c "New Team" templates/home.html`
Expected: `1`. (Only the empty-state version remains.)

### Step 4: Verify the template still parses

Run:
```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('home.html'); print('OK')"
```
Expected: `OK`.

### Step 5: Restart the app

Run: `./stop.sh && ./start.sh`
Expected: app starts.

### Step 6: Commit

```bash
git add templates/home.html
git commit -m "$(cat <<'EOF'
fix(nav): remove duplicate + New Team button on home

The identity bar always shows "+ New Team" up top, so the second
button after the team list was redundant. The empty-state version
(only shown when no teams exist) stays — it's the user's only path
to create their first team.

Refs spec: docs/superpowers/specs/2026-05-04-navigation-fix-design.md
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| Three-row layout (identity / breadcrumbs / sub-nav) | Task 1 (foundation) — base.html + components |
| `templates/components/breadcrumbs.html` | Task 1 step 1 |
| `templates/components/team_sub_nav.html` | Task 1 step 2 |
| Identity bar with brand + New Team | Task 1 step 3 (base.html) |
| `_breadcrumbs(*pairs)` helper | Task 1 step 5 |
| `_ctx` extension with breadcrumbs + team_sub_nav_active | Task 1 step 5 |
| Routes pass breadcrumbs + active sub-nav | Task 2 (all 6 route handlers) |
| Prev/next sprint computation | Task 3 step 1 |
| Sprint detail templates use prev/next | Task 3 steps 2-3 (both report and live) |
| Remove `← Sprint History` from sprint_report | Task 3 step 2 |
| Remove duplicate `+ New Team` on home | Task 4 |
| Mobile @480px adjustments | Task 1 step 4 (CSS includes a @media block for 480px) |
| Identity bar `+` icon-only on mobile | Task 1 step 4 (CSS uses `font-size: 0` + `::before { content: "+" }`) |
| Sub-nav horizontal scroll | Task 1 step 4 (`overflow-x: auto`) |
| Sprint nav stacks on mobile | Task 1 step 4 (`flex-direction: column`) |
| Display_name applied to breadcrumbs | Task 2 step 2 (sprint detail breadcrumb uses `_display_name`) |
| Display_name applied to prev/next labels | Task 3 steps 2-3 (template uses `\|display_name`) |

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "appropriate error handling" / "similar to Task N". Every step has a concrete code block, command, or expected output.

**Type/name consistency:**
- `_breadcrumbs(*pairs)` defined in Task 1, called in Tasks 2 and 3 with same signature.
- `breadcrumbs`, `team_sub_nav_active`, `prev_sprint`, `next_sprint` — same names across `_ctx` parameters, route kwargs, and template variables.
- `team_sub_nav_active` values consistent across plan: `'sprints'`, `'trends'`, `'settings'`.
- `_display_name` (Sub-project 1's helper) reused in Task 2 step 2 (sprint detail breadcrumb) and via the `|display_name` filter in Task 3 templates.

**Inline fix during review:** Task 2 had a vestigial `from src.routes.pages import _display_name as _disp` line that doesn't make sense since the code is already inside `pages.py`. Removed it; the call uses `_display_name(...)` directly (which is defined at module scope by Sub-project 1).

**Scry verification (controller-side, between tasks):**

Each task has its own scry verification scenarios. Listed here for the controller's reference; the implementer subagent does NOT run them.

| Task | Scry checks |
|---|---|
| 1 | After commit: `scry.open /` → assert identity bar has `Sprint Reporter` + `+ New Team`, no team-list links in top nav. Pages load without errors. |
| 2 | `scry.navigate` to each of `/teams/new`, `/teams/1/sprints`, `/teams/1/trends`, `/teams/1/settings`, `/sprint/8` → for each: evaluate `.breadcrumbs` content, assert correct labels and clickable structure. Click breadcrumb (e.g. `LAN` from `/sprint/8`) → assert URL change. On team pages: evaluate `.team-sub-nav .tab.active` → assert correct tab marked. |
| 3 | `scry.open /sprint/8` → evaluate `.sprint-nav` → assert prev label is `← Sprint 7` (or similar), next is `Sprint 9 →`. Click prev → assert URL `/sprint/7`. Open earliest sprint → assert `← Earlier` is `aria-disabled`. |
| 4 | `scry.open /` → evaluate `document.querySelectorAll('a[href="/teams/new"]').length` → assert 1 (only identity bar's button). |
