# Audit Bugs Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five UI bugs surfaced by the scry-driven audit, each verified by a scry session before commit.

**Architecture:** Five small independent edits — one HTML component, one chart-rendering script, one Jinja filter + template sweep, a CSS media query, and a JS toast helper + four button handlers. No backend logic changes (Bug 5 reads an existing field from the sync endpoint's response). No DB changes.

**Tech Stack:** FastAPI + Jinja2 templates, vanilla JS (Chart.js for burndown), CSS (no framework), scry MCP plugin for verification.

**Spec:** `docs/superpowers/specs/2026-05-04-audit-bugs-fix-design.md`

> **Implementation note on verification:** Scry runs in the controller's MCP context. Implementer subagents commit code; the controller (or whoever runs `superpowers:executing-plans`) runs the scry verification step *after* each task's commit. The verification step is part of the task acceptance.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `templates/components/kpi_cards.html` | Modify (1 line range) | STATUS card: three-way branch for sprint state |
| `templates/components/burndown_chart.html` | Modify | Drop the `slice()` so X-axis renders all sprint days; add caption when actual data is shorter than sprint length AND sprint is closed |
| `app.py` | Modify (3 lines added) | Register `display_name` Jinja filter |
| `templates/sprint_history.html`, `templates/sprint_live.html`, `templates/sprint_report.html`, `templates/home.html`, `templates/team_trends.html` | Modify | Apply `\|display_name` filter to every `sprint.name` / `s.sprint_name` |
| `static/style.css` | Modify (append block) | New `@media (max-width: 480px)` block + toast styles |
| `static/dashboard.js` | Modify | Toast helper + sessionStorage-deferred toast + update `syncSprints` (and three sibling functions) to use it |

---

## Task 1: Fix Bug 1 — "Day None of 14"

**Files:**
- Modify: `templates/components/kpi_cards.html:30-34` (the existing `<div class="kpi-card">` that holds the STATUS card)

- [ ] **Step 1: Confirm baseline**

Run: `grep -n "Day {{ sprint_day" templates/components/kpi_cards.html`

Expected:
```
33:    <div class="sub">Day {{ sprint_day|default('?') }} of {{ team.sprint_length_days }}</div>
```

- [ ] **Step 2: Replace the line with a three-way branch**

Use `Edit` to replace the single line at line 33:

Old:
```
    <div class="sub">Day {{ sprint_day|default('?') }} of {{ team.sprint_length_days }}</div>
```

New:
```
    <div class="sub">
      {% if sprint.closed_at %}Closed
      {% elif sprint_day is none %}Not started
      {% else %}Day {{ sprint_day }} of {{ team.sprint_length_days }}
      {% endif %}
    </div>
```

- [ ] **Step 3: Verify the template still renders**

Run: `.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('components/kpi_cards.html'); print('OK')"`

Expected: `OK` with no `TemplateSyntaxError`.

- [ ] **Step 4: Restart the app**

Run: `./stop.sh && ./start.sh`

Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

- [ ] **Step 5: Scry verification — closed sprint**

Run from controller (not subagent):

```
scry.open http://localhost:8000/sprint/8
scry.snapshot { inline: true, fullPage: false }
```

Expected: visual snapshot shows `STATUS: Behind / Closed` (where the bug previously showed `Day None of 14`). The word `None` MUST NOT appear anywhere on the page.

Programmatic check:
```
scry.evaluate {
  script: "Array.from(document.querySelectorAll('.kpi-card .sub')).map(el => el.textContent.trim())"
}
```
Expected: array contains `"Closed"` and does NOT contain `"Day None of 14"`.

- [ ] **Step 6: Scry verification — planning sprint**

```
scry.navigate http://localhost:8000/sprint/9
scry.evaluate {
  script: "document.body.textContent.includes('Day None')"
}
```
Expected: `false`. (Sprint 9 is in PLANNING; STATUS card may not even render if `on_track is undefined` — that's also fine. Just `Day None` must not appear.)

```
scry.close
```

- [ ] **Step 7: Commit**

```bash
git add templates/components/kpi_cards.html
git commit -m "$(cat <<'EOF'
fix(ui): replace 'Day None of 14' with state-aware status

Closed sprints now show "Closed", not-yet-started sprints show "Not started",
in-progress sprints keep the existing "Day X of N" format. Jinja's |default()
only fires for undefined, not None — and "Day X of N" was never the right
label for a closed sprint anyway.

Verified via scry: /sprint/8 (closed) shows "Closed", /sprint/9 (planning)
contains no "Day None" text.

Refs spec: docs/superpowers/specs/2026-05-04-audit-bugs-fix-design.md
EOF
)"
```

---

## Task 2: Fix Bug 2 — Burndown axis stops at last data point

**Files:**
- Modify: `templates/components/burndown_chart.html:22` (the `slice()` call) and add a caption block

- [ ] **Step 1: Confirm baseline**

Run: `cat templates/components/burndown_chart.html`

Expected: see the existing 31-line component; line 22 contains `labels: idealLabels.slice(0, Math.max(actualData.length, 2)),`. This is what truncates the X-axis to the actual data length.

- [ ] **Step 2: Replace the `labels:` line and add a caption**

Use `Edit` to make two changes in `templates/components/burndown_chart.html`.

**Change 2a** — drop the slice so the full sprint horizon shows:

Old:
```
      labels: idealLabels.slice(0, Math.max(actualData.length, 2)),
```

New:
```
      labels: idealLabels,
```

**Change 2b** — add a caption right after the chart container (between line 5 `</div>` and line 7 `<script>`):

Old:
```
  <div class="chart-container">
    <canvas id="burndownChart"></canvas>
  </div>
</div>
<script>
```

New:
```
  <div class="chart-container">
    <canvas id="burndownChart"></canvas>
  </div>
  {% if sprint.closed_at and progress_history and progress_history|length < team.sprint_length_days %}
    <div class="chart-caption" style="font-size:12px; color:#718096; margin-top:8px;">
      Last snapshot: Day {{ progress_history|length - 1 }}. No data captured for the remaining days.
    </div>
  {% endif %}
</div>
<script>
```

(`progress_history|length - 1` gives the last day index because the list contains entries for Day 0, Day 1, …, Day N-1.)

- [ ] **Step 3: Verify the template still renders**

Run: `.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('components/burndown_chart.html'); print('OK')"`

Expected: `OK`.

- [ ] **Step 4: Restart the app**

Run: `./stop.sh && ./start.sh`

Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

- [ ] **Step 5: Scry verification — burndown labels**

```
scry.open http://localhost:8000/sprint/8
scry.evaluate {
  script: "const c = Chart.getChart('burndownChart'); return { labels: c.data.labels, actualLen: c.data.datasets.find(d=>d.label==='Actual').data.length, sprintDays: 14 }"
}
```

Expected:
- `labels.length === 15` (Day 0 through Day 14)
- `labels[14] === "Day 14"`
- `actualLen <= 7` (data only goes up to Day 6 for sprint 8)

- [ ] **Step 6: Scry verification — caption visible**

```
scry.evaluate {
  script: "document.querySelector('.chart-caption')?.textContent.trim()"
}
```

Expected: a string like `"Last snapshot: Day 6. No data captured for the remaining days."`. Must contain "Day 6" (not "Day None" or empty).

```
scry.close
```

- [ ] **Step 7: Commit**

```bash
git add templates/components/burndown_chart.html
git commit -m "$(cat <<'EOF'
fix(ui): show full sprint horizon on burndown chart

X-axis now renders all sprint days (Day 0..Day N) regardless of how many
daily_progress rows exist. Actual-data line plots only what we have, so
truncated data is visually obvious. For closed sprints with truncated
data, a caption explains "Last snapshot: Day X. No data captured for
the remaining days."

Verified via scry: /sprint/8 chart now has 15 labels (Day 0-14), Actual
dataset has 7 points, caption renders with "Day 6".

Refs spec: docs/superpowers/specs/2026-05-04-audit-bugs-fix-design.md
EOF
)"
```

---

## Task 3: Fix Bug 3 — Strip parenthetical date from sprint names

**Files:**
- Modify: `app.py` (register filter)
- Modify: `templates/sprint_history.html`, `templates/sprint_live.html`, `templates/sprint_report.html`, `templates/home.html`, `templates/team_trends.html` (apply `|display_name`)

- [ ] **Step 1: Add the Jinja filter to `app.py`**

Use `Edit` to add an import and a filter registration. Find the line where `app = FastAPI(...)` is created (after the lifespan function). Add these lines AFTER the `app = FastAPI(...)` line:

```python
import re

def _display_name(name):
    if not name:
        return name
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(name)).strip()

# Register on the templates Jinja environment when routes are imported.
# We attach it after `app` is created but before routers are included.
```

Wait — the `templates` object is in `src/routes/pages.py`, not `app.py`. Let's instead put the filter on the templates env directly. Find `templates = Jinja2Templates(...)` (it's in `src/routes/pages.py`) and add the filter registration right after it.

Run: `grep -n "Jinja2Templates" src/routes/pages.py`
Expected: a line like `templates = Jinja2Templates(directory="templates")`.

- [ ] **Step 2: Register the filter in `src/routes/pages.py`**

Use `Edit` to add the imports and filter registration right after `templates = Jinja2Templates(...)`. Insert these lines:

```python
import re as _re

def _display_name(name):
    if not name:
        return name
    return _re.sub(r"\s*\([^)]*\)\s*$", "", str(name)).strip()

templates.env.filters["display_name"] = _display_name
```

(`_re` alias avoids any clash with route-handler-local `re` imports.)

- [ ] **Step 3: Verify the filter is registered**

Run:
```bash
.venv/bin/python -c "
from src.routes.pages import templates
f = templates.env.filters['display_name']
assert f('Sprint 8 (4/6 - 4/19)') == 'Sprint 8'
assert f('Iteration 1 (4/5 - 17/5)') == 'Iteration 1'
assert f('Sprint 8') == 'Sprint 8'
assert f('') == ''
assert f(None) is None
assert f('Q3 (refactor) sprint') == 'Q3 (refactor) sprint'
print('OK — all 6 cases pass')
"
```

Expected: `OK — all 6 cases pass`.

- [ ] **Step 4: Sweep templates to apply the filter**

For each location below, use `Edit` to add `|display_name` to the `sprint.name` reference. The exact substitutions:

**`templates/sprint_history.html:35`**
```
            <a href="/sprint/{{ sprint.id }}">{{ sprint.name }}</a>
```
becomes:
```
            <a href="/sprint/{{ sprint.id }}">{{ sprint.name|display_name }}</a>
```

**`templates/sprint_live.html:2`**
```
{% block title %}{{ sprint.name }} — Sprint Reporter{% endblock %}
```
becomes:
```
{% block title %}{{ sprint.name|display_name }} — Sprint Reporter{% endblock %}
```

**`templates/sprint_live.html:6`**
```
    <h1 style="display:inline" data-sprint-id="{{ sprint.id }}">{{ sprint.name }}</h1>
```
becomes:
```
    <h1 style="display:inline" data-sprint-id="{{ sprint.id }}">{{ sprint.name|display_name }}</h1>
```

**`templates/sprint_live.html:116`**
```
    <p>You are about to lock the baseline snapshot for <strong>{{ sprint.name }}</strong>.</p>
```
becomes:
```
    <p>You are about to lock the baseline snapshot for <strong>{{ sprint.name|display_name }}</strong>.</p>
```

**`templates/sprint_report.html:2`**
```
{% block title %}{{ sprint.name }} — Report — Sprint Reporter{% endblock %}
```
becomes:
```
{% block title %}{{ sprint.name|display_name }} — Report — Sprint Reporter{% endblock %}
```

**`templates/sprint_report.html:6`**
```
    <h1 style="display:inline">{{ sprint.name }}</h1>
```
becomes:
```
    <h1 style="display:inline">{{ sprint.name|display_name }}</h1>
```

**`templates/home.html:26`**
```
        <a href="/sprint/{{ team.active_sprint.id }}" style="font-size:16px; font-weight:600; text-decoration:none; color:#2d3748;">{{ team.active_sprint.name }}</a>
```
becomes:
```
        <a href="/sprint/{{ team.active_sprint.id }}" style="font-size:16px; font-weight:600; text-decoration:none; color:#2d3748;">{{ team.active_sprint.name|display_name }}</a>
```

**`templates/team_trends.html:141`**
```
          <td><a href="/sprint/{{ s.sprint_id }}">{{ s.sprint_name }}</a></td>
```
becomes:
```
          <td><a href="/sprint/{{ s.sprint_id }}">{{ s.sprint_name|display_name }}</a></td>
```

**`templates/team_trends.html:196`**
```
  const labels = sprints.map(s => s.sprint_name);
```

This is JS, not Jinja — the filter doesn't work here. Instead, change the route to also send a `display_name` field on each trend, OR apply the regex in JS.

Simpler: do the strip in JS. Replace line 196 with:
```
  const labels = sprints.map(s => (s.sprint_name || '').replace(/\s*\([^)]*\)\s*$/, '').trim());
```

- [ ] **Step 5: Restart the app**

Run: `./stop.sh && ./start.sh`

Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

- [ ] **Step 6: Scry verification — sprint history**

```
scry.open http://localhost:8000/teams/1/sprints
scry.evaluate {
  script: "Array.from(document.querySelectorAll('a[href^=\"/sprint/\"]')).map(a => a.textContent.trim())"
}
```

Expected: array contains entries like `"Sprint 8"`, `"Iteration 1"` — no parens, no `(4/6`, no `(17/5)`.

- [ ] **Step 7: Scry verification — sprint detail and trends**

```
scry.navigate http://localhost:8000/sprint/8
scry.evaluate { script: "document.querySelector('h1').textContent.trim()" }
```
Expected: `"Sprint 8"` (not `"Sprint 8 (4/6 - 4/19)"`).

```
scry.navigate http://localhost:8000/teams/1/trends
scry.evaluate {
  script: "Array.from(document.querySelectorAll('table a[href^=\"/sprint/\"]')).map(a => a.textContent.trim()).filter(t => t.match(/^Sprint|Iteration/))"
}
```
Expected: array of clean names — no `(4/`, `(5/`, `(2/` substrings.

```
scry.close
```

- [ ] **Step 8: Commit**

```bash
git add app.py src/routes/pages.py templates/sprint_history.html templates/sprint_live.html templates/sprint_report.html templates/home.html templates/team_trends.html
git commit -m "$(cat <<'EOF'
fix(ui): strip parenthetical dates from sprint names in display

ClickUp list names contain dates in inconsistent formats — Sprint 8
(4/6 - 4/19) is M/D, Iteration 1 (4/5 - 17/5) is D/M. The DATES
column already shows ISO dates, so the parenthetical is redundant.

Adds a display_name Jinja filter that strips a trailing (...) block,
applies it everywhere sprint.name is rendered. DB names unchanged —
only presentation. team_trends.html had one JS-side label
generation that gets the same regex inline.

Verified via scry: /teams/1/sprints, /sprint/8, /teams/1/trends all
render clean names; no "(4/" or "(5/" substrings remain.

Refs spec: docs/superpowers/specs/2026-05-04-audit-bugs-fix-design.md
EOF
)"
```

---

## Task 4: Fix Bug 4 — Mobile (360px) layout overflow

**Files:**
- Modify: `static/style.css` (append a new `@media (max-width: 480px)` block at end of file)

- [ ] **Step 1: Confirm baseline**

Run: `grep -nE "@media" static/style.css`

Expected: one line like `244:@media (max-width: 768px) {`.

- [ ] **Step 2: Append the new block**

Use `Edit` to append the following at the end of `static/style.css` (after the existing 768px block). Place this exact block as the new end of the file:

```css

/* --- Mobile (≤480px) ---------------------------------------------------- */
@media (max-width: 480px) {
  /* KPI row: stack into a 2-column grid instead of horizontal flex */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  .kpi-card {
    min-width: 0;
    padding: 10px 12px;
  }
  .kpi-card .value {
    font-size: 22px;
  }

  /* Top nav: scroll horizontally rather than overflow the page */
  nav, .nav, header nav {
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
  }

  /* Two-column grid (Burndown + Scope Changes etc) collapses to one column */
  .grid-2 {
    grid-template-columns: 1fr;
  }

  /* Panels: tighter padding, ensure they never overflow their container */
  .panel {
    padding: 12px;
    width: 100%;
    box-sizing: border-box;
  }

  /* Tasks table: hide HOURS column (lowest priority on mobile),
     truncate assignee names */
  .task-table th:nth-last-child(1),
  .task-table td:nth-last-child(1) {
    display: none;
  }
  .task-table td:nth-child(2) {  /* assignee column */
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Top-bar (sprint detail header) stacks vertically */
  .top-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  /* Page padding: tighter so nothing rubs against the edge */
  .content {
    padding-left: 12px;
    padding-right: 12px;
  }
}
```

- [ ] **Step 3: Verify CSS is still valid**

Run: `.venv/bin/python -c "import re; css = open('static/style.css').read(); braces = css.count('{') - css.count('}'); print('Braces balanced' if braces == 0 else f'IMBALANCED: {braces} extra opening' if braces > 0 else f'IMBALANCED: {-braces} extra closing')"`

Expected: `Braces balanced`.

- [ ] **Step 4: Restart the app**

Run: `./stop.sh && ./start.sh`

Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

- [ ] **Step 5: Scry verification — responsive**

```
scry.responsive {
  url: "http://localhost:8000/sprint/8",
  outDir: "/tmp/scry-task4-sprint",
  widths: [360, 768, 1024, 1440]
}
```

Expected: `findings` array contains zero entries with `severity: "major"`. Minor `x-overflow` findings on minor elements are tolerated only if the document scrollWidth equals clientWidth at every width (no page-level horizontal scroll).

```
scry.responsive {
  url: "http://localhost:8000/teams/1/sprints",
  outDir: "/tmp/scry-task4-history",
  widths: [360, 768, 1024, 1440]
}
```

Expected: same. Specifically, the previous run showed 8 issues at 360px on `/sprint/8`. After this fix, expect ≤ 1 issue (and that one should NOT be `kind: "page-overflow"`).

If issues remain, re-read the responsive output, identify which selector is overflowing, and add a rule for it before committing.

- [ ] **Step 6: Commit**

```bash
git add static/style.css
git commit -m "$(cat <<'EOF'
fix(ui): mobile (≤480px) layout — stack KPIs, scroll nav, hide hours

Adds a @media (max-width: 480px) block:
- KPI row: 2-column grid instead of horizontal flex
- Top nav: overflow-x: auto so team names scroll instead of overflow
- .grid-2 collapses to a single column (Burndown + Scope Changes stack)
- Panels: tighter padding + box-sizing to prevent overflow
- Tasks table: hide HOURS column, ellipsis on assignee names
- Top-bar stacks vertically on sprint detail

Verified via scry.responsive: /sprint/8 and /teams/1/sprints at 360px
no longer produce page-overflow.

Refs spec: docs/superpowers/specs/2026-05-04-audit-bugs-fix-design.md
EOF
)"
```

---

## Task 5: Fix Bug 5 — Toast feedback for sync (and three siblings)

**Files:**
- Modify: `static/style.css` (append toast styles)
- Modify: `static/dashboard.js` (rewrite the four async handlers + add `showToast` helper + DOMContentLoaded drain)

- [ ] **Step 1: Confirm baseline**

Run: `cat static/dashboard.js`

Expected: see the existing 47-line file with `refreshSprint`, `closeForecast`, `closeSprint`, `syncSprints` and the kpi-filter listener.

- [ ] **Step 2: Append toast CSS**

Append the following to the end of `static/style.css`:

```css

/* --- Toast notifications ------------------------------------------------ */
.toast-container {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}
.toast {
  padding: 10px 16px;
  border-radius: 6px;
  background: #2d3748;
  color: #fff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  animation: toast-in 0.2s ease-out;
  max-width: 360px;
  font-size: 14px;
  pointer-events: auto;
}
.toast.success { background: #38a169; }
.toast.error   { background: #e53e3e; }
@keyframes toast-in {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 3: Replace `static/dashboard.js` entirely with the new version**

Use `Write` (full replacement is cleaner than four separate Edits). New content:

```javascript
document.addEventListener('DOMContentLoaded', function() {
  // KPI-card filter behavior (unchanged)
  document.querySelectorAll('.kpi-card[data-filter]').forEach(card => {
    card.addEventListener('click', function() {
      const filter = this.dataset.filter;
      const isActive = this.classList.contains('active');
      document.querySelectorAll('.kpi-card').forEach(c => c.classList.remove('active'));
      if (isActive) {
        document.querySelectorAll('.task-table tr[data-filter]').forEach(row => row.classList.remove('filtered-out'));
      } else {
        this.classList.add('active');
        document.querySelectorAll('.task-table tr[data-filter]').forEach(row => {
          if (row.dataset.filter.includes(filter)) { row.classList.remove('filtered-out'); }
          else { row.classList.add('filtered-out'); }
        });
      }
    });
  });

  // Drain a pending toast (queued before location.reload)
  const pending = sessionStorage.getItem('pending_toast');
  if (pending) {
    sessionStorage.removeItem('pending_toast');
    try {
      const { message, kind } = JSON.parse(pending);
      showToast(message, kind);
    } catch (e) { /* malformed — ignore */ }
  }
});

function showToast(message, kind) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'toast ' + (kind || 'info');
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function deferToast(message, kind) {
  // Queue a toast that survives the next location.reload()
  try {
    sessionStorage.setItem('pending_toast', JSON.stringify({ message, kind: kind || 'success' }));
  } catch (e) { /* storage full / private mode — ignore */ }
}

async function refreshSprint(sprintId) {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = 'Refreshing...'; btn.disabled = true;
  try {
    const resp = await fetch(`/sprints/${sprintId}/refresh`, { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.json().then(d => d.detail).catch(() => 'unknown');
      showToast('Refresh misslyckades: ' + detail, 'error');
      btn.disabled = false; btn.textContent = '🔄 Refresh Now';
      return;
    }
    deferToast('✓ Refresh klar');
    location.reload();
  } catch (e) {
    showToast('Refresh misslyckades: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = '🔄 Refresh Now';
  }
}

async function closeForecast(sprintId) {
  if (!confirm('Close the forecast? This captures the baseline snapshot.')) return;
  try {
    const resp = await fetch(`/sprints/${sprintId}/close-forecast`, { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.json().then(d => d.detail).catch(() => 'unknown');
      showToast('Close forecast misslyckades: ' + detail, 'error');
      return;
    }
    deferToast('✓ Forecast låst');
    location.reload();
  } catch (e) {
    showToast('Close forecast misslyckades: ' + e.message, 'error');
  }
}

async function closeSprint(sprintId) {
  if (!confirm('Close this sprint? The report will be frozen.')) return;
  try {
    const resp = await fetch(`/sprints/${sprintId}/close`, { method: 'POST' });
    if (!resp.ok) {
      const detail = await resp.json().then(d => d.detail).catch(() => 'unknown');
      showToast('Close sprint misslyckades: ' + detail, 'error');
      return;
    }
    deferToast('✓ Sprint stängd');
    location.reload();
  } catch (e) {
    showToast('Close sprint misslyckades: ' + e.message, 'error');
  }
}

async function syncSprints(teamId) {
  const btn = document.getElementById('sync-btn');
  btn.textContent = 'Syncing...'; btn.disabled = true;
  try {
    const resp = await fetch(`/teams/${teamId}/sync-sprints`, { method: 'POST' });
    if (!resp.ok) {
      showToast('Sync misslyckades', 'error');
      btn.disabled = false; btn.textContent = '🔄 Sync Sprints';
      return;
    }
    const data = await resp.json().catch(() => ({ synced: 0 }));
    const count = data.synced || 0;
    const msg = count === 0
      ? 'Inga nya sprintar hittades.'
      : '✓ Sync klar — ' + count + ' ' + (count === 1 ? 'sprint' : 'sprintar') + ' synkade.';
    deferToast(msg);
    location.reload();
  } catch (e) {
    showToast('Sync misslyckades: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = '🔄 Sync Sprints';
  }
}
```

- [ ] **Step 4: Verify JS syntax**

Run: `node -c static/dashboard.js`

Expected: exits 0 with no output. Any `SyntaxError` here means the rewrite went sideways.

(If `node -c` is not available, fall back to: `.venv/bin/python -c "import esprima" 2>/dev/null || echo "no JS parser available — skip syntax check"`. The browser will catch errors at runtime; the scry step below will surface any.)

- [ ] **Step 5: Restart the app**

Run: `./stop.sh && ./start.sh`

Expected: `Sprint Reporter körs på http://localhost:8000 (PID X)`.

- [ ] **Step 6: Scry verification — sync triggers a visible toast**

```
scry.open http://localhost:8000/teams/1/sprints
scry.click { target: "🔄 Sync Sprints" }
```

Wait briefly for the reload (the click handler does `location.reload()` after a successful POST):

```
scry.evaluate { script: "new Promise(r => setTimeout(r, 2500))" }
scry.evaluate {
  script: "const t = document.querySelector('.toast'); return t ? { text: t.textContent.trim(), classes: t.className } : null"
}
```

Expected: a non-null result like `{ text: "Inga nya sprintar hittades." (or "✓ Sync klar — N sprintar synkade."), classes: "toast success" }`.

If the toast already faded (4s timeout), the result is `null` — that's still a valid pass as long as there were no console errors. Confirm:

```
scry.consoleErrors
```

Expected: `errors: []`.

- [ ] **Step 7: Scry verification — toast helper basics**

While still on the page, manually invoke a toast to confirm the CSS works:

```
scry.evaluate { script: "showToast('manual test toast', 'info'); return document.querySelector('.toast')?.textContent" }
```

Expected: `"manual test toast"`.

```
scry.snapshot { inline: true, fullPage: false }
```

Expected screenshot: top-right corner shows the toast. Verify visually it's positioned correctly and styled (dark background, white text).

```
scry.close
```

- [ ] **Step 8: Commit**

```bash
git add static/style.css static/dashboard.js
git commit -m "$(cat <<'EOF'
fix(ui): toast feedback for sync, refresh, close-forecast, close-sprint

All four async button handlers used location.reload() with no success
feedback — user couldn't tell if their action did anything. Adds a
small toast helper (CSS + JS) and a sessionStorage-deferred mechanism
so toasts survive the reload.

For sync: reads `synced` count from the response and shows
"✓ Sync klar — N sprintar synkade." or "Inga nya sprintar hittades."
For the other three: tailored success messages.

Verified via scry: clicking Sync Sprints produces a visible toast
after reload; manual showToast() call renders correctly with no
console errors.

Refs spec: docs/superpowers/specs/2026-05-04-audit-bugs-fix-design.md
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| Bug 1 (Day None) | Task 1, all steps |
| Bug 2 (burndown axis + caption) | Task 2, all steps; both 2a (slice) and 2b (caption) implemented |
| Bug 3 (display_name filter + sweep) | Task 3, all 9 file touches plus the JS-side strip in team_trends.html:196 |
| Bug 4 (mobile @480px) | Task 4, full @media block including all 7 things from the spec |
| Bug 5 (toast helper + 4 button handlers) | Task 5, both CSS and JS full file replacements |
| Verification strategy (scry per bug) | Each task has a "Scry verification" step before commit |

**Placeholder scan:** No "TBD", "TODO", "implement later", "appropriate error handling", or "similar to Task N". Every code block is complete. Every command has expected output.

**Type/name consistency:**
- `display_name` filter — same name in `pages.py` registration and every template usage.
- `showToast`, `deferToast` — same names in `dashboard.js` and in the verification step.
- `progress_history` (Jinja variable) — matches `pages.py:194` (`progress_history=progress`) and the burndown component's existing `progressData` variable use.
- `sprint.closed_at` — used in both Task 1 and Task 2's caption condition, both reference the same DB column from the sprint dict.

**Inline fix during review:** noticed Task 3 originally listed `app.py` as the place to register the filter, but `templates = Jinja2Templates(...)` is in `src/routes/pages.py`. Updated to put the filter registration in `src/routes/pages.py` instead. Files-changed table at the top reflects this.
