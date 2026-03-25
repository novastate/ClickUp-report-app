# Sprint Retro & Insights Enhancements

**Date**: 2026-03-25
**Status**: Draft

## Problem

ClickUp loses track of incomplete tasks once they're moved to the next sprint or backlog. The app captures a forecast baseline, but doesn't record final task states at sprint close. This means:

- No way to see what was left unfinished in a closed sprint
- No carry-over detection between sprints
- No per-person workload analysis for retros
- Scope change timeline lacks detail (who added what, when)

## Design

### 1. Final Snapshot at Sprint Close

**What changes**: When a sprint is closed (manually or auto-close), capture every task's current status, assignee, and hours alongside the existing baseline snapshot.

**Database**: New table `sprint_final_snapshots` with index.

```sql
CREATE TABLE sprint_final_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    task_status TEXT NOT NULL,
    assignee_name TEXT,
    assignee_hours TEXT,  -- JSON array of [{name, hours}]
    points REAL,
    hours REAL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_final_snap_sprint ON sprint_final_snapshots(sprint_id);
```

Also add `assignee_hours TEXT` column to the existing `sprint_snapshots` table and update `save_forecast_snapshot()` to persist it. This is needed for workload distribution to compare baseline vs final assignments.

**Code changes** (two locations):
1. `close_sprint_route()` in `src/routes/sprints.py` — add call to new `save_final_snapshot()` after fetching tasks, before calling `do_close_sprint()`
2. `daily_snapshot_job()` in `app.py` — add same `save_final_snapshot()` call in the auto-close block, before calling `do_close_sprint()`

**Why a separate table**: The existing `sprint_snapshots` table stores the baseline (forecast). Keeping them separate avoids ambiguity — baseline is baseline, final is final.

### 2. Unfinished Tasks on Closed Sprint Report

**What changes**: The sprint report page shows unfinished tasks in a prominent section at the top, before the completed tasks.

**Definition of "unfinished"**: Tasks that were in the **original forecast baseline** (not scope additions) and are not in status "complete" or "closed" in the final snapshot. Scope additions that weren't completed are shown separately in the scope changes section — they have a different retro meaning (added late AND not finished).

**UI treatment**:
- New section titled "Unfinished" above the task table
- Each unfinished task shows: name, assignee, status, and the team's metric (hours/points/count)
- Sorted by the team's metric descending (biggest misses first). For task_count teams, sort by status then name.
- Visual indicator: orange left border or background tint
- Count shown in a new KPI card: "Unfinished: X" with metric-appropriate label (stories for all types — the forecasted count is always task count)

**Task table changes**: When viewing a closed sprint, tasks are ordered:
1. Unfinished (from baseline forecast, not completed) — highlighted
2. Completed
3. Scope additions (added after forecast)
4. Scope removals

### 3. Carry-Over Detection

**What changes**: When closing a forecast for a new sprint, check the previous sprint's final snapshot for unfinished tasks. If any of those task IDs appear in the new sprint's task list, tag them as "carried over".

**Database**: New column on `sprint_snapshots`

```sql
ALTER TABLE sprint_snapshots ADD COLUMN carried_over BOOLEAN DEFAULT 0;
```

(Added via try/except in `init_db()`, matching existing pattern for `capacity_mode` column.)

**Detection logic** (in `close_forecast_route()`):
1. Find the most recent closed sprint for the same team
2. Get its final snapshot, filter to unfinished tasks
3. Compare task IDs with the new sprint's task list
4. Mark matching tasks as `carried_over = 1` in the new sprint's baseline snapshot

**Edge case**: If the previous sprint hasn't been closed yet (no final snapshot), skip carry-over detection. The data isn't available. This is acceptable — carry-over is a best-effort enrichment, not a hard requirement.

**UI treatment**:
- Carried-over tasks show a "↩ Carried Over" badge in the task table
- New KPI or sub-stat: "X carried over from previous sprint"
- In the previous sprint's report, unfinished tasks that were carried over show "→ Carried to Sprint X"

### 4. Workload Distribution (Retro View)

**What changes**: New section on the closed sprint report showing per-assignee performance breakdown.

**UI**: Table below the existing content, adapts to team's metric type:

**Hours-based teams:**

| Assignee | Stories | Completed | Completion % | Hours |
|----------|---------|-----------|-------------|-------|
| Alice    | 8       | 7         | 88%         | 24h   |
| Bob      | 6       | 3         | 50%         | 18h   |

**Points-based teams:**

| Assignee | Stories | Completed | Completion % | Points |
|----------|---------|-----------|-------------|--------|
| Alice    | 8       | 7         | 88%         | 21pts  |
| Bob      | 6       | 3         | 50%         | 13pts  |

**Task-count teams:**

| Assignee | Stories | Completed | Completion % |
|----------|---------|-----------|-------------|
| Alice    | 8       | 7         | 88%         |
| Bob      | 6       | 3         | 50%         |

(No extra metric column — count IS the metric.)

**Data source**: Built from `sprint_snapshots` (baseline) and `sprint_final_snapshots` (final). For each assignee:
- **Stories**: Task count in baseline where they are assignee (parsed from `assignee_hours` JSON or `assignee_name`)
- **Completed**: Task count in final snapshot with status complete/closed
- **Hours/Points**: From `assignee_hours` JSON breakdown (hours teams) or `points` field (points teams). Omitted for task_count teams.

**Highlight rules**:
- Completion below 60%: red text
- Completion above 90%: green text
- If assigned count is >1.5x the team average: "overloaded" indicator

### 5. Scope Change Timeline Detail

**What changes**: Enhance scope change records with timing detail.

**Database**: Add column to `scope_changes`

```sql
ALTER TABLE scope_changes ADD COLUMN sprint_day INTEGER;
```

(Added via try/except in `init_db()`, matching existing pattern.)

**When populated**: `detect_scope_changes()` calculates `sprint_day` as `(today - sprint.start_date).days + 1` when recording a new change.

**Backfill**: Existing scope changes can be backfilled since `detected_at` and sprint `start_date` are both available. Run in migration: `UPDATE scope_changes SET sprint_day = CAST(julianday(detected_at) - julianday((SELECT start_date FROM sprints WHERE id = sprint_id)) + 1 AS INTEGER) WHERE sprint_day IS NULL`.

**UI changes to scope timeline chart**:
- X-axis shows sprint days (Day 1, Day 2, ...)
- Each scope change plotted on its day
- Hover/tooltip shows: task name, assignee, day added/removed
- Visual: green dots for added, red dots for removed

**Retro value**: Team can see "most scope was added on Day 3" or "scope crept in throughout the sprint".

## Implementation Order

1. **Final snapshot** — foundation for everything else (includes DB migration, `save_final_snapshot()`, changes to `close_sprint_route()` and `daily_snapshot_job()`)
2. **Unfinished tasks highlight** — immediate retro value
3. **Carry-over detection** — connects sprints together
4. **Workload distribution** — deeper retro insight
5. **Scope timeline detail** — polish

## Migration

- New table `sprint_final_snapshots` with index: created on startup via `init_db()`
- New column `assignee_hours` on `sprint_snapshots`: added via try/except ALTER TABLE in `init_db()`
- New column `carried_over` on `sprint_snapshots`: added via try/except ALTER TABLE in `init_db()`
- New column `sprint_day` on `scope_changes`: added via try/except ALTER TABLE in `init_db()`, with backfill query for existing records
- Existing closed sprints won't have final snapshots — their reports continue to work as before, just without the unfinished/workload sections. A backfill is not practical since the tasks have already moved in ClickUp.

## What's NOT in scope

- Notifications/alerts (future enhancement)
- Cross-team dashboards (future enhancement)
- ClickUp webhook integration for real-time updates
- Task-level time tracking (depends on ClickUp time tracking setup)
