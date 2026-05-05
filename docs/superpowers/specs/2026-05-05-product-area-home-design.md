# Product-Area Grouped Home Page

## Context

The app's home page (`/`) currently shows a flat list of teams (`ANI`, `CNW`, `LAN`, `WAN`) as one-row entries with three buttons each (Sprint History, Trends, Settings). It's a directory — useful but bland and doesn't surface the hierarchy the user actually thinks in.

Verified against the live ClickUp API for workspace `SGIT`:
- Workspace `SGIT` has **15 Spaces** (= Product Areas): `Network Services`, `Core IT Services`, `Digital Workplace`, `Enterprise Workflows`, `IT Service Desk`, …
- Each Space contains multiple Folders (= Product Teams). `Network Services` alone has 15 folders, 4 of which are registered in the app today (`ANI`, `CNW`, `LAN`, `WAN`).
- Each Folder contains multiple Lists (= Sprints/Iterations).

The user's vocabulary mirrors this: **Product Area = Space**, **Product Team = Folder**, **Sprint = List**. The DB already stores `clickup_space_id` and `clickup_folder_id` per team — we just don't have the human-readable Space name nor a UI that groups by it.

## Problem

1. **Hierarchy is invisible.** A user looking at the home page can't tell whether `ANI` and `LAN` belong to the same Product Area or different ones.
2. **No status at a glance.** Every team shows "No active sprint" — the same default text dominates the page even when each team has 12 closed sprints with rich completion data behind them.
3. **Adding teams from new Product Areas would worsen this.** A flat list of 20 teams across 5 Product Areas would be unreadable.

## Goal

After this:

1. Home page groups teams by Product Area (= ClickUp Space). The Space name is the section heading.
2. Each Product Area section has its own roll-up stats (#teams, active sprints, avg velocity, last activity).
3. Each team row shows a velocity sparkline (last 8 closed sprints' completion %) and a "Last sprint" preview line, replacing the bland "No active sprint".
4. A workspace-level summary banner sits at the top.
5. The "New Team" flow captures and persists the Space name when a user picks a Space from the existing dropdown — no extra clicks for the user.

## Non-Goals

- **No filtering / searching** of teams on the home page. Volume is low (≤30 teams) for the foreseeable future.
- **No multi-workspace home page.** Workspace selection (from Initiative 3 OAuth) already happens at session level. The home page renders for the active workspace only.
- **No drill-down on Product Area.** The Space heading is just a label + roll-up stats; clicking it does nothing in v1. Click-through to a Product-Area dashboard is a future feature.
- **No team reordering / drag-and-drop.** Display order: alphabetical by Product Area, then alphabetical by team within.
- **No new metrics.** All stats reuse existing computations (`get_sprint_summary`, `get_team_trends`). We re-aggregate at the Product Area level — no new database columns for stats.
- **No backfill of historical Space names** beyond what existing teams need (4 rows). New teams write `space_name` at creation time.
- **No copy/i18n changes elsewhere in the app.** "Team" stays "Team" in URLs, breadcrumbs, settings — only the home page exposes "Product Area" terminology.

## Design

### Part 1: Schema

Add one column to `teams`:

```sql
ALTER TABLE teams ADD COLUMN space_name TEXT;
```

Wrapped in `try/except Exception: pass` per the existing migration pattern in `src/database.py`. No data backfill in the migration itself — the home route does opportunistic backfill on first load (see Part 4).

`team_service.create_team` gains an optional kw-only `space_name: str | None = None` parameter and includes it in the INSERT. Existing callers (already passing `workspace_id_new`) extend their kwargs.

`team_service.get_all_teams()` and `get_team(team_id)` automatically return the new column (they `SELECT *`).

### Part 2: Home route — grouping + stats

`src/routes/pages.py::home` builds a structured context object instead of a flat list:

```python
{
  "workspace": {
    "total_teams": 4,
    "total_areas": 1,
    "total_closed_sprints": 12,
    "avg_completion": 0.78,            # rounded to %
    "last_activity": "2h ago",          # human-readable from latest daily_progress.captured_at
  },
  "product_areas": [
    {
      "space_id": "90120495342",
      "space_name": "Network Services",
      "teams": [
        {
          "id": 1, "name": "ANI",
          "active_sprint": None,         # or {id, name, day, on_track}
          "last_closed": {                # most recent closed sprint, may be None
            "name": "Iteration 12",
            "completion": 0.87,
            "ago": "2 weeks ago",
          },
          "velocity_sparkline": [12, 14, 11, 13, 15, 12, 14, 16],  # last 8 closed velocities
          "metric_type": "task_count",
        },
        # ... CNW, LAN, WAN
      ],
      "stats": {
        "active_sprints": 0,
        "closed_sprints": 12,
        "avg_velocity": 13,
        "avg_completion": 0.85,
      },
    },
    # ... future Product Areas
  ],
}
```

Sorting:
- Product Areas alphabetical by `space_name`.
- Teams within an area alphabetical by `name`.

Performance: 4 teams × ~8 queries each is acceptable on SQLite (sub-100ms total). No caching for v1.

### Part 3: Backfill of `space_name`

On home-page load, after fetching `teams`, identify any teams with `space_name IS NULL`:

```python
teams_needing_backfill = [t for t in teams if not t.get("space_name")]
if teams_needing_backfill:
    # Group by (workspace_id, space_id) so we minimise API calls
    space_lookups = {(t["clickup_workspace_id"], t["clickup_space_id"])
                     for t in teams_needing_backfill}
    space_name_by_id = {}
    for ws_id, sp_id in space_lookups:
        try:
            spaces = await client.get_spaces(ws_id)
            for s in spaces:
                space_name_by_id[s["id"]] = s["name"]
        except ClickUpError as e:
            log.warning("Could not backfill space_name for ws %s: %s", ws_id, e)
    for t in teams_needing_backfill:
        name = space_name_by_id.get(t["clickup_space_id"])
        if name:
            team_service.update_team(t["id"], space_name=name)
            t["space_name"] = name
```

Cost: at most one `/team/{ws_id}/space` call per *unique workspace* in the team list, run only when there are NULL rows. Once all 4 existing rows are populated, this code path no-ops on subsequent loads.

If backfill fails (e.g., user's token revoked), log a warning, fall back to grouping by `clickup_space_id` raw, and show the ID as the Product Area heading. Better than crashing.

### Part 4: New Team flow

`templates/team_settings.html` already has a Space dropdown (populated via `/api/clickup/spaces`). When the user picks a space, the `<option>` value is `space_id` and the visible text is `space_name`. We don't currently capture the visible text on submit.

Two small changes:
1. The Space `<select>` gets a hidden mirror input that updates with the selected option's text:
   ```html
   <select id="space_select" name="clickup_space_id" onchange="document.getElementById('space_name').value = this.options[this.selectedIndex].text">
     ...
   </select>
   <input type="hidden" id="space_name" name="space_name" value="">
   ```
2. The POST handler in `src/routes/teams.py::create_team` reads `body.space_name` and passes it through to `team_service.create_team(..., space_name=...)`.

The `TeamCreate` Pydantic model gains `space_name: str | None = None`. Existing tests that construct `TeamCreate` continue to work (kwarg defaults to None).

### Part 5: Layout & visuals

`templates/home.html` re-rendered to match the structure in Part 2. Approximate skeleton:

```html
<section class="workspace-banner">
  <div class="banner-stat">
    <strong>{{ ws.total_teams }}</strong> teams
  </div>
  <div class="banner-stat">
    <strong>{{ ws.total_areas }}</strong> product areas
  </div>
  <div class="banner-stat">
    <strong>{{ ws.total_closed_sprints }}</strong> closed sprints
  </div>
  <div class="banner-stat">
    <strong>{{ (ws.avg_completion * 100) | round | int }}%</strong> avg completion
  </div>
  <div class="banner-stat text-muted">last activity {{ ws.last_activity }}</div>
</section>

{% for pa in product_areas %}
<section class="product-area">
  <header class="pa-header">
    <h2>{{ pa.space_name }}</h2>
    <span class="pa-badge">{{ pa.teams | length }} team{{ 's' if pa.teams|length != 1 else '' }}</span>
    <div class="pa-stats">
      <span>active sprints: <strong>{{ pa.stats.active_sprints }}</strong></span>
      <span>closed: <strong>{{ pa.stats.closed_sprints }}</strong></span>
      <span>avg velocity: <strong>{{ pa.stats.avg_velocity }}</strong></span>
      <span>avg completion: <strong>{{ (pa.stats.avg_completion * 100) | round | int }}%</strong></span>
    </div>
  </header>

  <div class="team-grid">
    {% for team in pa.teams %}
    <article class="team-card">
      <h3>{{ team.name }}</h3>
      {% if team.active_sprint %}
        <p class="status">Active: {{ team.active_sprint.name }} (day {{ team.active_sprint.day }})</p>
      {% elif team.last_closed %}
        <p class="status">Last sprint: {{ team.last_closed.name }} · {{ (team.last_closed.completion * 100)|round|int }}% · {{ team.last_closed.ago }}</p>
      {% else %}
        <p class="status text-muted">No sprints yet</p>
      {% endif %}
      <canvas class="sparkline" data-points="{{ team.velocity_sparkline | tojson }}"></canvas>
      <div class="team-actions">
        <a class="btn btn-secondary" href="/teams/{{ team.id }}/sprints">Sprint History</a>
        <a class="btn btn-secondary" href="/teams/{{ team.id }}/trends">Trends</a>
        <a class="btn btn-secondary" href="/teams/{{ team.id }}/settings">Settings</a>
      </div>
    </article>
    {% endfor %}
  </div>
</section>
{% endfor %}
```

CSS additions in `static/style.css`:

- `.workspace-banner`: horizontal flex, neutral background, larger numbers, modest padding.
- `.product-area`: section spacing, light divider above header.
- `.pa-header`: row with title + badge + stats inline.
- `.team-grid`: CSS grid, `repeat(auto-fill, minmax(320px, 1fr))`. Each card is full-width on mobile, multi-column on desktop.
- `.team-card`: white background, subtle border, padding, hover state lifting. Reuses existing token variables (`--purple-500` accent on hover, etc.).
- `.sparkline`: 100% width × 28px height canvas.

The design uses the design tokens already in `static/style.css` (Plus Jakarta Sans font, ClickUp purple accent). No new tokens needed.

### Part 6: Sparkline JS

A small block in `static/dashboard.js` (or a new `static/sparklines.js` loaded in `home.html` only):

```js
document.querySelectorAll('canvas.sparkline').forEach(canvas => {
  const points = JSON.parse(canvas.dataset.points || '[]');
  if (points.length === 0) return;
  // Use Chart.js (already loaded in base.html)
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: points.map((_, i) => i + 1),
      datasets: [{
        data: points,
        borderColor: 'rgba(123, 104, 238, 0.9)',  // ClickUp purple
        borderWidth: 2,
        tension: 0.3,
        pointRadius: 0,
        fill: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
    },
  });
});
```

If `velocity_sparkline` is empty (team has no closed sprints), the canvas just renders nothing — no Chart.js call.

### Files changed

| File | Action |
|---|---|
| `src/database.py` | Add `ALTER TABLE teams ADD COLUMN space_name TEXT` migration |
| `src/services/team_service.py` | `create_team(..., space_name=None)`, persist on INSERT |
| `src/models.py` | Add `space_name: str \| None = None` to `TeamCreate` (or appropriate Pydantic model) |
| `src/routes/teams.py` | Pass `body.space_name` into `team_service.create_team` |
| `src/routes/pages.py` | Rewrite `home` to build the new context (Part 2 + 3) |
| `templates/home.html` | Replace flat list with grouped layout (Part 5) |
| `templates/team_settings.html` | Add hidden `space_name` input mirroring the Space `<select>` |
| `static/style.css` | New rules for `.workspace-banner`, `.product-area`, `.team-card`, `.team-grid`, `.sparkline` |
| `static/dashboard.js` | Sparkline-rendering block |

No new dependencies. No tests added (per non-goal "no test coverage expansion" — Initiative 1B is the test-coverage initiative; this UI work is light enough that manual scry verification is appropriate).

## Verification

Manual via scry:

1. Restart app. Visit `/`. Expect a Product Area section labelled `Network Services` containing all 4 teams as cards.
2. Verify the banner numbers match (`1` area, `4` teams, `N` closed sprints).
3. Verify each team card shows either an active sprint or "Last sprint: ..." preview, plus a sparkline (renders only if the team has closed sprints).
4. Inspect DB: `sqlite3 sprint_data.db "SELECT name, space_name FROM teams"` — all 4 should have `Network Services`.
5. Restart app a second time. Verify no extra ClickUp API calls in `app.log` (backfill is idempotent — runs only when NULL rows exist).
6. Mobile viewport (<480px): verify cards stack to one column, banner wraps cleanly, sparkline still readable.

## Risk

Low. Schema change is additive. Backfill is opportunistic and degrades gracefully on API failure. Layout is rewritten but only on the home page — all other routes untouched. No production-data risk.

## Distribution

Standard deploy bundle. On first load after deploy, the home route runs the backfill once. Subsequent loads are no-ops on the backfill path.
