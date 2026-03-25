# Retro Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add final snapshots, unfinished task highlighting, carry-over detection, workload distribution, and scope timeline detail to sprint reports.

**Architecture:** Extends the existing snapshot pattern with a new `sprint_final_snapshots` table. Closed sprint reports gain new sections built from comparing baseline vs final data. All features are metric-type aware (hours/points/task_count).

**Tech Stack:** Python/FastAPI, SQLite, Jinja2 templates, Chart.js

**Spec:** `docs/superpowers/specs/2026-03-25-retro-insights-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/database.py` | Modify | Add new table + migration columns |
| `src/services/snapshot_service.py` | Modify | Add `save_final_snapshot()`, `get_final_snapshot()`, update `save_forecast_snapshot()` to include `assignee_hours` |
| `src/routes/sprints.py` | Modify | Call `save_final_snapshot()` in `close_sprint_route()`, add carry-over detection in `close_forecast_route()` |
| `app.py` | Modify | Call `save_final_snapshot()` in auto-close block |
| `src/routes/pages.py` | Modify | Pass final snapshot + unfinished/carry-over data to closed sprint template |
| `src/services/trend_service.py` | Modify | Add `get_workload_distribution()`, update `get_sprint_summary()` with unfinished count |
| `templates/sprint_report.html` | Modify | Add unfinished section, workload table |
| `templates/components/kpi_cards.html` | Modify | Add unfinished KPI card |
| `templates/components/task_table.html` | Modify | Carry-over badge, unfinished ordering |
| `templates/components/scope_timeline.html` | Modify | Sprint-day based timeline |
| `templates/components/workload_table.html` | Create | Per-assignee retro breakdown |

---

### Task 1: Database Migration — Final Snapshots Table + New Columns

**Files:**
- Modify: `src/database.py:10-98`

- [ ] **Step 1: Add `sprint_final_snapshots` table to `init_db()`**

In `src/database.py`, add inside the `executescript()` block (after the `scope_changes` table, before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS sprint_final_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    task_status TEXT NOT NULL,
    assignee_name TEXT,
    assignee_hours TEXT,
    points REAL,
    hours REAL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_final_snap_sprint ON sprint_final_snapshots(sprint_id);
```

- [ ] **Step 2: Add migration columns via try/except**

After the existing `capacity_mode` migration (line 92-95), add:

```python
try:
    conn.execute("ALTER TABLE sprint_snapshots ADD COLUMN assignee_hours TEXT")
except Exception:
    pass

try:
    conn.execute("ALTER TABLE sprint_snapshots ADD COLUMN carried_over BOOLEAN DEFAULT 0")
except Exception:
    pass

try:
    conn.execute("ALTER TABLE scope_changes ADD COLUMN sprint_day INTEGER")
except Exception:
    pass
```

- [ ] **Step 3: Add sprint_day backfill for existing scope changes**

After the ALTER TABLE statements, add:

```python
conn.execute("""
    UPDATE scope_changes SET sprint_day = CAST(
        julianday(detected_at) - julianday((SELECT start_date FROM sprints WHERE id = scope_changes.sprint_id)) + 1
    AS INTEGER)
    WHERE sprint_day IS NULL AND EXISTS (SELECT 1 FROM sprints WHERE id = scope_changes.sprint_id AND start_date IS NOT NULL)
""")
```

- [ ] **Step 4: Verify migration runs cleanly**

Run: `source .venv/bin/activate && python3 -c "from src.database import init_db; init_db('./sprint_data.db'); print('OK')"`

Expected: `OK` with no errors.

- [ ] **Step 5: Verify new table and columns exist**

Run: `sqlite3 sprint_data.db ".schema sprint_final_snapshots" && sqlite3 sprint_data.db "PRAGMA table_info(sprint_snapshots)" && sqlite3 sprint_data.db "PRAGMA table_info(scope_changes)"`

Expected: Table schema shown, `assignee_hours` and `carried_over` columns in sprint_snapshots, `sprint_day` column in scope_changes.

- [ ] **Step 6: Commit**

```bash
git add src/database.py
git commit -m "feat: add sprint_final_snapshots table and migration columns"
```

---

### Task 2: Final Snapshot Service Functions

**Files:**
- Modify: `src/services/snapshot_service.py:8-16`

- [ ] **Step 1: Update `save_forecast_snapshot()` to include `assignee_hours`**

Replace the existing function (lines 8-16) with:

```python
def save_forecast_snapshot(sprint_id: int, tasks: list[dict]):
    import json
    conn = get_connection(_db())
    for t in tasks:
        ah = t.get("assignee_hours")
        conn.execute(
            "INSERT INTO sprint_snapshots (sprint_id, task_id, task_name, task_status, assignee_name, points, hours, assignee_hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sprint_id, t["task_id"], t["task_name"], t["task_status"], t.get("assignee_name"), t.get("points"), t.get("hours"), json.dumps(ah) if ah else None),
        )
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Add `save_final_snapshot()` function**

Add after `get_forecast_snapshot()` (after line 22):

```python
def save_final_snapshot(sprint_id: int, tasks: list[dict]):
    import json
    conn = get_connection(_db())
    for t in tasks:
        ah = t.get("assignee_hours")
        conn.execute(
            "INSERT INTO sprint_final_snapshots (sprint_id, task_id, task_name, task_status, assignee_name, assignee_hours, points, hours) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sprint_id, t["task_id"], t["task_name"], t["task_status"], t.get("assignee_name"), json.dumps(ah) if ah else None, t.get("points"), t.get("hours")),
        )
    conn.commit()
    conn.close()

def get_final_snapshot(sprint_id: int) -> list[dict]:
    import json
    conn = get_connection(_db())
    rows = conn.execute("SELECT * FROM sprint_final_snapshots WHERE sprint_id = ?", (sprint_id,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("assignee_hours"):
            d["assignee_hours"] = json.loads(d["assignee_hours"])
        else:
            d["assignee_hours"] = []
        result.append(d)
    return result
```

- [ ] **Step 3: Verify functions exist**

Run: `source .venv/bin/activate && python3 -c "from src.services.snapshot_service import save_final_snapshot, get_final_snapshot; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/services/snapshot_service.py
git commit -m "feat: add save_final_snapshot and get_final_snapshot functions"
```

---

### Task 3: Capture Final Snapshot on Sprint Close

**Files:**
- Modify: `src/routes/sprints.py:54-68` (close_sprint_route)
- Modify: `app.py:43-53` (auto-close block)

- [ ] **Step 1: Update `close_sprint_route()` to save final snapshot**

In `src/routes/sprints.py`, add import at line 3:

```python
from src.services.snapshot_service import save_forecast_snapshot, record_daily_progress, detect_scope_changes, get_scope_changes, get_forecast_snapshot, get_daily_progress_history, save_final_snapshot
```

Replace lines 54-68 with:

```python
@router.post("/{sprint_id}/close")
async def close_sprint_route(sprint_id: int):
    await refresh_route(sprint_id)
    sprint = get_sprint(sprint_id)
    client, raw_tasks = await _fetch_tasks(sprint)
    tasks = [client.extract_task_data(t) for t in raw_tasks]
    # Save final snapshot with current task states
    save_final_snapshot(sprint_id, tasks)
    # Capture any new scope additions to baseline
    snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint_id)}
    added_tasks = [t for t in tasks if t["task_id"] not in snapshot_ids]
    if added_tasks:
        save_forecast_snapshot(sprint_id, added_tasks)
    try:
        updated = do_close_sprint(sprint_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return updated
```

- [ ] **Step 2: Update auto-close in `app.py` to save final snapshot**

In `app.py`, update the import at line 21 to include `save_final_snapshot`:

```python
from src.services.snapshot_service import save_forecast_snapshot, get_forecast_snapshot, save_final_snapshot
```

In the auto-close block (after line 48, before `do_close_sprint`), add:

```python
                save_final_snapshot(sprint["id"], tasks)
```

So the block becomes:
```python
            if date.today() > end:
                save_final_snapshot(sprint["id"], tasks)
                snapshot_ids = {t["task_id"] for t in get_forecast_snapshot(sprint["id"])}
                ...
```

- [ ] **Step 3: Verify no import errors**

Run: `source .venv/bin/activate && python3 -c "from src.routes.sprints import router; print('OK')" && python3 -c "from app import app; print('OK')"`

Expected: `OK` twice.

- [ ] **Step 4: Commit**

```bash
git add src/routes/sprints.py app.py
git commit -m "feat: capture final snapshot on sprint close (manual and auto)"
```

---

### Task 4: Update `detect_scope_changes()` with `sprint_day`

**Files:**
- Modify: `src/services/snapshot_service.py:51-92`

- [ ] **Step 1: Update `detect_scope_changes()` signature and logic**

The function needs a `sprint_start_date` parameter to calculate sprint_day. Update the function:

```python
def detect_scope_changes(sprint_id: int, current_tasks: list[dict], sprint_start_date=None) -> list[dict]:
    from datetime import date as date_type
    snapshot = get_forecast_snapshot(sprint_id)
    existing_changes = get_scope_changes(sprint_id)

    snapshot_ids = {t["task_id"] for t in snapshot}
    current_ids = {t["task_id"] for t in current_tasks}
    current_by_id = {t["task_id"]: t for t in current_tasks}

    already_added = set()
    already_removed = set()
    for ch in existing_changes:
        if ch["change_type"] == "added":
            already_added.add(ch["task_id"])
            already_removed.discard(ch["task_id"])
        else:
            already_removed.add(ch["task_id"])
            already_added.discard(ch["task_id"])

    # Calculate sprint_day
    sprint_day = None
    if sprint_start_date:
        if isinstance(sprint_start_date, str):
            sprint_start_date = date_type.fromisoformat(sprint_start_date)
        sprint_day = (date_type.today() - sprint_start_date).days + 1

    new_changes = []
    conn = get_connection(_db())

    for tid in current_ids - snapshot_ids:
        if tid not in already_added:
            task = current_by_id[tid]
            conn.execute(
                "INSERT INTO scope_changes (sprint_id, task_id, task_name, change_type, assignee_name, sprint_day) VALUES (?, ?, ?, 'added', ?, ?)",
                (sprint_id, tid, task["task_name"], task.get("assignee_name"), sprint_day),
            )
            new_changes.append({"task_id": tid, "task_name": task["task_name"], "change_type": "added"})

    for tid in snapshot_ids - current_ids:
        if tid not in already_removed:
            snapshot_task = next(t for t in snapshot if t["task_id"] == tid)
            conn.execute(
                "INSERT INTO scope_changes (sprint_id, task_id, task_name, change_type, assignee_name, sprint_day) VALUES (?, ?, ?, 'removed', ?, ?)",
                (sprint_id, tid, snapshot_task["task_name"], snapshot_task.get("assignee_name"), sprint_day),
            )
            new_changes.append({"task_id": tid, "task_name": snapshot_task["task_name"], "change_type": "removed"})

    conn.commit()
    conn.close()
    return new_changes
```

- [ ] **Step 2: Update all callers to pass `sprint_start_date`**

In `src/routes/pages.py:99`, change:
```python
detect_scope_changes(sprint_id, tasks)
```
to:
```python
detect_scope_changes(sprint_id, tasks, sprint_start_date=sprint.get("start_date"))
```

In `app.py:35`, change:
```python
detect_scope_changes(sprint["id"], tasks)
```
to:
```python
detect_scope_changes(sprint["id"], tasks, sprint_start_date=sprint.get("start_date"))
```

In `src/routes/sprints.py:81`, change:
```python
new_changes = detect_scope_changes(sprint_id, tasks)
```
to:
```python
new_changes = detect_scope_changes(sprint_id, tasks, sprint_start_date=sprint.get("start_date"))
```

- [ ] **Step 3: Verify no errors on app startup**

Run: `curl -s http://localhost:8000/health`

Expected: `{"status":"ok"}`

- [ ] **Step 4: Commit**

```bash
git add src/services/snapshot_service.py src/routes/pages.py app.py src/routes/sprints.py
git commit -m "feat: record sprint_day on scope changes"
```

---

### Task 5: Unfinished Tasks in Closed Sprint Report

**Files:**
- Modify: `src/routes/pages.py:109-127` (closed sprint task reconstruction)
- Modify: `src/services/trend_service.py:19-45` (add unfinished count to summary)
- Modify: `templates/sprint_report.html`
- Modify: `templates/components/kpi_cards.html`

- [ ] **Step 1: Update `get_sprint_summary()` to include unfinished count**

In `src/services/trend_service.py`, add import at top:

```python
from src.services.snapshot_service import get_forecast_snapshot, get_daily_progress_history, get_scope_changes, get_final_snapshot
```

In `get_sprint_summary()`, after `removed = ...` (line 32), add:

```python
    # Count unfinished from final snapshot (baseline tasks not completed)
    final = get_final_snapshot(sprint_id)
    if final:
        baseline_ids = {t["task_id"] for t in snapshot}
        final_by_id = {t["task_id"]: t for t in final}
        unfinished = sum(1 for tid in baseline_ids if tid in final_by_id and final_by_id[tid]["task_status"] not in ("complete", "closed"))
    else:
        unfinished = 0
```

Add `"unfinished": unfinished,` to the return dict.

- [ ] **Step 2: Update closed sprint page route to use final snapshot**

In `src/routes/pages.py`, add import:
```python
from src.services.snapshot_service import get_scope_changes, get_daily_progress_history, get_forecast_snapshot, get_final_snapshot
```

Replace the closed sprint block (lines 109-126) with:

```python
        # For closed sprints, use final snapshot for accurate status
        snapshot = get_forecast_snapshot(sprint_id)
        final = get_final_snapshot(sprint_id)
        changes = get_scope_changes(sprint_id)
        added_ids = {c["task_id"] for c in changes if c["change_type"] == "added"}
        removed_ids = {c["task_id"] for c in changes if c["change_type"] == "removed"}
        final_by_id = {t["task_id"]: t for t in final}
        baseline_ids = {t["task_id"] for t in snapshot if t["task_id"] not in added_ids}

        tasks = []
        # Unfinished baseline tasks first
        for t in snapshot:
            if t["task_id"] in added_ids:
                continue  # scope additions handled below
            if t["task_id"] in removed_ids:
                t["scope_change"] = "removed"
            elif final_by_id.get(t["task_id"], {}).get("task_status") not in ("complete", "closed"):
                t["scope_change"] = "unfinished"
                # Update status from final snapshot
                if t["task_id"] in final_by_id:
                    t["task_status"] = final_by_id[t["task_id"]]["task_status"]
            else:
                t["scope_change"] = None
                if t["task_id"] in final_by_id:
                    t["task_status"] = final_by_id[t["task_id"]]["task_status"]
            tasks.append(t)

        # Sort: unfinished first, then completed, then removed
        order = {"unfinished": 0, None: 1, "removed": 2}
        tasks.sort(key=lambda t: order.get(t.get("scope_change"), 1))

        # Scope additions at the end
        for c in changes:
            if c["change_type"] == "added":
                final_status = final_by_id.get(c["task_id"], {}).get("task_status", c.get("task_status", "unknown"))
                tasks.append({
                    **c,
                    "scope_change": "added",
                    "task_status": final_status,
                    "points": None,
                    "hours": None,
                })
```

- [ ] **Step 3: Add unfinished KPI card**

In `templates/components/kpi_cards.html`, after the scope changes card (after line 16), add:

```html
  {% if summary.unfinished is defined and summary.unfinished > 0 %}
  <div class="kpi-card" data-filter="unfinished">
    <div class="value orange">{{ summary.unfinished }}</div>
    <div class="label">Unfinished</div>
    <div class="sub">from forecast</div>
  </div>
  {% endif %}
```

- [ ] **Step 4: Add unfinished styling to task table**

In `templates/components/task_table.html`, update line 16 to handle the "unfinished" filter:

Change:
```
data-filter="{% if task.task_status in ['complete','closed'] %}completed forecasted{% elif task.scope_change == 'added' %}scope_changes{% elif task.scope_change == 'removed' %}scope_changes{% else %}not_completed forecasted{% endif %}"
```
to:
```
data-filter="{% if task.scope_change == 'unfinished' %}unfinished not_completed forecasted{% elif task.task_status in ['complete','closed'] %}completed forecasted{% elif task.scope_change == 'added' %}scope_changes{% elif task.scope_change == 'removed' %}scope_changes{% else %}not_completed forecasted{% endif %}"
```

Update line 21 to add unfinished class:
Change:
```
class="task-row {% if task.scope_change == 'added' %}scope-added{% elif task.scope_change == 'removed' %}scope-removed{% endif %}"
```
to:
```
class="task-row {% if task.scope_change == 'unfinished' %}scope-unfinished{% elif task.scope_change == 'added' %}scope-added{% elif task.scope_change == 'removed' %}scope-removed{% endif %}"
```

Update line 22 (emoji column) to add unfinished icon:
Change:
```
{% if task.task_status in ['complete','closed'] %}✅{% elif task.scope_change == 'added' %}➕{% elif task.scope_change == 'removed' %}➖{% elif task.task_status == 'in progress' %}🔵{% else %}⬜{% endif %}
```
to:
```
{% if task.scope_change == 'unfinished' %}🟠{% elif task.task_status in ['complete','closed'] %}✅{% elif task.scope_change == 'added' %}➕{% elif task.scope_change == 'removed' %}➖{% elif task.task_status == 'in progress' %}🔵{% else %}⬜{% endif %}
```

- [ ] **Step 5: Add CSS for unfinished styling**

In `templates/base.html`, add to the existing styles:

```css
.scope-unfinished { background: #fffaf0; border-left: 3px solid #ed8936; }
```

- [ ] **Step 6: Test by visiting a closed sprint**

Navigate to `http://localhost:8000/sprint/6` and verify:
- Unfinished tasks appear at the top with orange indicator
- Completed tasks below
- KPI card shows unfinished count (if any)

Note: Sprint 6 was closed before final snapshot was implemented, so it won't have final data. The unfinished section will only appear for sprints closed after this change.

- [ ] **Step 7: Commit**

```bash
git add src/routes/pages.py src/services/trend_service.py templates/sprint_report.html templates/components/kpi_cards.html templates/components/task_table.html templates/base.html
git commit -m "feat: show unfinished tasks prominently in closed sprint report"
```

---

### Task 6: Carry-Over Detection

**Files:**
- Modify: `src/routes/sprints.py:35-52` (close_forecast_route)
- Modify: `templates/components/task_table.html`

- [ ] **Step 1: Add carry-over detection to `close_forecast_route()`**

In `src/routes/sprints.py`, after `save_forecast_snapshot(sprint_id, tasks)` (line 44), add:

```python
    # Detect carry-overs from previous sprint
    from src.services.sprint_service import get_team_sprints
    team_sprints = get_team_sprints(sprint["team_id"])
    prev_closed = None
    for s in team_sprints:
        if s["id"] != sprint_id and s.get("closed_at"):
            if prev_closed is None or (s.get("start_date") or "") > (prev_closed.get("start_date") or ""):
                prev_closed = s
    if prev_closed:
        from src.services.snapshot_service import get_final_snapshot
        prev_final = get_final_snapshot(prev_closed["id"])
        if prev_final:
            unfinished_ids = {t["task_id"] for t in prev_final if t["task_status"] not in ("complete", "closed")}
            current_ids = {t["task_id"] for t in tasks}
            carried = unfinished_ids & current_ids
            if carried:
                from src.database import get_connection
                from src.services.snapshot_service import _db
                conn = get_connection(_db())
                for tid in carried:
                    conn.execute("UPDATE sprint_snapshots SET carried_over = 1 WHERE sprint_id = ? AND task_id = ?", (sprint_id, tid))
                conn.commit()
                conn.close()
```

- [ ] **Step 2: Pass carry-over data to template**

In `src/routes/pages.py`, in the closed sprint block, after building the tasks list, add carry-over info. Update the forecast snapshot query to include `carried_over`:

The `get_forecast_snapshot()` already returns all columns including `carried_over` (via `SELECT *`), so no service change needed. The template just needs to check `task.carried_over`.

- [ ] **Step 3: Add carry-over badge to task table**

In `templates/components/task_table.html`, on line 23 (task name cell), change:

```html
<td>{{ task.task_name }}{% if task.scope_change == 'added' %}<span class="scope-badge">(added)</span>{% endif %}</td>
```
to:
```html
<td>{{ task.task_name }}{% if task.scope_change == 'added' %}<span class="scope-badge">(added)</span>{% endif %}{% if task.carried_over %}<span class="scope-badge" style="background:#ebf4ff; color:#3182ce;">↩ carried over</span>{% endif %}</td>
```

- [ ] **Step 4: Verify no errors**

Run: `curl -s http://localhost:8000/health`

Expected: `{"status":"ok"}`

- [ ] **Step 5: Commit**

```bash
git add src/routes/sprints.py src/routes/pages.py templates/components/task_table.html
git commit -m "feat: detect and display carry-over tasks from previous sprint"
```

---

### Task 7: Workload Distribution Table

**Files:**
- Create: `templates/components/workload_table.html`
- Modify: `src/routes/pages.py`
- Modify: `templates/sprint_report.html`

- [ ] **Step 1: Create workload table component**

Create `templates/components/workload_table.html`:

```html
{% if final_snapshot %}
<div class="panel">
  <h3>Workload Distribution</h3>
  <table class="task-table">
    <thead>
      <tr>
        <th>Assignee</th>
        <th>Stories</th>
        <th>Completed</th>
        <th>Completion %</th>
        {% if team.metric_type == 'hours' %}<th>Hours</th>{% endif %}
        {% if team.metric_type == 'points' %}<th>Points</th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for w in workload %}
      <tr>
        <td>
          {% if team_members is defined and team_members and w.name not in team_members %}<span style="color:#e53e3e;" title="External">⊘</span> {% endif %}{{ w.name }}
          {% if w.overloaded %}<span style="color:#e53e3e; font-size:11px;">(overloaded)</span>{% endif %}
        </td>
        <td>{{ w.assigned }}</td>
        <td>{{ w.completed }}</td>
        <td>
          <span class="{% if w.pct >= 90 %}green{% elif w.pct < 60 %}red{% else %}orange{% endif %}">
            {{ w.pct }}%
          </span>
        </td>
        {% if team.metric_type == 'hours' %}<td>{{ w.metric_value }}h</td>{% endif %}
        {% if team.metric_type == 'points' %}<td>{{ w.metric_value }}pts</td>{% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}
```

- [ ] **Step 2: Add `get_workload_distribution()` to trend_service**

In `src/services/trend_service.py`, add:

```python
def get_workload_distribution(sprint_id: int, metric_type: str = "task_count") -> list[dict]:
    import json
    snapshot = get_forecast_snapshot(sprint_id)
    final = get_final_snapshot(sprint_id)
    if not final:
        return []

    final_by_id = {t["task_id"]: t for t in final}

    # Build per-assignee stats
    assignee_stats = {}
    for t in snapshot:
        # Parse assignees from assignee_name (comma-separated)
        assignee = t.get("assignee_name") or "Unassigned"
        names = [n.strip() for n in assignee.split(",")] if assignee != "Unassigned" else ["Unassigned"]
        for name in names:
            if name not in assignee_stats:
                assignee_stats[name] = {"assigned": 0, "completed": 0, "hours": 0, "points": 0}
            assignee_stats[name]["assigned"] += 1
            final_task = final_by_id.get(t["task_id"])
            if final_task and final_task["task_status"] in ("complete", "closed"):
                assignee_stats[name]["completed"] += 1
            assignee_stats[name]["hours"] += t.get("hours") or 0
            assignee_stats[name]["points"] += t.get("points") or 0

    if not assignee_stats:
        return []

    avg_assigned = sum(s["assigned"] for s in assignee_stats.values()) / len(assignee_stats)

    result = []
    for name, stats in sorted(assignee_stats.items(), key=lambda x: x[1]["assigned"], reverse=True):
        pct = round(stats["completed"] / stats["assigned"] * 100) if stats["assigned"] > 0 else 0
        metric_value = 0
        if metric_type == "hours":
            metric_value = round(stats["hours"], 1)
        elif metric_type == "points":
            metric_value = round(stats["points"], 1)
        result.append({
            "name": name,
            "assigned": stats["assigned"],
            "completed": stats["completed"],
            "pct": pct,
            "metric_value": metric_value,
            "overloaded": stats["assigned"] > avg_assigned * 1.5,
        })

    return result
```

- [ ] **Step 3: Pass workload data to template**

In `src/routes/pages.py`, in `sprint_page()`, after the summary/progress lines and before the template render, add for closed sprints:

```python
    workload = []
    final_snapshot = []
    if status == "closed":
        from src.services.trend_service import get_workload_distribution
        from src.services.snapshot_service import get_final_snapshot
        workload = get_workload_distribution(sprint_id, team.get("metric_type", "task_count"))
        final_snapshot = get_final_snapshot(sprint_id)
```

Add `workload=workload, final_snapshot=final_snapshot` to the `_ctx()` call in the template response.

- [ ] **Step 4: Include workload table in sprint report**

In `templates/sprint_report.html`, before `{% include "components/task_table.html" %}` (line 62), add:

```html
  {% include "components/workload_table.html" %}
```

- [ ] **Step 5: Verify closed sprint report loads**

Navigate to `http://localhost:8000/sprint/6` — page should load without errors. Workload table will only appear for sprints with final snapshots.

- [ ] **Step 6: Commit**

```bash
git add templates/components/workload_table.html src/services/trend_service.py src/routes/pages.py templates/sprint_report.html
git commit -m "feat: add per-assignee workload distribution to sprint report"
```

---

### Task 8: Enhanced Scope Timeline with Sprint Days

**Files:**
- Modify: `templates/components/scope_timeline.html`

- [ ] **Step 1: Update scope timeline to show sprint day**

Replace `templates/components/scope_timeline.html` with:

```html
{% if scope_changes %}
<div class="panel">
  <h3>Scope Changes</h3>
  <div class="scope-timeline">
    {% for change in scope_changes %}
    <div class="scope-event {{ change.change_type }}">
      <div class="date">
        {% if change.sprint_day %}Day {{ change.sprint_day }}{% else %}{{ change.detected_at[:10] }}{% endif %}
      </div>
      <div class="detail">
        {% if change.change_type == 'added' %}➕{% else %}➖{% endif %}
        "{{ change.task_name }}"{% if change.assignee_name %} — {{ change.assignee_name }}{% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 2: Verify scope timeline renders**

Navigate to an active sprint with scope changes and confirm the timeline shows "Day X" instead of dates.

- [ ] **Step 3: Commit**

```bash
git add templates/components/scope_timeline.html
git commit -m "feat: show sprint day in scope change timeline"
```

---

### Task 9: Final Commit — Push All Changes

- [ ] **Step 1: Verify everything works end-to-end**

Test the following pages load without errors:
- `http://localhost:8000/` (home)
- `http://localhost:8000/sprint/7` (active sprint — LAN Sprint 7)
- `http://localhost:8000/sprint/6` (closed sprint — graceful degradation, no final snapshot)

- [ ] **Step 2: Push**

```bash
git push
```

- [ ] **Step 3: Also commit the KPI label changes from earlier session**

```bash
git add templates/components/kpi_cards.html src/routes/pages.py
git commit -m "polish: stories label on KPI cards and live completed count"
git push
```
