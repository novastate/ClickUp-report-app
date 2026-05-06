# Sprint Reporter — Roadmap

Living document. Updated as we ship.

**Source:** distillation of "what's missing" reflection on 2026-05-06. The app is strong on per-sprint capture but weak on cross-time and cross-level analysis — what ClickUp itself doesn't do well.

---

## Up next (high impact)

### 1. Area- and workspace-level trend reports
**Status:** queued (next initiative)

Today: only `/teams/{id}/trends` exists (per-team trend over multiple sprints).
Gap: no equivalent at Product Area or Workspace level. Cannot answer *"how is Network Services as a whole trending over the last 12 sprints?"*

Datan finns (per-sprint summaries via daily snapshots). Aggregera och rendera.

**Includes:**
- `/areas/{space_id}/trends` — area-level trend graph (avg velocity, completion, accuracy across teams in area)
- `/trends` (workspace) — workspace-wide aggregate
- Forecast accuracy as a first-class trend line (item #3 below — gratis add-on när #1 byggs)

### 2. Sprint-over-sprint diff (iteration follow-up)
**Status:** queued (paired with #1)

Today: closed sprint report shows the snapshot.
Gap: no view answers *"how does this sprint compare to last? Velocity up/down? Scope changes more/fewer? Which assignees delivered more/less?"*

The "iteration follow-up" the user explicitly mentioned ClickUp lacks.

**Includes:**
- "vs previous" delta on sprint report (velocity Δ, completion Δ, scope changes Δ, etc.)
- Assignee-level diff: who shifted load between sprints
- Visual: ↑ green / ↓ red arrows next to numbers

---

## Mid impact

### 4. Burnup chart
We have burndown. Burnup shows scope growth visually — when scope changes mid-sprint, burnup is clearer than burndown for "what happened here?"

### 5. Anomaly highlighting on trends pages
Today: just numbers and a sparkline. No callout when something's unusual.
Examples: *"LAN's last 3 sprints were 30% below their 12-sprint median"* surfaced as a banner or marked dot on the sparkline. Pulls the user's eye to what needs attention.

### 6. Capacity vs delivered (utilization)
We track capacity per assignee. We track delivered hours. But no view shows utilization (`delivered / capacity`) over time — the only way to detect systematic over-commit or under-commit.

---

## Lower impact / nice-to-have

### 7. Cycle time / lead time per task
We don't currently use ClickUp's status-history. How long do tasks sit in "in progress"? Strong signal for WIP problems and blockers.

### 8. Shareable read-only sprint links
"Skicka sprintrapporten till PALT" → idag kräver inloggning. Public-read-only-länk per closed sprint vore enkelt att addera.

### 9. Weekly digest (Slack/email)
Push instead of pull. *"Veckans översikt för dina favoriter."* Lightweight first pass: email-only via SMTP.

---

## Already shipped (this app's core)

- ✅ **Sprint capture & live view** — daily snapshots, KPIs, scope changes, burndown
- ✅ **Closed-sprint report** — frozen final snapshot, completion %, velocity, carry-overs, per-assignee workload
- ✅ **Per-team trends** (`/teams/{id}/trends`) — multi-sprint view, accuracy chart, period deltas
- ✅ **Workspace → Product Area → Team hierarchy** — `/`, `/areas/{id}`, drill-down navigation
- ✅ **Velocity sparklines** on team and area cards
- ✅ **Per-user team favorites** — ★ + "Your Favorites" section on home
- ✅ **OAuth login** (per-user ClickUp sign-in, with `AUTH_BYPASS=true` for dev)
- ✅ **Resilient daily snapshot job** — retry, catch-up, per-sprint isolation
- ✅ **Structured logging** — rotating file + stdout

---

## Items intentionally NOT on the roadmap

- **No "favorite area" / pinning of areas.** YAGNI; reduce area-card click cost first if it becomes friction.
- **No multi-workspace home page.** OAuth scopes user to one active workspace.
- **No drag-reorder anywhere.** Alphabetical sort is sufficient.
- **No notification badges / pager-style alerts.** Logs + future digest cover this.
- **No external observability platform** (Datadog/Sentry). Local logs are enough for the single-Mac → Azure path.

---

## Notes

This roadmap reflects what's missing **for a sprint reporting tool that complements ClickUp**, not what would replicate ClickUp. The core insight: ClickUp is great at task-level reporting; it's weak at iteration-over-time analysis. The high-impact items above lean into that gap.
