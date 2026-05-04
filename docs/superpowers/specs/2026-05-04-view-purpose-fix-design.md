# View Purpose & Messaging Fix (Sub-project 3)

## Context

The audit surfaced seven items where the app communicates the wrong thing — labels that mislead, numbers that confuse, missing helper text, redundant filters. After Sub-projects 1 (bugs) and 2 (navigation), the structural problems are gone; this sub-project polishes what the UI actually says to the user.

One item from the original audit (#15: "no UI to set capacity") was a misread on my part — the capacity table at `templates/components/capacity_table.html` already exists and is included on the planning view of sprint detail. It's just not discoverable from the planning overview's "Available" stat. So #14 and #15 collapse into a single fix.

This spec covers six items. Polish (Sub-project 4) is next.

## Problem

Six things the UI says badly:

1. **`PLANNING` badge** is shown on a sprint that's actually in progress — like "Iteration 1" with start_date in the past. The label is technically correct (forecast not locked) but reads as "the sprint hasn't started yet", which is the opposite of the truth. Users get confused about what state they're in.
2. **`-141.5h Available` rendered in red** when capacity is 0/unset. Looks like the team is overbooked by 141.5 hours; actually it just means capacity hasn't been filled in yet. The user has no path-pointer to "scroll down to set capacity."
3. **Period filter `Last 4 / Last 8 / All`** shows three options on the trends page even when the team has fewer than 4 closed sprints, in which case all three return identical data. Pure clutter for new teams.
4. **Velocity chart** plots most-recent sprint on the left and oldest on the right. Time data conventionally reads left-to-right. Reverse-chronological time-series is jarring.
5. **No help text** under "Metric Type" or "Capacity Mode" radio groups on the team-settings/new-team form. New users have to guess what the values mean.
6. **`🔄 Sync Sprints` button** has no tooltip or hint. New users don't know if it pulls from ClickUp, pushes to ClickUp, or what.

## Goal

Each fix is small, targeted, and verifiable in the running app. After this sub-project:

- Every status badge reads in user-language, not internal-state-language.
- Every "negative number in red" only renders when there's a real problem.
- Every filter only shows options that change the view.
- Every chart reads left-to-right in time.
- Every form value has a one-line explanation visible without hovering.
- Every action button explains what it does.

## Non-Goals

- **No backend status-state changes.** `get_sprint_status()` keeps returning `'planning'`, `'active'`, `'closed'`. Only the *display* changes.
- **No new capacity workflow.** The existing `capacity_table.html` is fine where it is. We just point users to it.
- **No CSS redesign.** Existing classes stay; we add a tiny number of new helper classes.

## Design

### Item 1 — `PLANNING` → `FORECAST` (display only)

`get_sprint_status()` returns the canonical state strings; we don't touch them. We add a Jinja filter that maps state → user-facing label:

```python
def _status_label(state):
    return {"planning": "Forecast", "active": "Active", "closed": "Closed"}.get(state, state)
templates.env.filters["status_label"] = _status_label
```

Then sweep all `{{ status|upper }}` and `{{ sprint.status | upper }}` references and pipe them through `status_label`:

- `templates/sprint_live.html:8`: `<span class="badge badge-{{ status }}">{{ status|upper }}</span>` → `<span class="badge badge-{{ status }}">{{ status|status_label|upper }}</span>`
- `templates/sprint_history.html:42`: same pattern
- `templates/home.html:29`: `<span class="badge-active">ACTIVE</span>` — already correct, no change

CSS classes (`badge-planning`, `badge-active`, `badge-closed`) keep their current names — they're the internal state, not the user label.

Plus the existing rename of `Plan` → `Forecast` on the sprint history row's link button (`templates/sprint_history.html:66`):
- Old: `{% if sprint.status == 'active' %}Live View{% elif sprint.status == 'planning' %}Plan{% else %}Report{% endif %}`
- New: `{% if sprint.status == 'active' %}Live View{% elif sprint.status == 'planning' %}Forecast{% else %}Report{% endif %}`

### Item 2 — `-141.5h Available` when capacity is 0

In `templates/sprint_live.html`, the Planning Overview block has:
```html
<div class="plan-stat">
  <div class="value" id="plan-avail-value">—</div>
  <div class="label">Available</div>
</div>
```

The actual value is computed by JS in `capacity_table.html:159-165` (`updateOverview`). We change the JS to render a hint-string instead of a negative number when `cap === 0`:

```javascript
function updateOverview(cap, assigned) {
  if (!planCapEl) return;
  if (cap === 0) {
    planCapEl.textContent = '—';
    planAvailEl.innerHTML = '<a href="#capacity-panel" style="font-size:13px; color:#4299e1; text-decoration:none;">Set capacity ↓</a>';
    planAvailEl.style.color = '';   // clear red
    return;
  }
  const avail = cap - assigned;
  planCapEl.textContent = fmt(cap) + unit;
  planAvailEl.textContent = fmt(avail) + unit;
  planAvailEl.style.color = avail < 0 ? '#e53e3e' : '#38a169';
}
```

The link `#capacity-panel` exists already (`capacity_table.html:1` has `id="capacity-panel"`), so click-to-scroll works without additional changes.

### Item 3 — Period filter only shows useful options

In `src/routes/pages.py` (the trends route at line ~213), compute `closed_sprint_count` and pass it to the template:

```python
@router.get("/teams/{team_id}/trends", response_class=HTMLResponse)
def team_trends_page(request: Request, team_id: int, range: int = 8):
    team = get_team(team_id)
    from src.services.trend_service import get_team_trends
    trends = get_team_trends(team_id, limit=range if range > 0 else None)
    closed_count = len(trends.get("sprints", []))   # or query the DB directly
    return templates.TemplateResponse("team_trends.html", _ctx(
        request,
        team=team,
        trends=trends,
        range=range,
        closed_count=closed_count,
        breadcrumbs=_breadcrumbs(...),
        team_sub_nav_active="trends",
    ))
```

In `templates/team_trends.html:9-13`, change the filter buttons to:

```jinja
<div class="period-filter">
  {% if closed_count > 4 %}
    <a href="?range=4" class="btn {% if range == 4 %}btn-primary{% else %}btn-secondary{% endif %}">Last 4</a>
  {% endif %}
  {% if closed_count > 8 %}
    <a href="?range=8" class="btn {% if range == 8 %}btn-primary{% else %}btn-secondary{% endif %}">Last 8</a>
  {% endif %}
  <a href="?range=0" class="btn {% if range == 0 %}btn-primary{% else %}btn-secondary{% endif %}">All</a>
</div>
```

Threshold logic:
- ≤4 closed sprints → only `[All]` shown.
- 5–8 → `[Last 4]` + `[All]`.
- >8 → all three.

(`Last 8` only shows if there are more than 8 — same gate.)

### Item 4 — Velocity chart oldest-first

In `templates/team_trends.html:196`, the `sprints` array comes from `trends.sprints` and is currently sorted newest-first. Reverse it for the chart:

```javascript
const sprints = ({{ trends.sprints | tojson }}).slice().reverse();
const labels = sprints.map(s => (s.sprint_name || '').replace(/\s*\([^)]*\)\s*$/, '').trim());
```

(The `.slice()` clones the array so we don't mutate the data used by the table elsewhere on the page.)

This affects the velocity chart, completion rate, and forecast accuracy line charts (they all read from `sprints`). The table at `team_trends.html:140+` keeps newest-first ordering — that's correct for a list (newest at top).

### Item 5 — Help text on Metric Type & Capacity Mode

In `templates/team_settings.html`, find the `<label>Metric Type</label>` block (around line 50-60ish in the existing form) and add a `<small class="help-text">` directly after it:

```html
<label>Metric Type</label>
<small class="help-text">How sprint progress is measured. Task Count = number of tasks done. Story Points = points completed. Hours = hours completed.</small>
<div class="radio-group">
  ... existing radios ...
</div>
```

Same for Capacity Mode:
```html
<label>Capacity Mode</label>
<small class="help-text">Where to track effort capacity. Individual = per team member, set on each sprint. Team = single total per sprint. None = don't track capacity.</small>
```

CSS for `.help-text` (append to `style.css`):
```css
.help-text {
  display: block;
  color: #718096;
  font-size: 12px;
  margin: 4px 0 8px 0;
  line-height: 1.4;
}
```

### Item 6 — Sync Sprints tooltip + clearer label

In `templates/sprint_history.html` (the sync button at line ~10):

```html
<button class="btn btn-primary" id="sync-btn"
        onclick="syncSprints({{ team.id }})"
        title="Pulls all sprint lists from the team's ClickUp folder into this view. Doesn't push anything to ClickUp.">
  🔄 Sync from ClickUp
</button>
```

(Two changes: button text `Sync Sprints` → `Sync from ClickUp`, plus a `title` attribute for native browser tooltip.)

## Verification (scry)

| Item | Scry test |
|---|---|
| 1 | `scry.evaluate` on `/sprint/9` (planning) → assert `.badge`-text is `FORECAST`, NOT `PLANNING` |
| 1 | `scry.evaluate` on `/teams/1/sprints` → assert "Plan" link text is now "Forecast" for planning sprints |
| 2 | `scry.open` on Iteration 1 (planning sprint) → assert `#plan-avail-value` contains an `<a href="#capacity-panel">` link, NOT `-141.5h` |
| 3 | `scry.evaluate` on `/teams/1/trends` → count `.period-filter .btn` — should be 2 (Last 4 + All) since LAN has 3 closed sprints (or 1 if we adjust threshold). Verify against actual closed_count in DB. |
| 4 | `scry.evaluate` on `/teams/1/trends` → assert `Chart.getChart('velocityChart').data.labels[0]` is the *oldest* sprint name (e.g. `Sprint 6`), not the newest (`Sprint 8`) |
| 5 | `scry.evaluate` on `/teams/new` → count `.help-text` elements — should be ≥ 2 |
| 6 | `scry.evaluate` on `/teams/1/sprints` → assert `#sync-btn` has `title` attribute, and button text contains `from ClickUp` |

## Edge Cases

- **Item 1**: status values other than the three known ones — `_status_label` returns the input unchanged (graceful fallback).
- **Item 2**: capacity entered then deleted (set to 0) — falls back to the same hint state, which is correct.
- **Item 3**: a team with exactly 4 closed sprints — `closed_count > 4` is False, so `Last 4` won't show. Acceptable: at exactly 4, `Last 4` and `All` are identical anyway.
- **Item 4**: trends with 0 sprints — `sprints.slice().reverse()` is `[]`, charts render empty (existing behavior).
- **Item 6**: `title` attribute is desktop-only; mobile users don't see tooltips. Acceptable — this is an advanced feature for desktop power-users.

## Distribution

Six files change: `src/routes/pages.py`, four templates, plus a CSS append. No DB changes. No new dependencies. Bundle deploys via the normal cycle.

## Testing

Manual via the scry verification table above. No automated tests — same reasoning as Sub-projects 1 and 2: these are presentation-layer changes whose correctness is best verified by looking at the rendered page.
