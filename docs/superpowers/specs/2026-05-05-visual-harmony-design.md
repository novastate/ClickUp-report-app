# Visual Harmony Fix

## Context

A user-supplied screenshot of `/teams/X/sprints` revealed three UX issues we missed in the four-sub-project audit-fix sequence:

1. **Two stacked dark headers** — the new identity bar (Sub-project 2) plus the original `.top-bar` (kept from before) make every page below Home look like four separate panels stacked. Visual rhythm broken.
2. **Duplicate Settings link** — the original `.top-bar` has a `⚙ Settings` button on team-context pages, and the sub-nav (Sub-project 2) now also has a Settings tab. Same destination, two clickable spots.
3. **`btn-light` action buttons are invisible** — the per-row "Forecast" / "Plan" / "Report" links in the Sprint History table use `btn-light`, which renders so light against white that they look disabled.

Sub-project 4 (polish) was supposed to catch this kind of thing but the audit didn't include "look at full pages and judge visual coherence" — it was item-by-item. Lesson noted; this spec fixes what we missed.

## Problem

Every page under Home (`sprint_history.html`, `team_trends.html`, `sprint_report.html`, `sprint_live.html`) has the same shape:

```
[ identity bar — dark ]
[ breadcrumbs    — light ]
[ team sub-nav   — light ]
[ .top-bar       — DARK AGAIN — h1 + meta + actions ]
[ content        — light ]
```

Plus `home.html` also has a `.top-bar` containing `<h1>Sprint Reporter</h1>` — but the identity bar already shows "Sprint Reporter" as the brand link. Pure duplication on home.

## Goal

One dark band per page (identity bar), then light hierarchy below it. Specifically:

- Replace `.top-bar` on the four team-context pages with a light `.page-header` that contains the same h1 + meta + action buttons but on light background, visually unified with breadcrumbs and sub-nav.
- Remove `.top-bar` from `home.html` entirely (Sprint Reporter is in the identity bar; home doesn't need a second h1).
- Remove the duplicate `⚙ Settings` button from `sprint_history.html`'s actions area (sub-nav has it).
- Migrate the table-row action buttons from `btn-light` to `btn-secondary` (visible mid-tier styling).
- Drop `.btn-light` from CSS (last user gone).

## Non-Goals

- No redesign of identity bar, breadcrumbs, sub-nav (Sub-project 2 work stays).
- No new color palette, typography, or spacing system. Just consistent application of what exists.
- No changes to dashboard.js, route handlers, or backend.

## Design

### Page-header (replaces `.top-bar` on 4 templates)

A light, simpler header band that lives directly under the team sub-nav. Same content slots (h1 + optional meta + optional actions) but on light background and slimmer padding so it doesn't fight breadcrumbs/sub-nav for visual weight.

```html
<header class="page-header">
  <div class="title">
    <h1>{{ team.name }}</h1>
    <span class="meta">Sprint History</span>
  </div>
  <div class="actions">
    <button ...>🔄 Sync from ClickUp</button>
  </div>
</header>
```

CSS (added to `static/style.css`):

```css
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #edf2f7;
}
.page-header h1 {
  margin: 0;
  font-size: 1.4rem;
  color: #1a202c;
}
.page-header .title { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-header .meta {
  color: #718096;
  font-size: 13px;
}
.page-header .actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
```

The four templates each get their `<div class="top-bar">...</div>` block converted to `<header class="page-header">...</header>` with internal structure adjusted (the `<div class="title">` wrapper is new, replacing the bare `<div>` previously used).

### Per-page changes

**`templates/sprint_history.html`** — old `.top-bar`:
```html
<div class="top-bar">
  <div>
    <h1>{{ team.name }}</h1>
    <span class="meta">Sprint History</span>
  </div>
  <div class="actions">
    <button class="btn btn-primary" id="sync-btn" ...>🔄 Sync from ClickUp</button>
    <a href="/teams/{{ team.id }}/settings" class="btn btn-secondary">⚙ Settings</a>
  </div>
</div>
```

→ new `.page-header` (drops the duplicate `⚙ Settings` link):
```html
<header class="page-header">
  <div class="title">
    <h1>{{ team.name }}</h1>
    <span class="meta">Sprint History</span>
  </div>
  <div class="actions">
    <button class="btn btn-primary" id="sync-btn" title="..." onclick="syncSprints({{ team.id }})">🔄 Sync from ClickUp</button>
  </div>
</header>
```

**`templates/team_trends.html`** — old `.top-bar` has period-filter buttons + `← Sprint History`. Period filter stays (it's contextual to trends), but the `← Sprint History` link is now redundant (sub-nav has it). Drop it. Convert wrapper to `.page-header`.

**`templates/sprint_report.html`** — old `.top-bar` has h1 + dates + CLOSED badge + `.sprint-nav` (prev/next from Sub-project 2). All stays, just wrapper changes.

**`templates/sprint_live.html`** — old `.top-bar` has h1 + dates + status badge + actions (refresh/close-forecast/close-sprint + sprint-nav). All stays, wrapper changes.

**`templates/home.html`** — old `.top-bar`:
```html
<div class="top-bar">
  <div>
    <h1 style="display:inline">Sprint Reporter</h1>
  </div>
</div>
```

→ removed entirely. The identity bar already shows "Sprint Reporter".

### `btn-light` migration

Find: `templates/sprint_history.html:66` uses `btn-light` for the per-row action link (Forecast/Report). Change `btn-light` → `btn-secondary`.

After this change, `.btn-light` has no users left in templates. Remove the class from `static/style.css` (lines 121-122) — dead CSS.

### CSS cleanup of `.top-bar`

Once all five templates are migrated and `.top-bar` is no longer referenced, remove the `.top-bar`, `.top-bar h1`, `.top-bar .meta`, `.top-bar .actions` rules from `static/style.css` (lines ~62-91). Dead CSS.

## Verification (scry)

For each of the four team-context pages:
- Snapshot at 1440px width.
- Assert exactly ONE element with `background: rgb(26, 32, 44)` (the dark identity bar) — no second dark band.
- Assert `.page-header` element exists.
- Assert `.top-bar` does NOT exist anywhere in the DOM.

For sprint_history specifically:
- `document.querySelectorAll('.page-header [href*="/settings"]').length === 0` (no duplicate Settings link).
- `document.querySelectorAll('.btn-light').length === 0` (gone).
- Per-row action links should have computed `background-color` matching `.btn-secondary` (not the light grey).

For home:
- No `.top-bar` and no `.page-header` (home doesn't need one — content panels handle their own headings).

## Distribution

Six files change: 5 templates + style.css. No backend, no DB. Bundle deploys normally.
