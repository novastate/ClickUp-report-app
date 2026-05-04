# View Purpose & Messaging Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix six places where the UI says the wrong thing — confusing PLANNING badge, scary `-141.5h Available`, redundant period filter options, reverse-time velocity chart, missing help text on form values, hint-less Sync button.

**Architecture:** Six small targeted edits. One Jinja filter, one JS update, one route + template change, one JS reverse, two text additions. No backend logic changes. No DB changes.

**Tech Stack:** FastAPI + Jinja2, vanilla JS (Chart.js), CSS — same surface as Sub-projects 1 and 2.

**Spec:** `docs/superpowers/specs/2026-05-04-view-purpose-fix-design.md`

> **Verification note:** scry runs in the controller's MCP context. Implementer subagents commit code; the controller runs scry verification after each task's commit.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/routes/pages.py` | Modify | Add `_status_label` Jinja filter (Task 1); compute & pass `closed_count` to trends template (Task 3). |
| `templates/sprint_live.html` | Modify | Apply `\|status_label` to badge (Task 1). |
| `templates/sprint_history.html` | Modify | Apply `\|status_label` to badge; rename "Plan" → "Forecast" link text (Task 1). Update sync button text + tooltip (Task 6). |
| `templates/components/capacity_table.html` | Modify | `updateOverview()` JS shows "Set capacity ↓" hint when capacity is 0 (Task 2). |
| `templates/team_trends.html` | Modify | Conditional period filter buttons (Task 3); reverse `sprints` array for chart labels/data (Task 4). |
| `templates/team_settings.html` | Modify | Add `<small class="help-text">` lines under Metric Type and Capacity Mode (Task 5). |
| `static/style.css` | Modify | Append `.help-text` styles (Task 5). |

---

## Task 1: PLANNING → FORECAST (display only)

**Files:**
- Modify: `src/routes/pages.py` (add `_status_label` filter registration)
- Modify: `templates/sprint_live.html:8`
- Modify: `templates/sprint_history.html:42` and `:66`

### Step 1: Register `_status_label` filter

In `src/routes/pages.py`, find the existing `_display_name` filter registration (added in Sub-project 1 right after `templates = Jinja2Templates(...)`). Add `_status_label` immediately after it.

Use `Edit`:

old_string:
```
templates.env.filters["display_name"] = _display_name
```

new_string:
```
templates.env.filters["display_name"] = _display_name


def _status_label(state):
    return {"planning": "Forecast", "active": "Active", "closed": "Closed"}.get(state, state)


templates.env.filters["status_label"] = _status_label
```

### Step 2: Verify filter works
Run:
```bash
.venv/bin/python -c "
from src.routes.pages import templates
f = templates.env.filters['status_label']
assert f('planning') == 'Forecast', f('planning')
assert f('active') == 'Active', f('active')
assert f('closed') == 'Closed', f('closed')
assert f('weird') == 'weird', f('weird')
print('OK — all 4 cases pass')
"
```
Expected: `OK — all 4 cases pass`. If any assert fails, STOP and report BLOCKED.

### Step 3: Apply filter in `templates/sprint_live.html:8`

Use `Edit`:

old_string:
```
    <span class="badge badge-{{ status }}">{{ status|upper }}</span>
```

new_string:
```
    <span class="badge badge-{{ status }}">{{ status|status_label|upper }}</span>
```

### Step 4: Apply filter in `templates/sprint_history.html:42`

Use `Edit`:

old_string:
```
            <span class="badge-{{ sprint.status }}">{{ sprint.status | upper }}</span>
```

new_string:
```
            <span class="badge-{{ sprint.status }}">{{ sprint.status | status_label | upper }}</span>
```

### Step 5: Rename "Plan" → "Forecast" link in `templates/sprint_history.html:66`

Use `Edit`:

old_string:
```
              {% if sprint.status == 'active' %}Live View{% elif sprint.status == 'planning' %}Plan{% else %}Report{% endif %}
```

new_string:
```
              {% if sprint.status == 'active' %}Live View{% elif sprint.status == 'planning' %}Forecast{% else %}Report{% endif %}
```

### Step 6: Restart and verify
Run: `./stop.sh && ./start.sh`
Expected: app starts.

### Step 7: Commit
```bash
git add src/routes/pages.py templates/sprint_live.html templates/sprint_history.html
git commit -m "$(cat <<'EOF'
fix(ui): display 'FORECAST' instead of 'PLANNING' for pre-locked sprints

Adds a status_label Jinja filter that maps internal state strings to
user-facing labels: planning -> Forecast, active -> Active, closed ->
Closed. Internal status values (CSS classes, route logic) unchanged.

Sprint history's "Plan" action button is renamed to "Forecast" for
consistency. Resolves the audit complaint that "Iteration 1" looked
like it hadn't started yet because of the PLANNING label.

Refs spec: docs/superpowers/specs/2026-05-04-view-purpose-fix-design.md
EOF
)"
```

---

## Task 2: Replace `-141.5h Available` with capacity hint when capacity is 0

**Files:**
- Modify: `templates/components/capacity_table.html` — the JS `updateOverview()` function around lines 159-165

### Step 1: Locate the `updateOverview` function

Run: `grep -nA 7 "function updateOverview" templates/components/capacity_table.html`

Expected: line ~159 with current body:
```javascript
  function updateOverview(cap, assigned) {
    if (!planCapEl) return;
    const avail = cap - assigned;
    planCapEl.textContent = fmt(cap) + unit;
    planAvailEl.textContent = fmt(avail) + unit;
    planAvailEl.style.color = avail < 0 ? '#e53e3e' : '#38a169';
  }
```

### Step 2: Replace with cap-zero-aware version

Use `Edit`:

old_string:
```
  function updateOverview(cap, assigned) {
    if (!planCapEl) return;
    const avail = cap - assigned;
    planCapEl.textContent = fmt(cap) + unit;
    planAvailEl.textContent = fmt(avail) + unit;
    planAvailEl.style.color = avail < 0 ? '#e53e3e' : '#38a169';
  }
```

new_string:
```
  function updateOverview(cap, assigned) {
    if (!planCapEl) return;
    if (cap === 0) {
      planCapEl.textContent = '—';
      planAvailEl.innerHTML = '<a href="#capacity-panel" style="font-size:13px; color:#4299e1; text-decoration:none;">Set capacity ↓</a>';
      planAvailEl.style.color = '';
      return;
    }
    const avail = cap - assigned;
    planCapEl.textContent = fmt(cap) + unit;
    planAvailEl.textContent = fmt(avail) + unit;
    planAvailEl.style.color = avail < 0 ? '#e53e3e' : '#38a169';
  }
```

### Step 3: Verify the template still parses
Run:
```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('components/capacity_table.html'); print('OK')"
```
Expected: `OK`.

### Step 4: Restart the app
Run: `./stop.sh && ./start.sh`

### Step 5: Commit
```bash
git add templates/components/capacity_table.html
git commit -m "$(cat <<'EOF'
fix(ui): replace '-141.5h Available' with capacity hint when cap=0

When team capacity hasn't been set yet, the Planning Overview's
Available stat showed a large negative number in red — looking like
a critical overbooking warning. Now shows "Set capacity ↓" linked to
the existing capacity panel below. Real overbooking still renders red.

Refs spec: docs/superpowers/specs/2026-05-04-view-purpose-fix-design.md
EOF
)"
```

---

## Task 3: Period filter only shows useful options

**Files:**
- Modify: `src/routes/pages.py` — trends route (line ~213) compute `closed_count`
- Modify: `templates/team_trends.html:10-12` — wrap filter buttons in conditionals

### Step 1: Update trends route

Find the trends route in `src/routes/pages.py`:

```bash
grep -nA 5 "def team_trends_page" src/routes/pages.py
```

Expected: a few lines around line ~213.

Use `Edit`:

old_string:
```python
@router.get("/teams/{team_id}/trends", response_class=HTMLResponse)
def team_trends_page(request: Request, team_id: int, range: int = 8):
    team = get_team(team_id)
    from src.services.trend_service import get_team_trends
    trends = get_team_trends(team_id, limit=range if range > 0 else None)
    return templates.TemplateResponse("team_trends.html", _ctx(
        request,
        team=team,
        trends=trends,
        range=range,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Trends", None)),
        team_sub_nav_active="trends",
    ))
```

new_string:
```python
@router.get("/teams/{team_id}/trends", response_class=HTMLResponse)
def team_trends_page(request: Request, team_id: int, range: int = 8):
    team = get_team(team_id)
    from src.services.trend_service import get_team_trends
    trends = get_team_trends(team_id, limit=range if range > 0 else None)
    # Always count ALL closed sprints (independent of the range filter) so we know
    # which filter buttons to show
    all_trends = get_team_trends(team_id, limit=None)
    closed_count = len(all_trends.get("sprints", []))
    return templates.TemplateResponse("team_trends.html", _ctx(
        request,
        team=team,
        trends=trends,
        range=range,
        closed_count=closed_count,
        breadcrumbs=_breadcrumbs(("Home", "/"), (team["name"], f"/teams/{team['id']}/sprints"), ("Trends", None)),
        team_sub_nav_active="trends",
    ))
```

### Step 2: Update period filter in `templates/team_trends.html:10-12`

Use `Edit`:

old_string:
```
    <a href="?range=4" class="btn {% if range == 4 %}btn-primary{% else %}btn-secondary{% endif %}">Last 4</a>
    <a href="?range=8" class="btn {% if range == 8 %}btn-primary{% else %}btn-secondary{% endif %}">Last 8</a>
    <a href="?range=0" class="btn {% if range == 0 %}btn-primary{% else %}btn-secondary{% endif %}">All</a>
```

new_string:
```
    {% if closed_count > 4 %}
    <a href="?range=4" class="btn {% if range == 4 %}btn-primary{% else %}btn-secondary{% endif %}">Last 4</a>
    {% endif %}
    {% if closed_count > 8 %}
    <a href="?range=8" class="btn {% if range == 8 %}btn-primary{% else %}btn-secondary{% endif %}">Last 8</a>
    {% endif %}
    <a href="?range=0" class="btn {% if range == 0 %}btn-primary{% else %}btn-secondary{% endif %}">All</a>
```

### Step 3: Verify Python and template parse
```bash
.venv/bin/python -c "from src.routes import pages; print('OK')"
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('team_trends.html'); print('OK')"
```
Both should print `OK`.

### Step 4: Restart the app
Run: `./stop.sh && ./start.sh`

### Step 5: Commit
```bash
git add src/routes/pages.py templates/team_trends.html
git commit -m "$(cat <<'EOF'
fix(ui): period filter only shows useful options

Last 4, Last 8, and All all returned identical data when the team has
fewer than 4-8 closed sprints. Now: Last 4 only shows when there are
more than 4; Last 8 only when more than 8; All always visible.

Trends route computes closed_count independently of the active range
filter so the buttons reflect the team's full sprint history.

Refs spec: docs/superpowers/specs/2026-05-04-view-purpose-fix-design.md
EOF
)"
```

---

## Task 4: Velocity chart oldest→newest

**Files:**
- Modify: `templates/team_trends.html:195-196` (the JS that builds the `sprints` array for charts)

### Step 1: Locate the charts setup

Run: `grep -nA 3 "trends.sprints | tojson" templates/team_trends.html`

Expected: line ~195 with `const sprints = {{ trends.sprints | tojson }};` and line ~196 with the labels generation.

### Step 2: Reverse the array for charts

Use `Edit`:

old_string:
```
  const sprints = {{ trends.sprints | tojson }};
  const labels = sprints.map(s => (s.sprint_name || '').replace(/\s*\([^)]*\)\s*$/, '').trim());
```

new_string:
```
  // Reverse so charts plot oldest -> newest left-to-right
  // (.slice() clones so we don't mutate the array used by the table elsewhere)
  const sprints = ({{ trends.sprints | tojson }}).slice().reverse();
  const labels = sprints.map(s => (s.sprint_name || '').replace(/\s*\([^)]*\)\s*$/, '').trim());
```

### Step 3: Verify template parses
```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('team_trends.html'); print('OK')"
```
Expected: `OK`.

### Step 4: Restart
Run: `./stop.sh && ./start.sh`

### Step 5: Commit
```bash
git add templates/team_trends.html
git commit -m "$(cat <<'EOF'
fix(ui): velocity chart sorts oldest -> newest left-to-right

Trends data is delivered newest-first (correct for the table below
the chart), but rendering it left-to-right that way puts the most
recent sprint on the LEFT — opposite to how time-series data
conventionally reads. Reverse the array (cloned, so the table still
gets newest-first).

Affects velocity bar chart, completion rate line, forecast accuracy
line — they all share the same labels/sprints variables.

Refs spec: docs/superpowers/specs/2026-05-04-view-purpose-fix-design.md
EOF
)"
```

---

## Task 5: Help text on Metric Type and Capacity Mode

**Files:**
- Modify: `templates/team_settings.html` — add `<small class="help-text">` after each radio-group label
- Modify: `static/style.css` — append `.help-text` styles

### Step 1: Locate the labels

Run: `grep -nE "<label>(Metric Type|Capacity Mode)" templates/team_settings.html`

Expected: 2 lines, around `:44` (Metric Type) and `:65` (Capacity Mode).

### Step 2: Add help text under "Metric Type"

Use `Edit`:

old_string:
```
      <div class="form-group">
        <label>Metric Type</label>
        <div class="radio-group">
          <label>
            <input type="radio" name="metric_type" value="task_count"
```

new_string:
```
      <div class="form-group">
        <label>Metric Type</label>
        <small class="help-text">How sprint progress is measured. Task Count = number of tasks done. Story Points = points completed. Hours = hours completed.</small>
        <div class="radio-group">
          <label>
            <input type="radio" name="metric_type" value="task_count"
```

### Step 3: Add help text under "Capacity Mode"

Use `Edit`:

old_string:
```
      <div class="form-group">
        <label>Capacity Mode</label>
        <div class="radio-group">
          <label>
            <input type="radio" name="capacity_mode" value="none"
```

new_string:
```
      <div class="form-group">
        <label>Capacity Mode</label>
        <small class="help-text">Where to track effort capacity. Individual = per team member, set on each sprint. Team = single total per sprint. None = don't track capacity.</small>
        <div class="radio-group">
          <label>
            <input type="radio" name="capacity_mode" value="none"
```

### Step 4: Append `.help-text` CSS to `static/style.css`

Append at the end of the file:

```css

/* Form help text under labels */
.help-text {
  display: block;
  color: #718096;
  font-size: 12px;
  margin: 4px 0 8px 0;
  line-height: 1.4;
}
```

### Step 5: Verify CSS balances
```bash
.venv/bin/python -c "css = open('static/style.css').read(); print('balanced' if css.count('{') == css.count('}') else 'IMBALANCED')"
```
Expected: `balanced`.

### Step 6: Verify template parses
```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('team_settings.html'); print('OK')"
```
Expected: `OK`.

### Step 7: Restart
Run: `./stop.sh && ./start.sh`

### Step 8: Commit
```bash
git add templates/team_settings.html static/style.css
git commit -m "$(cat <<'EOF'
fix(ui): help text under Metric Type and Capacity Mode

New users had to guess what "Task Count vs Story Points vs Hours"
or "Individual vs Team vs None" meant. Adds a short inline
explanation under each label, styled small and muted.

Refs spec: docs/superpowers/specs/2026-05-04-view-purpose-fix-design.md
EOF
)"
```

---

## Task 6: Sync Sprints — clearer text + tooltip

**Files:**
- Modify: `templates/sprint_history.html:10-12` (the sync button)

### Step 1: Locate the button

Run: `grep -nA 3 "id=\"sync-btn\"" templates/sprint_history.html`

Expected: lines around `:10` showing the current button.

### Step 2: Update the button

Use `Edit`:

old_string:
```
    <button class="btn btn-primary" id="sync-btn" onclick="syncSprints({{ team.id }})">
      🔄 Sync Sprints
    </button>
```

new_string:
```
    <button class="btn btn-primary" id="sync-btn" onclick="syncSprints({{ team.id }})"
            title="Pulls all sprint lists from the team's ClickUp folder into this view. Doesn't push anything to ClickUp.">
      🔄 Sync from ClickUp
    </button>
```

### Step 3: Verify template parses
```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('sprint_history.html'); print('OK')"
```
Expected: `OK`.

### Step 4: Restart
Run: `./stop.sh && ./start.sh`

### Step 5: Commit
```bash
git add templates/sprint_history.html
git commit -m "$(cat <<'EOF'
fix(ui): clearer Sync button — 'Sync from ClickUp' + explainer tooltip

"Sync Sprints" didn't tell new users where data came from or whether
the sync wrote back to ClickUp. Renamed to "Sync from ClickUp" and
added a title attribute that explains the direction explicitly.

Refs spec: docs/superpowers/specs/2026-05-04-view-purpose-fix-design.md
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec item | Plan task |
|---|---|
| Item 1 — PLANNING → FORECAST display | Task 1 (filter + 3 templates) |
| Item 2 — `-141.5h` hint when cap=0 | Task 2 (capacity_table.html JS) |
| Item 3 — period filter dynamic | Task 3 (pages.py + team_trends.html) |
| Item 4 — velocity chart oldest-first | Task 4 (team_trends.html JS) |
| Item 5 — help text under Metric Type / Capacity Mode | Task 5 (team_settings.html + CSS) |
| Item 6 — Sync button text + tooltip | Task 6 (sprint_history.html) |
| `_status_label` filter | Task 1 step 1 |
| Edge case "unknown status" | Task 1's filter has graceful fallback (returns input unchanged) |
| Edge case "0 capacity" | Task 2 step 2 (`if (cap === 0)` branch) |
| Edge case "exactly 4 closed sprints" | Task 3 step 2 (`closed_count > 4` strict) |
| Verification table | Each task has a "scry" task in the controller's plan; the implementer just commits and the controller runs scry between tasks |

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "appropriate error handling" / "similar to Task N". Every step has concrete code or commands.

**Type/name consistency:**
- `_status_label` (Python) and `status_label` (Jinja filter name) consistent across Task 1.
- `closed_count` (Python kwarg) used in Task 3 step 1 and referenced as `closed_count` in template Task 3 step 2.
- `.help-text` (CSS class) consistent in Task 5 templates and CSS.
- All filters added in this and prior sub-projects (`display_name`, `status_label`) registered the same way (`templates.env.filters["..."] = func`).

**Inline fixes during review:** None needed — spec is concrete and tasks map 1:1.

---

## Scry verification (controller-side, between tasks)

| Task | Scry checks |
|---|---|
| 1 | After commit: `scry.open /sprint/9` (planning sprint), `scry.evaluate` to read `.badge`'s text → assert `FORECAST`, NOT `PLANNING`. Then on `/teams/1/sprints`, find a planning row's action-link text → assert it's `Forecast`, NOT `Plan`. |
| 2 | `scry.open` on a sprint with capacity_mode=individual but cap=0 (e.g. Iteration 1 if such exists). `scry.evaluate` to read `#plan-avail-value` → assert it contains `Set capacity` (link), NOT a negative number. |
| 3 | `scry.evaluate` on `/teams/1/trends` → count `.actions a[href^='?range=']` (period filter buttons). LAN has 3 closed sprints, so should be exactly 1 (`All`). |
| 4 | `scry.evaluate` on `/teams/1/trends` → assert `Chart.getChart('velocityChart').data.labels[0]` is the oldest (e.g. `Sprint 6`), not `Sprint 8`. |
| 5 | `scry.evaluate` on `/teams/new` → count `.help-text` elements → assert ≥ 2. Spot-check that one of them contains the word "Task Count". |
| 6 | `scry.evaluate` on `/teams/1/sprints` → `#sync-btn` element → assert `.title` attribute exists and `.textContent` contains `from ClickUp`. |
