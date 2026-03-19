# Sprint Reporting MVP — Design Spec

**Date:** 2026-03-18
**Status:** Draft
**Author:** Henrik Collin + Claude

---

## Purpose

Build a lightweight web app that tracks sprint performance for ClickUp teams. The native ClickUp reports lack the ability to measure team performance over time, track scope changes during a sprint, and freeze sprint reports for historical comparison.

This MVP serves Henrik as a team coach — a tool to follow a team during sprints, ask the right questions based on data, and measure improvement over time.

## Constraints

- MVP is single-user (Henrik), running locally on his laptop
- No infrastructure required — single `python app.py` command
- Develop against PA Setup Template space (ID: 90125112812) in SGIT workspace
- Design must work with any SGIT team folder later
- Store only snapshots and metrics, not raw ClickUp data
- Teams use different metrics: some use points, some hours, some task count

## Architecture

```
ClickUp API → FastAPI Backend → SQLite → HTML + Chart.js Dashboard
```

- **FastAPI** serves both the REST API and HTML dashboard pages
- **ClickUp API** called live to fetch current sprint data; API key stored in local config
- **SQLite** single file database storing only snapshots and metrics
- **Dashboard** HTML pages with Chart.js, served by the same Python process
- **Run command:** `python app.py` → `http://localhost:8000`

### What gets stored in SQLite

- Sprint forecast baselines (task list at forecast close)
- Daily progress snapshots (auto-captured + on-demand)
- Scope changes (tasks added/removed after forecast)
- Team configuration (metric type, ClickUp IDs)

### What does NOT get stored

- Raw task descriptions or content
- Personal data beyond assignee display names
- ClickUp API keys (stored in local config file, not DB)

## Data Model

### Teams

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Team display name |
| clickup_space_id | TEXT | ClickUp space ID |
| clickup_folder_id | TEXT | ClickUp folder containing iteration lists |
| metric_type | TEXT | `points` \| `hours` \| `task_count` |
| sprint_length_days | INTEGER | Default 14 |
| created_at | DATETIME | |

### Sprints

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| team_id | INTEGER FK | References teams.id |
| name | TEXT | Sprint name (from ClickUp list name) |
| clickup_list_id | TEXT | ClickUp iteration list ID |
| start_date | DATE | First day of sprint |
| end_date | DATE | Last day of sprint |
| forecast_closed_at | DATETIME | When "Close Forecast" was clicked (NULL = still planning) |
| closed_at | DATETIME | When "Close Sprint" was clicked (NULL = still active) |
| created_at | DATETIME | |

**Derived status** (not stored — computed from timestamps):
- `planning` = `forecast_closed_at IS NULL`
- `active` = `forecast_closed_at IS NOT NULL AND closed_at IS NULL`
- `closed` = `closed_at IS NOT NULL`

### Sprint Snapshots (forecast baseline)

Captured once when "Close Forecast" is clicked.

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| sprint_id | INTEGER FK | References sprints.id |
| task_id | TEXT | ClickUp task ID |
| task_name | TEXT | Task title |
| task_status | TEXT | Status at snapshot time |
| assignee_name | TEXT | Display name (nullable) |
| points | REAL | Story points (nullable) |
| hours | REAL | Time estimate in hours (nullable) |
| created_at | DATETIME | |

### Daily Progress

Auto-captured once daily while sprint is active. Also captured on-demand via "Refresh Now".

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| sprint_id | INTEGER FK | References sprints.id |
| captured_at | DATETIME | When this snapshot was taken |
| total_tasks | INTEGER | Total tasks in sprint list |
| completed_tasks | INTEGER | Tasks with closed status |
| total_points | REAL | Sum of points (nullable) |
| completed_points | REAL | Points completed (nullable) |
| total_hours | REAL | Sum of hours (nullable) |
| completed_hours | REAL | Hours completed (nullable) |


**Note:** `tasks_added` and `tasks_removed` counts are derived from the scope_changes table at query time (`COUNT(*) WHERE sprint_id = ? AND change_type = ?`). They are not stored in daily_progress.

### Scope Changes

Tracked by comparing live ClickUp data against the forecast snapshot.

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| sprint_id | INTEGER FK | References sprints.id |
| task_id | TEXT | ClickUp task ID |
| task_name | TEXT | Task title |
| change_type | TEXT | `added` \| `removed` |
| detected_at | DATETIME | When the change was first detected |
| assignee_name | TEXT | Who added it (nullable) |

**Scope change tracking is event-log style.** Each detection creates a new row. If a task is removed and re-added, both events are recorded. The unique key for deduplication within a single refresh is `(sprint_id, task_id, change_type, detected_at)`. Net scope change is calculated by counting adds minus removes per task_id.

## Sprint Lifecycle

```
1. PLANNING
   - App detects iteration lists in the team's ClickUp folder
   - Team fills the iteration list in ClickUp
   - App shows live task list (no tracking yet)

2. CLOSE FORECAST (button click)
   - Snapshots all tasks currently in the iteration list
   - This becomes the baseline — "what we committed to"
   - Sprint status changes to "active"
   - Daily auto-snapshots begin

3. ACTIVE SPRINT (2 weeks)
   - Dashboard shows live burndown, KPIs, scope changes
   - Auto-snapshot captured daily for historical graph
   - "Refresh Now" button pulls fresh data on demand
   - Scope changes detected by comparing live data vs forecast snapshot
   - Any task added to the list after forecast = scope addition
   - Any task removed from the list after forecast = scope removal

4. CLOSE SPRINT (button click)
   - Final snapshot captured
   - Sprint report frozen for historical reference
   - closed_at timestamp set
   - Sprint appears in history list and feeds into trend charts
   - Note: auto-close is a future consideration. MVP uses manual close only.
```

## Dashboard Pages

### 1. Live Sprint View

The main screen during a sprint — standup companion.

**Components:**
- **Top bar:** Sprint name, date range, status badge, "Refresh Now" button, "Close Sprint" button
- **KPI cards (clickable filters):**
  - Forecasted (total tasks/points/hours at forecast close)
  - Completed (current count)
  - Scope Changes (+added / -removed)
  - Completion % (with day X of 14)
  - On Track indicator: **ahead** = actual remaining < ideal remaining by >10%, **on track** = within 10% of ideal, **behind** = actual remaining > ideal remaining by >10%. Ideal burndown = linear from forecasted total to 0 over sprint_length_days
- **Burndown chart:** Ideal line vs actual progress over sprint duration
- **Scope changes panel:** Chronological list of additions/removals with dates and who
- **Task list:** All tasks with status, assignee, metric value. Scope additions highlighted. Filtered by clicking KPI cards above

**KPI card interaction:** Clicking any KPI card filters the task list below to show only relevant tasks. Click "Completed" → shows only completed tasks. Click "Scope Changes" → shows only added/removed tasks. Click again to clear filter.

### 2. Sprint Review / Report

Frozen report after sprint ends. Used in retrospective.

**Components:**
- **Top bar:** Sprint name, dates, CLOSED badge, "Back to History" link
- **Summary verdict:** Green/yellow/red banner with headline (e.g., "Sprint Goal Achieved — 87% Completion")
- **KPI cards (clickable filters):** Forecasted, Completed (split: from forecast + from added), Not Completed, Scope Changes
- **Final burndown chart:** Complete 14-day burndown
- **Forecast accuracy bar:** Visual percentage — committed vs delivered
- **Scope change timeline:** Chronological timeline with dates and details
- **Task list:** Full task list with status, assignee, metric value. Filtered by KPI card clicks. Not-completed tasks highlighted

### 3. Team Performance Over Time

Multi-sprint trend view — the coaching view.

**Components:**
- **Top bar:** Team name, sprint range selector (Last 4 / Last 8 / All)
- **Trend KPI cards:** Avg velocity, avg completion rate, avg scope change, forecast accuracy — each with trend arrow (improving/declining)
- **Velocity bar chart:** Tasks/points/hours per sprint with trend line
- **Completion rate line chart:** Per sprint with configurable target line
- **Scope changes chart:** Added vs removed per sprint (stacked bar)
- **Sprint comparison table:** All sprints side by side (velocity, completion, scope change, forecast accuracy). Click any row to open its report

### 4. Team Settings

Configuration page.

**Fields:**
- Team name
- ClickUp Space ID (dropdown populated from API)
- ClickUp Folder ID (dropdown populated from API, filtered by space)
- Metric type: points | hours | task_count (radio buttons)
- Sprint length in days (default 14)

### 5. Sprint History

List of all past and current sprints.

**Components:**
- Table with columns: Sprint name, dates, status, velocity, completion %, scope changes
- Click any row to open its report (or live view if active)
- Filter by status (planning / active / closed)

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Database | SQLite (single file) |
| Frontend | HTML templates (Jinja2), Chart.js |
| HTTP client | httpx (async ClickUp API calls) |
| Task scheduler | APScheduler (daily auto-snapshot) |
| CSS | Minimal custom CSS (no framework) |

## API Endpoints

```
GET  /                          → Dashboard home (redirect to active sprint or history)
GET  /teams                     → Team settings list
POST /teams                     → Create team
GET  /teams/{id}                → Get single team (for edit form)
PUT  /teams/{id}                → Update team settings
DELETE /teams/{id}              → Delete team
POST /teams/{id}/sync-sprints   → Detect new iteration lists in ClickUp folder, create sprint records
GET  /teams/{id}/sprints        → Sprint history for team
GET  /sprints/{id}              → Sprint detail (live or report)
POST /sprints/{id}/close-forecast → Close forecast, capture baseline
POST /sprints/{id}/close        → Close sprint, freeze report
POST /sprints/{id}/refresh      → On-demand data refresh from ClickUp
GET  /sprints/{id}/tasks        → Task list with optional status filter
GET  /teams/{id}/trends         → Multi-sprint trend data
GET  /api/clickup/spaces        → Proxy: list available spaces
GET  /api/clickup/folders/{space_id} → Proxy: list folders in space
```

## Configuration

Local config file (`.env`):

```
CLICKUP_API_KEY=pk_xxxxx
HOST=localhost
PORT=8000
DB_PATH=./sprint_data.db
DAILY_SNAPSHOT_TIME=06:00
```

The ClickUp API key is global (one key per app instance, not per team). All teams in SGIT share the same workspace and the same API key. The `.env` file should be in `.gitignore`.

## Scope Change Detection Logic

On every refresh (manual or auto):
1. Fetch current tasks from the ClickUp iteration list
2. Compare task IDs against the forecast snapshot
3. New task IDs not in snapshot → `added` scope change
4. Snapshot task IDs not in current list → `removed` scope change
5. Store new scope changes with timestamp
6. Update daily progress record

## Out of Scope (MVP)

- Multi-user authentication / login
- Server deployment / hosting
- Email/Slack notifications
- Custom dashboards or drag-and-drop widgets
- Direct ClickUp write-back (moving tasks, changing status)
- Comparison between different teams
- Sprint goal tracking (free-text goals)
- Retrospective notes integration
- PDF export of sprint reports
- Auto-close sprints at midnight (MVP uses manual close)

## Future Considerations

- Host centrally for multiple coaches (add auth, PostgreSQL)
- Configurable planning day per team (some teams don't plan on day 1)
- Cross-team comparison views
- Export to PowerPoint/PDF for management reporting
- Integration with other tools (Azure DevOps, Jira) if needed
