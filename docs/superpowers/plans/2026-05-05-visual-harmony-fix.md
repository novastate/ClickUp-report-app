# Visual Harmony Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dark `.top-bar` (which stacks redundantly under the new identity bar) with a light `.page-header` on four templates, drop it entirely from home, fix per-row action buttons by migrating `btn-light` → `btn-secondary`, and clean up dead CSS.

**Architecture:** Two tasks. Task 1 adds `.page-header` CSS and migrates all five templates in one coherent commit (all visible UI changes ship together). Task 2 removes the now-unused `.top-bar` and `.btn-light` CSS as a clean cleanup commit.

**Tech Stack:** Plain HTML + CSS. No JS, no backend.

**Spec:** `docs/superpowers/specs/2026-05-05-visual-harmony-design.md`

> **Verification note:** scry runs in the controller's MCP context. Implementer subagents commit code; the controller runs scry verification after each task's commit.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `static/style.css` | Task 1: append `.page-header` styles. Task 2: remove `.top-bar` and `.btn-light` rules. |
| `templates/sprint_history.html` | Task 1: `.top-bar` → `.page-header`, drop duplicate Settings link, `btn-light` → `btn-secondary` |
| `templates/team_trends.html` | Task 1: `.top-bar` → `.page-header`, drop redundant `← Sprint History` link |
| `templates/sprint_report.html` | Task 1: `.top-bar` → `.page-header` |
| `templates/sprint_live.html` | Task 1: `.top-bar` → `.page-header` |
| `templates/home.html` | Task 1: remove `.top-bar` entirely (Sprint Reporter is in identity bar) |

---

## Task 1: Add `.page-header`, migrate all templates, fix btn-light

**Files:**
- Modify: `static/style.css` (append)
- Modify: `templates/sprint_history.html`
- Modify: `templates/team_trends.html`
- Modify: `templates/sprint_report.html`
- Modify: `templates/sprint_live.html`
- Modify: `templates/home.html`

### Step 1: Append `.page-header` CSS to `static/style.css`

Append this exact block to the end of the file:

```css

/* --- Page header (replaces .top-bar on team-context pages) ------------- */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #edf2f7;
}
.page-header h1 {
  margin: 0;
  font-size: 1.4rem;
  color: #1a202c;
}
.page-header .title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.page-header .meta {
  color: #718096;
  font-size: 13px;
}
.page-header .actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
```

### Step 2: Convert `templates/sprint_history.html`

Use `Edit`:

old_string:
```
<div class="top-bar">
  <div>
    <h1>{{ team.name }}</h1>
    <span class="meta">Sprint History</span>
  </div>
  <div class="actions">
    <button class="btn btn-primary" id="sync-btn" onclick="syncSprints({{ team.id }})"
            title="Pulls all sprint lists from the team's ClickUp folder into this view. Doesn't push anything to ClickUp.">
      🔄 Sync from ClickUp
    </button>
    <a href="/teams/{{ team.id }}/settings" class="btn btn-secondary">⚙ Settings</a>
  </div>
</div>
```

new_string:
```
<header class="page-header">
  <div class="title">
    <h1>{{ team.name }}</h1>
    <span class="meta">Sprint History</span>
  </div>
  <div class="actions">
    <button class="btn btn-primary" id="sync-btn" onclick="syncSprints({{ team.id }})"
            title="Pulls all sprint lists from the team's ClickUp folder into this view. Doesn't push anything to ClickUp.">
      🔄 Sync from ClickUp
    </button>
  </div>
</header>
```

(Drops the duplicate `⚙ Settings` link.)

Then `Edit` again to migrate `btn-light` → `btn-secondary`:

old_string:
```
            <a href="/sprint/{{ sprint.id }}" class="btn {% if sprint.status == 'active' %}btn-primary{% else %}btn-light{% endif %}" style="font-size:11px; padding:4px 10px;">
```

new_string:
```
            <a href="/sprint/{{ sprint.id }}" class="btn {% if sprint.status == 'active' %}btn-primary{% else %}btn-secondary{% endif %}" style="font-size:11px; padding:4px 10px;">
```

### Step 3: Convert `templates/team_trends.html`

Use `Edit`:

old_string:
```
<div class="top-bar">
  <div>
    <h1 style="display:inline">{{ team.name }}</h1>
    <span class="meta">Performance Trends</span>
  </div>
  <div class="actions">
    {% if closed_count > 4 %}
    <a href="?range=4" class="btn {% if range == 4 %}btn-primary{% else %}btn-secondary{% endif %}">Last 4</a>
    {% endif %}
    {% if closed_count > 8 %}
    <a href="?range=8" class="btn {% if range == 8 %}btn-primary{% else %}btn-secondary{% endif %}">Last 8</a>
    {% endif %}
    <a href="?range=0" class="btn {% if range == 0 %}btn-primary{% else %}btn-secondary{% endif %}">All</a>
    <a href="/teams/{{ team.id }}/sprints" class="btn btn-secondary">← Sprint History</a>
  </div>
</div>
```

new_string:
```
<header class="page-header">
  <div class="title">
    <h1>{{ team.name }}</h1>
    <span class="meta">Performance Trends</span>
  </div>
  <div class="actions">
    {% if closed_count > 4 %}
    <a href="?range=4" class="btn {% if range == 4 %}btn-primary{% else %}btn-secondary{% endif %}">Last 4</a>
    {% endif %}
    {% if closed_count > 8 %}
    <a href="?range=8" class="btn {% if range == 8 %}btn-primary{% else %}btn-secondary{% endif %}">Last 8</a>
    {% endif %}
    <a href="?range=0" class="btn {% if range == 0 %}btn-primary{% else %}btn-secondary{% endif %}">All</a>
  </div>
</header>
```

(Drops the redundant `← Sprint History` link — sub-nav has it.)

### Step 4: Convert `templates/sprint_report.html`

Use `Edit`:

old_string:
```
<div class="top-bar">
  <div>
    <h1 style="display:inline">{{ sprint.name|display_name }}</h1>
    <span class="meta">{{ sprint.start_date }} — {{ sprint.end_date }}</span>
    <span class="badge badge-closed">CLOSED</span>
  </div>
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
  </div>
</div>
```

new_string:
```
<header class="page-header">
  <div class="title">
    <h1>{{ sprint.name|display_name }}</h1>
    <span class="meta">{{ sprint.start_date }} — {{ sprint.end_date }}</span>
    <span class="badge badge-closed">CLOSED</span>
  </div>
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
  </div>
</header>
```

### Step 5: Convert `templates/sprint_live.html`

Use `Edit`:

old_string:
```
<div class="top-bar">
  <div>
    <h1 style="display:inline" data-sprint-id="{{ sprint.id }}">{{ sprint.name|display_name }}</h1>
    <span class="meta">{{ sprint.start_date }} — {{ sprint.end_date }}</span>
    <span class="badge badge-{{ status }}">{{ status|status_label|upper }}</span>
  </div>
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
    <button class="btn btn-secondary" id="refresh-btn" onclick="refreshSprint({{ sprint.id }})">🔄 Refresh Now</button>
    <button class="btn btn-danger" onclick="closeSprint({{ sprint.id }})">🔒 Close Sprint</button>
    {% elif status == 'planning' %}
    <button class="btn btn-secondary" id="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
    <button class="btn btn-success" onclick="showCloseForecastModal()">📋 Close Forecast</button>
    {% endif %}
  </div>
</div>
```

new_string:
```
<header class="page-header">
  <div class="title">
    <h1 data-sprint-id="{{ sprint.id }}">{{ sprint.name|display_name }}</h1>
    <span class="meta">{{ sprint.start_date }} — {{ sprint.end_date }}</span>
    <span class="badge badge-{{ status }}">{{ status|status_label|upper }}</span>
  </div>
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
    <button class="btn btn-secondary" id="refresh-btn" onclick="refreshSprint({{ sprint.id }})">🔄 Refresh Now</button>
    <button class="btn btn-danger" onclick="closeSprint({{ sprint.id }})">🔒 Close Sprint</button>
    {% elif status == 'planning' %}
    <button class="btn btn-secondary" id="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
    <button class="btn btn-success" onclick="showCloseForecastModal()">📋 Close Forecast</button>
    {% endif %}
  </div>
</header>
```

### Step 6: Remove `.top-bar` from `templates/home.html`

Use `Edit`:

old_string:
```
<div class="top-bar">
  <div>
    <h1 style="display:inline">Sprint Reporter</h1>
  </div>
</div>

```

new_string:
```
```

(Replace with empty string — block fully removed. The blank line after it is also removed for tidiness.)

### Step 7: Verify all 5 templates parse

Run:
```bash
.venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
for tpl in ['sprint_history.html', 'team_trends.html', 'sprint_report.html', 'sprint_live.html', 'home.html']:
    env.get_template(tpl)
print('OK — 5 templates parse')
"
```
Expected: `OK — 5 templates parse`. Else STOP.

### Step 8: Verify no `.top-bar` references remain in templates

Run: `grep -rn 'class="top-bar"' templates/`
Expected: zero matches.

### Step 9: Verify no `btn-light` references remain in templates

Run: `grep -rn 'btn-light' templates/`
Expected: zero matches.

### Step 10: Verify `.page-header` is in CSS

Run: `grep -c "\.page-header" static/style.css`
Expected: at least 5 matches (the various `.page-header*` selectors).

### Step 11: CSS balance

Run:
```bash
.venv/bin/python -c "css = open('static/style.css').read(); print('balanced' if css.count('{') == css.count('}') else 'IMBALANCED')"
```
Expected: `balanced`. Else STOP.

### Step 12: Restart

Run: `./stop.sh && ./start.sh`
Expected: app starts.

### Step 13: Commit

```bash
git add static/style.css templates/sprint_history.html templates/team_trends.html templates/sprint_report.html templates/sprint_live.html templates/home.html
git commit -m "$(cat <<'EOF'
fix(ui): replace dark .top-bar with light .page-header

The new identity bar (Sub-project 2) plus the original .top-bar made
team-context pages stack two dark headers — visually fragmented. This
replaces .top-bar with a light .page-header on four team-context
templates, removes .top-bar entirely from home (Sprint Reporter is
already in the identity bar), drops the duplicate Settings link from
sprint history's actions area, drops the redundant "← Sprint History"
link from trends actions, and migrates the per-row action buttons
from btn-light (nearly invisible) to btn-secondary.

Refs spec: docs/superpowers/specs/2026-05-05-visual-harmony-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Task 2: Remove dead CSS (`.top-bar` and `.btn-light`)

After Task 1 ships, no template references `.top-bar` or `.btn-light` anymore. Remove the CSS rules.

**Files:**
- Modify: `static/style.css`

### Step 1: Confirm no usage

Run: `grep -rn 'btn-light\|class="top-bar"\|top-bar' templates/`
Expected: zero matches in template files.

If any matches appear, STOP — Task 1 missed something. Don't proceed.

### Step 2: Locate and remove `.top-bar` rules

The block in `static/style.css` (lines roughly 62-95) covers `.top-bar`, `.top-bar h1`, `.top-bar .meta`, `.top-bar .actions`. Find them and remove.

Use `Edit`:

old_string:
```
.top-bar {
  background: #1a202c;
  color: #e2e8f0;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.top-bar h1 {
  color: #f7fafc;
  font-size: 1.4rem;
}

.top-bar .meta {
  display: inline-block;
  margin-left: 12px;
  color: #a0aec0;
  font-size: 13px;
}

.top-bar .actions {
  display: flex;
  gap: 8px;
}
```

new_string:
```
```

(If the exact block doesn't match — e.g. spacing or trailing rules differ — use a smaller, exact-matching `Edit` per rule, or read the file first and adjust the old_string to match.)

### Step 3: Locate and remove `.btn-light` rules

Use `Edit`:

old_string:
```
.btn-light, a.btn.btn-light { background: #edf2f7; color: #4a5568 !important; border-color: #e2e8f0; }
.btn-light:hover, a.btn.btn-light:hover { background: #e2e8f0; color: #2d3748 !important; text-decoration: none; }
```

new_string:
```
```

### Step 4: CSS still balances

Run:
```bash
.venv/bin/python -c "css = open('static/style.css').read(); print('balanced' if css.count('{') == css.count('}') else 'IMBALANCED')"
```
Expected: `balanced`.

### Step 5: Confirm `.top-bar` and `.btn-light` are gone from CSS

Run: `grep -nE '\.top-bar|\.btn-light' static/style.css`
Expected: zero matches.

### Step 6: Restart

Run: `./stop.sh && ./start.sh`

### Step 7: Commit

```bash
git add static/style.css
git commit -m "$(cat <<'EOF'
chore: remove dead CSS — .top-bar and .btn-light

Both classes have zero remaining users in templates after the
visual-harmony migration. Removing them keeps the stylesheet honest.
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Self-Review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| `.page-header` CSS | Task 1 step 1 |
| sprint_history.html top-bar → page-header + drop Settings | Task 1 step 2 |
| sprint_history.html btn-light migration | Task 1 step 2 (second edit) |
| team_trends.html top-bar → page-header + drop "← Sprint History" | Task 1 step 3 |
| sprint_report.html top-bar → page-header | Task 1 step 4 |
| sprint_live.html top-bar → page-header | Task 1 step 5 |
| home.html: remove .top-bar entirely | Task 1 step 6 |
| Remove .top-bar CSS | Task 2 step 2 |
| Remove .btn-light CSS | Task 2 step 3 |

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "appropriate error handling" / "similar to Task N". All edits show concrete old/new strings.

**Type/name consistency:** `.page-header`, `.title`, `.actions`, `.meta` — same names in CSS and all 4 template usages.

**Edge cases:**
- The `style="display:inline"` attribute on `<h1>` was used because the original `.top-bar h1` had certain styling. The new `.page-header h1` is `display: block` by default but lives inside a `.title` flex wrapper, so visual outcome is similar. Removing `style="display:inline"` from each h1 (already done in plan).
- `data-sprint-id` attribute on `sprint_live.html`'s h1 stays — it's used by JS that resolves sprint identity, doesn't affect display.

---

## Scry verification (controller-side)

After Task 1:

| Check | Test |
|---|---|
| One dark band per page | `scry.evaluate` on `/teams/1/sprints` → `Array.from(document.querySelectorAll('header, nav, .top-bar, .page-header, .identity-bar')).filter(el => getComputedStyle(el).backgroundColor.match(/rgb\(2[6-9],\s*3\d,\s*\d+\)/)).length` should be **exactly 1** |
| `.top-bar` gone from DOM | `scry.evaluate` → `document.querySelector('.top-bar') === null` on each of /, /teams/1/sprints, /teams/1/trends, /sprint/8 |
| `.page-header` present | Same routes (except home) → `document.querySelector('.page-header') !== null` |
| Duplicate Settings link gone | `/teams/1/sprints` → `Array.from(document.querySelectorAll('.page-header a[href$="/settings"]')).length === 0` |
| `← Sprint History` link gone in trends | `/teams/1/trends` → `Array.from(document.querySelectorAll('.page-header a[href$="/sprints"]')).length === 0` |
| `btn-light` gone from DOM | All routes → `document.querySelectorAll('.btn-light').length === 0` |
| Action buttons visible | `/teams/1/sprints` → first row's per-row link computed `background-color` should NOT be the old `btn-light` `#edf2f7`. Probe and check the rendered class is `btn-secondary`. |
| Visual snapshot | `scry.snapshot { inline: true }` on `/teams/1/sprints` — should show ONE dark band at top, then breadcrumbs, then sub-nav, then light page-header, then content. |

After Task 2: smoke check — pages still render, no visual regression.
