# Polish Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three small UI rough edges from the audit: KPI cards stack at laptop widths, Delete Team moves to a "Danger zone" section, scope-changes KPI gets an explanatory tooltip.

**Architecture:** All three are small, isolated edits — one CSS append, one template restructure, one HTML attribute. No backend, no DB, no JS logic.

**Tech Stack:** Plain CSS, Jinja2 templates.

**Spec:** `docs/superpowers/specs/2026-05-04-polish-fix-design.md`

> **Verification note:** scry runs in the controller's MCP context. Implementer subagents commit code; the controller runs scry verification after each task's commit.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `static/style.css` | Append (Task 1 + Task 2) | New `@media (max-width: 1280px) and (min-width: 481px)` block for KPI grid, plus `.danger-zone` styles |
| `templates/team_settings.html` | Modify (Task 2) | Move Delete Team out of form-actions into a separate `.danger-zone` block |
| `templates/components/kpi_cards.html` | Modify (Task 3) | Add `title` attribute to scope-changes card |

---

## Task 1: KPI cards stack to 3×2 grid at ≤1280px

**Files:**
- Modify: `static/style.css` (append a new media block at end of file)

### Step 1: Confirm baseline

Run: `grep -nE "@media" static/style.css`

Expected: at least 2 existing matches — the 768px block (line ~244) and the 480px block (line ~670). No `1280` match yet.

### Step 2: Append the new media block

Append this exact block to the end of `static/style.css`:

```css

/* --- Tablet / narrow desktop (481-1280px): stack KPI cards ------------- */
@media (max-width: 1280px) and (min-width: 481px) {
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
}
```

### Step 3: Verify CSS balances

Run:
```bash
.venv/bin/python -c "css = open('static/style.css').read(); print('balanced' if css.count('{') == css.count('}') else 'IMBALANCED')"
```
Expected: `balanced`. Else STOP.

### Step 4: Verify the new query is present

Run: `grep -nE "1280" static/style.css`
Expected: at least one match in a `@media (max-width: 1280px) and (min-width: 481px)` line.

### Step 5: Restart

Run: `./stop.sh && ./start.sh`
Expected: app starts.

### Step 6: Commit

```bash
git add static/style.css
git commit -m "$(cat <<'EOF'
fix(ui): KPI row stacks to 3-column grid at 481-1280px

Six KPI cards trapped on closed sprint detail at laptop widths
(~1024px) — the last "Behind" status card got clipped. Adds a
mid-range media query that converts the flex row into a 3-column
grid for any non-mobile viewport up to 1280px. Above 1280px keeps
the existing one-row flex layout.

Refs spec: docs/superpowers/specs/2026-05-04-polish-fix-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Task 2: Delete Team danger zone

**Files:**
- Modify: `templates/team_settings.html` (lines 93-107: move Delete out of `.form-actions`)
- Modify: `static/style.css` (append `.danger-zone` styles)

### Step 1: Restructure form-actions in `team_settings.html`

Use `Edit`:

old_string:
```
      <div class="form-actions">
        <button type="submit" class="btn btn-primary" id="save-btn">
          {% if team %}Save Changes{% else %}Create Team{% endif %}
        </button>
        {% if team %}
        <a href="/teams/{{ team.id }}/sprints" class="btn btn-secondary">Cancel</a>
        {% else %}
        <a href="/" class="btn btn-secondary">Cancel</a>
        {% endif %}
        {% if team %}
        <button type="button" class="btn btn-danger" id="delete-btn" style="margin-left:auto;"
                onclick="deleteTeam({{ team.id }})">Delete Team</button>
        {% endif %}
      </div>
    </form>
```

new_string:
```
      <div class="form-actions">
        <button type="submit" class="btn btn-primary" id="save-btn">
          {% if team %}Save Changes{% else %}Create Team{% endif %}
        </button>
        {% if team %}
        <a href="/teams/{{ team.id }}/sprints" class="btn btn-secondary">Cancel</a>
        {% else %}
        <a href="/" class="btn btn-secondary">Cancel</a>
        {% endif %}
      </div>
    </form>

    {% if team %}
    <div class="danger-zone">
      <h4>Danger zone</h4>
      <p>Deleting this team removes all sprint history, snapshots, and scope changes. This cannot be undone.</p>
      <button type="button" class="btn btn-danger" id="delete-btn" onclick="deleteTeam({{ team.id }})">Delete Team</button>
    </div>
    {% endif %}
```

### Step 2: Append `.danger-zone` CSS to `static/style.css`

Append this exact block to the end of the file:

```css

/* --- Danger zone (Settings) ------------------------------------------- */
.danger-zone {
  margin-top: 32px;
  padding: 20px;
  border-top: 1px solid #fed7d7;
  background: #fff5f5;
}
.danger-zone h4 {
  margin: 0 0 8px 0;
  color: #c53030;
  font-size: 15px;
}
.danger-zone p {
  margin: 0 0 12px 0;
  color: #4a5568;
  font-size: 13px;
  line-height: 1.5;
}
```

### Step 3: Verify CSS balances

Run:
```bash
.venv/bin/python -c "css = open('static/style.css').read(); print('balanced' if css.count('{') == css.count('}') else 'IMBALANCED')"
```
Expected: `balanced`. Else STOP.

### Step 4: Verify template parses

Run:
```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('team_settings.html'); print('OK')"
```
Expected: `OK`. Else STOP.

### Step 5: Verify Delete button moved out of form-actions

Run:
```bash
awk '/<div class="form-actions">/,/<\/div>/' templates/team_settings.html | grep -c "Delete Team"
```
Expected: `0`. The Delete Team button must no longer be inside `.form-actions`.

Then:
```bash
grep -c "danger-zone" templates/team_settings.html
```
Expected: `1`.

### Step 6: Restart

Run: `./stop.sh && ./start.sh`

### Step 7: Commit

```bash
git add templates/team_settings.html static/style.css
git commit -m "$(cat <<'EOF'
fix(ui): Delete Team moves to a separate Danger zone section

Delete Team was right next to Save Changes in the same form-actions
row — one mis-click away from data loss. Now lives in a visually
distinct "Danger zone" block at the bottom of Settings, with explainer
text and a red-tinted background. The existing confirm() prompt in
deleteTeam() stays — defense in depth.

Refs spec: docs/superpowers/specs/2026-05-04-polish-fix-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Task 3: Scope Changes KPI tooltip

**Files:**
- Modify: `templates/components/kpi_cards.html:12-16` (the scope-changes card)

### Step 1: Locate the scope-changes card

Run: `grep -nA 4 'data-filter="scope_changes"' templates/components/kpi_cards.html`

Expected: 5-line block around line 12 with the value, label, and sub div.

### Step 2: Add `title` attribute

Use `Edit`:

old_string:
```
  <div class="kpi-card" data-filter="scope_changes">
    <div class="value red">+{{ summary.scope_added|default(0) }} / -{{ summary.scope_removed|default(0) }}</div>
    <div class="label">Scope Changes</div>
    <div class="sub">added / removed</div>
  </div>
```

new_string:
```
  <div class="kpi-card" data-filter="scope_changes"
       title="Tasks added (+) or removed (−) after the forecast was locked. Counts are independent — added tasks may include items completed before the sprint ended.">
    <div class="value red">+{{ summary.scope_added|default(0) }} / -{{ summary.scope_removed|default(0) }}</div>
    <div class="label">Scope Changes</div>
    <div class="sub">added / removed</div>
  </div>
```

### Step 3: Verify template parses

Run:
```bash
.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); env.get_template('components/kpi_cards.html'); print('OK')"
```
Expected: `OK`.

### Step 4: Restart

Run: `./stop.sh && ./start.sh`

### Step 5: Commit

```bash
git add templates/components/kpi_cards.html
git commit -m "$(cat <<'EOF'
fix(ui): tooltip on Scope Changes KPI explains what counts

The +N / -M number on the scope-changes card told you the count but
not what defines a "scope change". Adds a native browser title
attribute that explains: tasks added or removed after the forecast
was locked, counts independent.

Refs spec: docs/superpowers/specs/2026-05-04-polish-fix-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

---

## Self-Review

**Spec coverage:**

| Spec item | Plan task |
|---|---|
| Item 20 — KPI cards stack at ≤1280px | Task 1 |
| Item 21 — Delete Team danger zone | Task 2 (template restructure + CSS) |
| Item 23 — Scope Changes tooltip | Task 3 |
| Item 22 (Sprint/Iteration naming) | Out of scope per spec — explicitly skipped |

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "appropriate error handling". All commands and code blocks concrete.

**Type/name consistency:** `.danger-zone` (CSS class) consistent in Task 2 template and CSS. `.kpi-card[data-filter="scope_changes"]` selector consistent across task and verification.

---

## Scry verification (controller-side, between tasks)

| Task | Scry checks |
|---|---|
| 1 | `scry.responsive` on `/sprint/8` widths=[1024, 1280, 1440] → `findings[]` contains zero `severity:"major"` entries; visually a 3-column grid at 1024 and 1280, single row at 1440. |
| 2 | `scry.evaluate` on `/teams/1/settings` → `document.querySelector('.danger-zone') !== null`; AND `.form-actions` does NOT contain Delete (`Array.from(document.querySelectorAll('.form-actions .btn-danger')).length === 0`). |
| 3 | `scry.evaluate` on `/sprint/8` → `.kpi-card[data-filter="scope_changes"]` has `title` attribute; the title contains the words `added` AND `removed`. |
