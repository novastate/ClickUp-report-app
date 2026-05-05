# Workspace → Product Area → Team Hierarchy

## Context

The home page (`/`) currently renders Product Area sections with team cards underneath. In a workspace with one Product Area this looks like a drill-down view of that single area, not a workspace-level overview. As soon as the user adds teams from a second Product Area, the home page becomes a long vertical scroll of stacked area sections.

The user's mental model — confirmed in conversation — is a 3-level hierarchy:

1. **Workspace** (top) — list of Product Areas with rollup stats
2. **Product Area** (middle) — list of Product Teams (current home layout, scoped to one area)
3. **Team** (existing) — list of Sprints (already at `/teams/{id}/sprints`)

This initiative splits the current home page into level 1 + level 2 routes, with breadcrumb navigation between them.

## Problem

Three concrete pains today:

1. **Home is the wrong level.** It shows the inside of one Product Area, not an overview of all areas. With 5+ areas it would scroll forever.
2. **No drill-down semantics.** No URL identifies "the Network Services area" — teams are reached only via `/teams/{id}/sprints`. Skipping a level makes it impossible to bookmark or share an area-level view.
3. **Inconsistent breadcrumbs.** Sprint pages already breadcrumb `Home > Team > Sprint`. Inserting `Area` between Home and Team makes the trail match the actual hierarchy.

## Goal

After this:

1. `GET /` shows a **Workspace overview** — banner + grid of Product Area cards (one per Space).
2. `GET /areas/{space_id}` shows a **Product Area detail** — banner scoped to that area + its teams grid (the current home layout, just at a new URL).
3. Clicking an area card navigates to `/areas/{space_id}`. Each area card displays roll-up stats and a mini sparkline of the area's recent completion-rate history.
4. Breadcrumbs reflect the new path: `Home > Network Services > ANI > Sprint 12` (where each segment is a clickable link to the corresponding level).
5. The "Last sprint" preview that used to live on team cards moves naturally one level up — area cards now show "Last activity in this area" instead.

## Non-Goals

- **No new database tables or columns.** All level-1 data is computed by aggregating per-team data we already have.
- **No `/workspaces/...` routes.** The user is already scoped to a workspace via OAuth/session; there's no multi-workspace listing UI.
- **No team-level aggregation page** between area and sprint. Team-level lives at the existing `/teams/{id}/sprints` route.
- **No client-side routing or SPA behavior.** Plain server-rendered pages with full navigation.
- **No expand/collapse, drag-reorder, or filter UI.** Static grid + alphabetical sort within each level.
- **No "favorite area" / pinning.** Skip.
- **No deletion-from-overview affordance.** Settings link still on team-level pages, area has no settings page in v1.
- **No mobile-specific drill-down treatment beyond grid → single column at <720px** (existing breakpoint already handles this).

## Design

### Part 1: Routes

Two routes change/are added in `src/routes/pages.py`:

| Path | Handler | Returns |
|---|---|---|
| `GET /` | `home(request, user=…)` | `home.html` — workspace overview |
| `GET /areas/{space_id}` | `area_page(request, space_id, user=…)` | `area.html` — area detail (teams grid) |

The existing handlers for `/teams/{id}/sprints`, `/sprint/{id}`, etc. are unchanged.

### Part 2: `home_service` refactor

`src/services/home_service.py` already has `build_home_context(client, teams)` returning `{workspace, product_areas}`. Refactor into two top-level functions:

- `build_workspace_overview(client, teams) -> dict` — returns the data for the new home page:
  ```python
  {
    "workspace": { ... same as current ... },
    "areas": [
      {
        "space_id": "...",
        "space_name": "Network Services",
        "team_count": 4,
        "stats": {"active_sprints": 0, "closed_sprints": 4,
                  "avg_velocity": 26, "avg_completion": 0.56},
        "completion_sparkline": [0.48, 0.29, 0.15, 0.47, ...],
        "last_activity": "2 weeks ago",
      },
      # ...
    ],
  }
  ```
  The `completion_sparkline` is the chronologically-ordered completion-rate of all closed sprints across all teams in the area, capped at the last 12 entries.

- `build_area_detail(client, teams, space_id) -> dict` — filters teams down to those whose `clickup_space_id == space_id`, then runs the existing per-team logic. Returns:
  ```python
  {
    "area": {                                       # was inside product_areas[0] before
      "space_id": "...",
      "space_name": "Network Services",
      "stats": { ... },
    },
    "teams": [ ... same per-team card payload as today ... ],
  }
  ```
  Returns `None` if no team matches `space_id` (route returns 404).

The shared private helpers (`_team_card`, `_area_stats`, `_humanize_ago`, `_backfill_space_names`) stay; only the public surface changes.

The legacy `build_home_context` is **removed** — its only caller is the home route, which now uses `build_workspace_overview`.

### Part 3: Templates

#### `templates/home.html` (rewrite, level-1)

Workspace banner + area-card grid.

Each **area card** shows:
- Title: space name (clickable, links to `/areas/{space_id}`)
- Badge: "N teams"
- Stats row: active sprints / closed sprints / avg velocity / avg completion
- Mini sparkline: completion-rate trend (last 12 closed sprints across all teams in the area)
- Last activity meta line at the bottom

Card hover lifts and highlights the border, same treatment as team cards.

#### `templates/area.html` (new, level-2)

Same look as the current home page, just renamed and scoped to one area:

- Workspace banner is replaced by an **area banner** showing: area name (large, no longer clickable since you're on its page), team count, area-level stats. The same banner design used on home for workspace stats — just populated with area-level numbers.
- Below: the existing teams-grid layout — unchanged.

#### Breadcrumbs

The existing breadcrumb component (`templates/components/breadcrumbs.html`) already accepts a list. Update each route's `_breadcrumbs(...)` call:

| Page | Crumbs |
|---|---|
| `/` (home) | (none — root) |
| `/areas/{space_id}` | `Home / Network Services` |
| `/teams/{id}/sprints` | `Home / Network Services / ANI` |
| `/sprint/{id}` | `Home / Network Services / ANI / Sprint 12` |

The team-level crumbs need to know the team's `space_name`, which is already on the row from the `space_name` column added earlier.

### Part 4: CSS

Add `.area-card` rules to `static/style.css`. Reuse the existing `.team-card` token-based styling — same border/radius/hover, slightly different inner layout (bigger title, prominent stats):

```css
.area-card {
  /* same shell as .team-card */
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  text-decoration: none;
  color: inherit;
  min-height: 200px;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.area-card:hover {
  border-color: var(--accent);
  box-shadow: 0 4px 16px rgba(123, 104, 238, 0.10);
  transform: translateY(-1px);
}
.area-card-header { display: flex; align-items: baseline; gap: 12px; }
.area-card-title { font-size: 1.4rem; font-weight: 600; letter-spacing: -0.01em; margin: 0; }
.area-card-badge { /* same as .pa-badge */ }
.area-card-stats {
  display: flex; gap: 24px; font-size: 12px;
  color: var(--text-muted);
}
.area-card-stat strong { color: var(--text); font-size: 16px; font-weight: 600; }
.area-card-meta { font-size: 12px; color: var(--text-muted); margin-top: auto; }
```

The grid container is the same `.team-grid` (renamed conceptually but the same minmax(440px) behavior fits area cards too — at 1280px max-width = 2 columns).

`.team-grid` is fine as-is for the area page (level 2). For home (level 1) we use the same class — fewer concepts to learn, same look.

### Part 5: Sparkline data

`completion_sparkline` for area cards: chronologically-sorted completion rates of all closed sprints across all teams in the area, cap to last 12. This gives a visual "is this area trending up or down" signal regardless of which specific team contributed.

Renderer: same Chart.js block already in `static/dashboard.js`. The `canvas.sparkline` selector picks up both team-card sparklines (on area page) and area-card sparklines (on home) since they use the same class. No JS change needed.

### Files changed

| File | Action |
|---|---|
| `src/services/home_service.py` | Replace `build_home_context` with `build_workspace_overview` + `build_area_detail` |
| `src/routes/pages.py` | Modify `home` to use overview; add `area_page(space_id)` route; update breadcrumbs in sprint history + sprint detail handlers to include area segment |
| `templates/home.html` | Rewrite for level-1 (workspace banner + area cards) |
| `templates/area.html` | Create — level-2 (area banner + teams grid) |
| `static/style.css` | Add `.area-card` rules |

No new dependencies. No DB migration. No JS change.

### Edge cases

- **Team without space_name** (backfill failed): area card shows "(unassigned)" as the area name. Clicking it goes to `/areas/none` or similar — we'll filter `None`/empty space_id at the route to render an "unassigned" area listing instead. v1 keeps it simple: skip the link entirely if `space_id` is empty.
- **Area with zero teams** (after deleting all): the area disappears from the home grid (since teams drive the grouping). User can't reach `/areas/{space_id}` for an empty area — 404.
- **404 on `/areas/{unknown}`**: HTTPException 404 with a friendly "Product Area not found" page (reuse existing setup template if no friendlier exists; v1 just returns the FastAPI default 404).
- **Direct URL to /areas/{space_id} when not authenticated**: middleware redirects to `/auth/login` like every other protected route.

## Verification

Manual via scry:

1. Restart app. Visit `/`. Expect workspace banner + a single area card "Network Services" with 4 teams, stats inline, sparkline showing completion-rate trend.
2. Click the area card. Lands on `/areas/{space_id}`. Sees area banner + the four team cards (ANI/CNW/LAN/WAN) — same layout as the previous home page.
3. Click "Sprint History" on LAN. Lands on `/teams/{id}/sprints`. Breadcrumb reads `Home / Network Services / LAN`.
4. Click "Network Services" in the breadcrumb. Returns to `/areas/{space_id}`.
5. Click "Home" in the breadcrumb. Returns to `/`.
6. Verify mobile (<720px): area cards stack to single column, breadcrumbs wrap.

## Risk

Low. Pure rearrangement: no DB changes, no auth changes, no API changes. Existing routes for sprint history and sprint detail untouched except for breadcrumb additions.

## Distribution

Standard deploy bundle. Anyone with a bookmark on `/` lands on the new overview. Old direct links to `/teams/{id}/sprints` continue to work.
