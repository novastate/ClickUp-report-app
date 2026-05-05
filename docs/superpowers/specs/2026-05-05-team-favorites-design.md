# Per-User Team Favorites

## Context

The app has a 3-level hierarchy: Workspace (`/`) → Product Area (`/areas/{space_id}`) → Team (`/teams/{id}/sprints`). Users navigate to a team via two clicks. For a colleague who works primarily with the same 1-2 teams every day, that two-click path becomes friction.

This initiative adds per-user favorites: any user can ★ a Product Team to surface it directly on the home page. The starred teams render in a "★ Your Favorites" section above the Product Areas grid, with the full team-card detail (sparkline, last sprint, action buttons) — same layout as on the area page, just promoted to level-1.

The areas-overview spec (2026-05-05-areas-overview-design.md) reserved a slot for this section explicitly. We're now filling it.

## Problem

1. **Repeat navigation cost.** A user whose work centers on the LAN team in Network Services clicks Home → Network Services → LAN every time. Two clicks per session.
2. **No per-user customization.** The home page is identical for every authenticated user, regardless of their actual focus. A 30-team workspace surfaces all 30 with no signal of which ones matter to a given user.
3. **Hidden teams.** When a user has 5+ favorite teams scattered across multiple Product Areas, today they'd switch areas to find each one. Favorites collapses that into one section.

## Goal

After this initiative:

1. A user can click a ★ icon on any team card (on the area page) to mark it as a favorite. Toggling is instant via a fetch call, no page reload.
2. The home page shows a **"★ Your Favorites"** section between the workspace banner and the Product Areas grid, listing the user's starred teams as full team cards.
3. The favorites section is hidden when the user has zero favorites — no empty placeholder, no "tip" text.
4. Favorites are scoped to the authenticated user's `id` (`users.id` from the OAuth session). With AUTH_BYPASS the dev user `dev_bypass` keeps their own favorites — testable locally.

## Non-Goals

- **No drag-reorder, manual sort, or pin-to-top.** Order is alphabetical by team name. Adding sorting later is additive.
- **No favorites at the Product Area level.** Only Product Teams are favoritable. If users want a "shortcut to an area", that's a separate feature (and probably better solved by reducing the area-card click path).
- **No favorite-driven notifications.** No badges, alerts, or counts based on favorited teams.
- **No team-level favorites shared across users.** Per-user only.
- **No bulk operations.** No "favorite all teams in this area", no "clear all favorites".
- **No undo / confirm dialogs.** Click is committal — re-click un-favorites.
- **No "recently viewed" / activity-based suggestions.** We could surface "teams you visit most" later; not in scope.
- **No mobile-specific affordances beyond the existing card stacking.** The ★ button is the same size and position on every viewport.

## Design

### Part 1: Schema

One new table:

```sql
CREATE TABLE IF NOT EXISTS user_favorites (
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  team_id    INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_user_favorites_user ON user_favorites(user_id);
```

Added inside `init_db()`'s `executescript` block alongside the existing `CREATE TABLE`s. No migration needed for existing data — table is empty until users start clicking ★.

CASCADE on both FKs ensures favorites are cleaned up when a user is removed (token revoked / OAuth account deleted) or a team is deleted from the app.

### Part 2: Service module

`src/services/favorites_service.py` (new):

```python
def toggle_favorite(user_id: str, team_id: int) -> bool:
    """Toggle a favorite. Returns True if now favorited, False if un-favorited."""

def get_favorite_team_ids(user_id: str) -> set[int]:
    """Return the set of team IDs the user has favorited.
    Used to mark cards on the area page (so we can render filled vs empty stars)."""

def get_favorited_teams(user_id: str) -> list[dict]:
    """Return the user's favorited teams as full team rows (joined against teams).
    Filtered to teams that still exist (CASCADE handles deletes; this is just a SELECT)."""
```

All three are sync — they're single-table SQLite operations, fast enough not to need async. No ClickUp API involvement.

### Part 3: Toggle route

`POST /teams/{team_id}/favorite` in `src/routes/teams.py`. Requires `get_current_user`. Calls `toggle_favorite(user.id, team_id)`. Returns:

```json
{"favorited": true}    // or false
```

The route does not return the updated team list or trigger any cache invalidation. Frontend updates locally.

If `team_id` doesn't exist (404) or the user lacks access (the team isn't in their active workspace), return 404. The body is the simplest possible — frontend reads `favorited` and updates the icon.

### Part 4: Home page changes

`src/services/home_service.py::build_workspace_overview` gains a new parameter:

```python
async def build_workspace_overview(client, teams, user_id: str) -> dict
```

Returns the existing `{workspace, areas}` plus a new `favorites` key:

```python
{
  "workspace": {...},
  "favorites": [<team_card>, ...],   # may be empty list
  "areas": [...],
}
```

`favorites` is the result of `get_favorited_teams(user_id)` filtered to teams in the user's `_scoped_teams(request)` list (so favorites in another workspace, if that ever happens via workspace switching, don't bleed over), then mapped through `_team_card(team)`.

`templates/home.html` gets a new conditional section between the workspace banner and the area-card grid:

```html
{% if favorites %}
<section class="favorites-section">
  <header class="favorites-header">
    <h2 class="favorites-title">★ Your Favorites</h2>
    <span class="favorites-count">{{ favorites | length }} team{{ 's' if favorites|length != 1 else '' }}</span>
  </header>
  <div class="team-grid">
    {% for team in favorites %}
      {# same team-card markup as area.html, plus filled ★ #}
    {% endfor %}
  </div>
</section>
{% endif %}
```

When `favorites` is empty, the section is hidden entirely.

### Part 5: ★ button on team cards

`templates/area.html` (and the new home favorites section) renders a star button in the top-right of each team card. The button shows ★ filled when favorited, ☆ outline when not. The state is determined server-side at render time; clicks call the toggle endpoint and flip the icon locally.

Markup added inside `.team-card`:

```html
<button class="favorite-btn"
        data-team-id="{{ team.id }}"
        data-favorited="{{ 'true' if team.is_favorite else 'false' }}"
        aria-label="Toggle favorite"
        title="{% if team.is_favorite %}Unfavorite{% else %}Favorite{% endif %}">
  {% if team.is_favorite %}★{% else %}☆{% endif %}
</button>
```

The CSS positions the button absolute top-right of the card; the card gets `position: relative`. Filled state uses `var(--accent)` (purple); unfilled is muted gray with hover that brightens.

`is_favorite` is a new boolean on the `_team_card` payload, populated by `home_service` based on `get_favorite_team_ids(user_id)`. The team card builder gets the same new `user_id` parameter:

```python
def _team_card(team: dict, favorite_ids: set[int]) -> dict:
    ...
    return {..., "is_favorite": team["id"] in favorite_ids}
```

Both `build_workspace_overview` and `build_area_detail` call `get_favorite_team_ids(user_id)` once and pass the set into `_team_card` for each team.

### Part 6: Frontend toggle JS

A small block in `static/dashboard.js` listens for clicks on `.favorite-btn`:

```javascript
document.addEventListener('click', async function(e) {
  const btn = e.target.closest('.favorite-btn');
  if (!btn) return;
  e.preventDefault();
  const teamId = btn.dataset.teamId;
  const resp = await fetch(`/teams/${teamId}/favorite`, {method: 'POST'});
  if (!resp.ok) {
    showToast('Could not update favorite', 'error');
    return;
  }
  const {favorited} = await resp.json();
  btn.dataset.favorited = String(favorited);
  btn.textContent = favorited ? '★' : '☆';
  btn.title = favorited ? 'Unfavorite' : 'Favorite';
});
```

Uses event delegation on document so the handler works for both home favorites and area-page cards without re-binding after dynamic changes. Uses the existing `showToast` helper for error feedback.

The favorites section on the home page is **not** dynamically updated when the user un-favorites from there — the un-favorited card disappears only on next page load. Reason: keeping the JS minimal and avoiding the awkward "card animates out from under your cursor" feel. v2 can add fade-out if user testing surfaces friction.

### Part 7: Routes & access control

`POST /teams/{team_id}/favorite`:

- Auth required (`Depends(get_current_user)`).
- Verifies team exists via `team_service.get_team(team_id)`. Returns 404 if missing.
- Verifies team is in the user's scoped teams (workspace check). Returns 404 if not.
- Toggles the favorite, returns `{favorited: bool}`.

The workspace check is straightforward: `team["workspace_id"] == request.state.active_workspace_id`. If that mismatches, 404 (not 403, to avoid leaking team-existence across workspaces).

### Files changed

| File | Action |
|---|---|
| `src/database.py` | Add `user_favorites` table + index inside `init_db` |
| `src/services/favorites_service.py` | Create — `toggle_favorite`, `get_favorite_team_ids`, `get_favorited_teams` |
| `src/services/home_service.py` | Modify — `build_workspace_overview` and `build_area_detail` accept `user_id`, pass favorite_ids into `_team_card`. Add `favorites` key to overview return. |
| `src/routes/teams.py` | Add `POST /{team_id}/favorite` route |
| `src/routes/pages.py` | Modify `home` and `area_page` to pass `user["id"]` into the home_service calls |
| `templates/home.html` | Add `{% if favorites %}` section above the area grid |
| `templates/area.html` | Add ★ button to each team card |
| `static/style.css` | `.favorite-btn`, `.favorites-section`, `.favorites-header` rules |
| `static/dashboard.js` | Append click delegator that POSTs and updates the icon |

Cache version bump `v=9` → `v=10` in the 3 templates that load `style.css`.

No new dependencies. No new env vars.

### Edge cases

- **AUTH_BYPASS dev user toggles favorite.** Persists under `user_id="dev_bypass"` — same as any user. Safe.
- **User favorites a team, then admin deletes the team.** CASCADE removes the favorite row. Home page re-renders without it on next load.
- **User logs out and back in.** Session changes but `user_id` is stable (it's `users.id` = ClickUp user_id). Favorites survive.
- **Two browser tabs.** Click ★ in tab A, refresh tab B → tab B sees the new state on next render. Fine.
- **Click rate-limit / spam.** No protection. Worst case the user toggles 100×/sec and writes 100 rows to a 2-column index — negligible. v2 can add debouncing if needed.
- **Network failure on toggle.** Toast shows error; icon doesn't flip. User can retry. The DB never reaches a half-state because each call is a single atomic INSERT-or-DELETE.

## Verification

Manual via scry:

1. From a fresh DB state, visit `/`. Verify no Favorites section is rendered (zero favorites).
2. Click area card → land on `/areas/{space_id}`. Verify ★ button (outline) on each of LAN, ANI, CNW, WAN cards.
3. Click ★ on LAN. Icon flips to filled ★. Tail `app.log` — no errors. DB query: `sqlite3 sprint_data.db "SELECT * FROM user_favorites"` — one row with `user_id="dev_bypass"`, `team_id=<LAN's id>`.
4. Click ★ on WAN. Now two rows in DB.
5. Navigate to `/`. Favorites section appears with two cards (LAN, WAN), full sparkline + last-sprint preview, ★ filled.
6. Click ★ on LAN from home. Icon flips to ☆. DB row deleted. Card stays visible until next page load (intentional per spec).
7. Reload `/`. LAN card now gone from favorites; only WAN remains.
8. Click ★ on WAN to clear. Reload. Favorites section disappears.

## Risk

Low. Additive table (no migration), one new route, one new service module, two template tweaks, one CSS block, one JS handler. No changes to auth, OAuth, ClickUp client, snapshot job, or any other existing flow. Rollback = drop the table and revert the templates.

## Distribution

Standard deploy bundle. The `user_favorites` table is created automatically on first boot via `init_db()`. New cache bump (`v=10`) ensures the new CSS + JS load.
