# ClickUp API Discovery — PA Setup Template Space

**Date:** 2026-03-18
**API User:** Henrik Collin (henrik.collin@sandvik.com, ID: 49518522)
**Test Space:** PA Setup Template (ID: 90125112812) — SGIT Workspace (ID: 31570067)

---

## Workspaces Accessible

| Workspace | ID | Role | Members |
|---|---|---|---|
| U6 | 31542715 | Owner | 3 |
| SGIT | 31570067 | Admin | 188 |

## PA Setup Template Space — Configuration

- **Statuses:** to do → in progress → complete
- **Features enabled:** Sprints, Points, Time Tracking, Time Estimates, Priorities, Tags, Custom Fields, Milestones, WIP Limits, Multiple Assignees
- **Priorities:** urgent, high, normal, low
- **Members:** Andrew Donovan, Henrik Collin, Alexander Carlsson

## Space Structure

### Folder: PA Planning (ID: 90127681178)
| List | ID | Task Count |
|---|---|---|
| PA Intake | 901213285507 | 2 |
| PA Backlog | 901212834844 | 6 |
| OKRs | 901215794711 | 2 |

### Folder: PALT (ID: 90127681191)
| List | ID | Task Count |
|---|---|---|
| PALT Backlog | 901214727285 | 4 |

### Folder: Product Team Template 1 (ID: 90128667171)
| List | ID | Task Count |
|---|---|---|
| Intake | 901214727256 | 0 |
| Backlog | 901214727258 | 7 |
| Iteration 5 (23/2 - 8/3) | 901215994887 | 0 |
| Iteration 6 (9/3 - 22/3) | 901215994889 | 5 |

## Task Data Model

### Standard Fields Available
| Field | Type | Notes |
|---|---|---|
| id | string | Unique task ID |
| name | string | Task title |
| status | object | `status`, `type`, `color` |
| priority | object | urgent/high/normal/low (nullable) |
| points | number | Story points (nullable) |
| assignees | array | User objects with username, email, id |
| start_date | timestamp | ms epoch (nullable) |
| due_date | timestamp | ms epoch (nullable) |
| date_created | timestamp | ms epoch |
| date_updated | timestamp | ms epoch |
| date_closed | timestamp | ms epoch (nullable) |
| date_done | timestamp | ms epoch (nullable) |
| time_estimate | number | ms (nullable) |
| time_spent | number | ms (nullable) |
| tags | array | Tag objects |
| parent | string | Parent task ID (for subtasks) |
| list | object | Which list the task belongs to |
| folder | object | Which folder |
| space | object | Which space |
| dependencies | array | Task dependencies |
| linked_tasks | array | Linked tasks |
| checklists | array | Checklist items |

### Custom Fields

| Field | Type | ID | Options |
|---|---|---|---|
| Development phase | drop_down | 47e59200-069d-4703-b9d1-339faf17fdb3 | Pipeline, Development, Transition, Completed |
| Group IT PA | drop_down | 7658409c-2a25-41da-aa51-822bd1bde39d | Core PA, CS A PA, CS E PA, DW PA, EW PA, GILT, Group IT Wide, NS PA, OPS-LT |
| Planned | drop_down | bb92a06e-7cd1-462b-94bf-ded231452c28 | Planned, Adhoc |
| Product Teams | labels | de6836dc-410d-43d6-8baa-bbc9c89aa479 | NS-LAN, NS-WAN, NS-CNW, NS-Support, Cloud Managed Services, Compute Operations, Output Management, Core Support Team, Application Operations, DW-Productivity, DW-Collaboration, DW-Telecom, DW-Managed Clients, DW-Digital Employee Exp, DW-Managed Apps, IT Service Desk, EW-Core IT Workflow, EW-Core Platform, EW-IT Workflow & Experience, EW-Global IT Process, EW-CoE & Innovation, EW-SecOps, EUR, Ops Automation CoE |
| Responsible Resource | users | 3e237fe0-83fd-46d2-b7ee-30c28ab0f1af | User picker |
| Andrew's Field | drop_down | e0a48bf3-52e2-4aab-a70b-548a3a61c1d2 | Option 1, Option 2 (test field) |

## Key API Endpoints

```
Base URL: https://api.clickup.com/api/v2

# Auth header: Authorization: <api_token>

GET /team                           # All workspaces
GET /team/{team_id}/space           # Spaces in workspace
GET /space/{space_id}/folder        # Folders in space
GET /space/{space_id}/list          # Folderless lists
GET /folder/{folder_id}/list        # Lists in folder
GET /list/{list_id}/task            # Tasks in list
    ?include_closed=true
    &subtasks=true
    &page=0
GET /task/{task_id}                 # Single task detail
GET /task/{task_id}/time_in_status  # Time spent per status
GET /list/{list_id}/field           # Custom fields for a list
GET /team/{team_id}/time_entries    # Time tracking entries
```

## Sprint Reporting Data Points

Key metrics derivable from this API for sprint reporting:

1. **Sprint Velocity** — Sum of `points` for tasks with status=complete per iteration list
2. **Sprint Burndown** — Track `date_closed` vs `due_date` across iteration tasks
3. **Completion Rate** — Completed tasks / total tasks per iteration
4. **Cycle Time** — `date_closed` - `date_created` (or use time_in_status API)
5. **Lead Time** — `date_closed` - first appearance in backlog
6. **Backlog Health** — Tasks by priority, age, and points in backlog lists
7. **Team Workload** — Tasks by assignee across iterations
8. **Planned vs Adhoc** — Custom field "Planned" breakdown
9. **Development Phase** — Pipeline → Development → Transition → Completed flow
10. **Product Team Performance** — Filter by "Product Teams" label

## Sample Task Data

From Backlog (Product Team Template 1):
- "This is my idea" — 1 point, Compute Operations team
- "Story Test 1" — 2 points
- "Story test 2" — 1 point
- "Task" — 1 point
- "Epic 1", "Feature 1", "Feature 2" — no points assigned
- "story" — NS-LAN team

## Notes
- Iteration lists follow naming pattern: `Iteration N (date - date)`
- Sprint = Iteration list; Backlog = separate list in same folder
- The folder structure is: Space → Folder (per team area) → Lists (Intake, Backlog, Iterations)
- Sprints feature is enabled at space level
- Time tracking is enabled with rollup
