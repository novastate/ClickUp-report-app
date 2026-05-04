# Navigation & Breadcrumbs Fix (Sub-project 2)

## Context

The audit found seven navigation problems in Sprint Reporter. The current top nav is a single flat row (`Home | ANI | CNW | LAN | WAN | + New Team`) with no contextual cues — once you click into a team, you can't tell *where* in the team you are, and going back relies on ad-hoc "← Sprint History" links scattered across detail pages. This sub-project introduces a standard hierarchical pattern (top bar + breadcrumbs + contextual sub-nav) that solves all seven items in one coherent change.

This is Sub-project 2 of the four-part audit-fix sequence. Sub-project 1 (bugs) is shipped. View-purpose (3) and polish (4) come next.

## Problem

Seven navigation issues from the audit:

1. **No breadcrumbs anywhere** — the only "where am I" cue is the page header.
2. **Top nav lists only teams** — once you're in `/teams/1/sprints`, nothing tells you whether you're looking at history, trends, or settings until you read the page heading.
3. **Settings has no "← Back to LAN"** — Cancel/Save go somewhere implicitly but the path back is invisible.
4. **New Team has no Cancel target visible**.
5. **`← Sprint History`** lives in the upper-right corner of sprint detail pages — opposite to the conventional left-side back placement.
6. **`+ New Team` appears twice on home** — once in the top nav, once at the bottom of the team list.
7. **No way to jump between adjacent sprints in the same team** — to go from Sprint 8 to Sprint 7 you must go back to Sprint History and click again.

## Goal

A standard three-row top section (identity bar / breadcrumbs / sub-nav) that makes the user's location explicit and one-click reachable from anywhere. After this:

- Every page below the home shows breadcrumbs from `Home` to the current page, with every prior level clickable.
- Inside any team-context page, a sub-nav makes the three sibling sections (Sprint History / Trends / Settings) one click away with the active tab marked.
- Sprint detail pages have prev/next sprint navigation, eliminating the "back to history → click next sprint" round-trip.
- Duplicated `+ New Team` is consolidated to a single location.

## Non-Goals

- **No team-switcher dropdown** in the top bar. Going from one team to another routes through Home. (V2 if needed.)
- **No active-sprint shortcut** in nav. Home already surfaces it on the team card.
- **No global search / spotlight.**
- **No client-side routing or SPA-ification.** Stay on the current FastAPI + Jinja server-rendered architecture.

## Design

### Three-row layout

Replace the current single `<nav>` in `templates/base.html` with a three-row top section. Rows 2 and 3 are conditional (only render when the page passes the right context).

```
Row 1: Identity bar      ← always
  Sprint Reporter                               + New Team

Row 2: Breadcrumbs       ← conditional (skipped on /)
  Home  ›  LAN  ›  Sprint 8

Row 3: Team sub-nav      ← conditional (only inside team-context)
  [ Sprint History ]   [ Trends ]   [ Settings ]
```

### Component breakdown

| File | Action | Responsibility |
|------|--------|----------------|
| `templates/base.html` | Modify | Replace flat `<nav>` with three sections, render breadcrumbs/sub-nav from blocks. |
| `templates/components/breadcrumbs.html` | Create | Render a list of `(label, href)` tuples with `›` separators; last entry is plain text (you-are-here). |
| `templates/components/team_sub_nav.html` | Create | Render three tabs (Sprint History / Trends / Settings) with the `active` one marked. Takes `team` and `active` as parameters. |
| `src/routes/pages.py` | Modify | Add a `_breadcrumbs(...)` helper and pass `breadcrumbs` + `team_sub_nav_active` (where applicable) into every template context via the existing `_ctx` helper. |
| `templates/sprint_report.html`, `templates/sprint_live.html` | Modify | Remove the `← Sprint History` button from the top-bar; add prev/next sprint links to the same area. |
| `templates/home.html` | Modify | Remove the duplicate `+ New Team` button at the bottom (the top-bar one stays). |
| `static/style.css` | Modify | Add styles for `.top-bar` (identity), `.breadcrumbs`, `.team-sub-nav`, `.team-sub-nav .tab`, `.team-sub-nav .tab.active`, `.sprint-nav` (prev/next). |

### Identity bar (Row 1)

```html
<header class="identity-bar">
  <a href="/" class="brand">Sprint Reporter</a>
  <a href="/teams/new" class="btn btn-primary">+ New Team</a>
</header>
```

The current team-list (`Home | ANI | CNW | LAN | WAN`) **is removed**. Users navigate to a team by clicking its card on Home. Rationale: with sub-nav inside teams plus breadcrumbs, the team-list link in top nav is a redundant third path that creates clutter and offers no contextual cue when you're already inside one.

### Breadcrumbs (Row 2)

`templates/components/breadcrumbs.html`:
```jinja
{% if breadcrumbs %}
<nav class="breadcrumbs" aria-label="breadcrumb">
  {% for crumb in breadcrumbs %}
    {% if not loop.last %}
      <a href="{{ crumb.href }}">{{ crumb.label }}</a>
      <span class="separator">›</span>
    {% else %}
      <span class="current">{{ crumb.label }}</span>
    {% endif %}
  {% endfor %}
</nav>
{% endif %}
```

Routes pass a `breadcrumbs` list. Examples:

| Route | Breadcrumbs |
|---|---|
| `/` | (none — empty list) |
| `/teams/new` | `Home › New Team` |
| `/teams/1/sprints` | `Home › LAN` |
| `/teams/1/trends` | `Home › LAN › Trends` |
| `/teams/1/settings` | `Home › LAN › Settings` |
| `/sprint/8` | `Home › LAN › Sprint 8` |

Note: `/teams/1/sprints` is treated as the team's "home" — its breadcrumb terminates at the team name (not at "Sprint History" again). Trends and Settings are explicitly nested *under* the team. This matches how a user thinks: "I'm at LAN's main page" vs "I'm in LAN's Trends section".

### Team sub-nav (Row 3)

`templates/components/team_sub_nav.html`:
```jinja
{% if team and team_sub_nav_active %}
<nav class="team-sub-nav">
  <a href="/teams/{{ team.id }}/sprints" class="tab {% if team_sub_nav_active == 'sprints' %}active{% endif %}">Sprint History</a>
  <a href="/teams/{{ team.id }}/trends" class="tab {% if team_sub_nav_active == 'trends' %}active{% endif %}">Trends</a>
  <a href="/teams/{{ team.id }}/settings" class="tab {% if team_sub_nav_active == 'settings' %}active{% endif %}">Settings</a>
</nav>
{% endif %}
```

Active values per route:

| Route | `team_sub_nav_active` |
|---|---|
| `/teams/X/sprints` | `'sprints'` |
| `/teams/X/trends` | `'trends'` |
| `/teams/X/settings` | `'settings'` |
| `/sprint/X` | `'sprints'` (sprint detail belongs under the History tab) |
| `/`, `/teams/new` | (not set — sub-nav not rendered) |

### Prev/Next sprint (replaces `← Sprint History`)

In sprint detail pages (`sprint_report.html` and `sprint_live.html`), the top-right action area currently has:

```html
<a href="/teams/{{ team.id }}/sprints" class="btn btn-secondary">← Sprint History</a>
```

Replace with:

```html
<div class="sprint-nav">
  {% if prev_sprint %}
    <a href="/sprint/{{ prev_sprint.id }}" class="btn btn-secondary">← {{ prev_sprint.name|display_name }}</a>
  {% else %}
    <span class="btn btn-secondary disabled" aria-disabled="true">← Earlier</span>
  {% endif %}
  {% if next_sprint %}
    <a href="/sprint/{{ next_sprint.id }}" class="btn btn-secondary">{{ next_sprint.name|display_name }} →</a>
  {% else %}
    <span class="btn btn-secondary disabled" aria-disabled="true">Later →</span>
  {% endif %}
</div>
```

The route handler at `src/routes/pages.py` (sprint detail handler at line 93) computes `prev_sprint` and `next_sprint` by querying sprints in the same team ordered by `start_date`. Returns `None` for both if no neighbor exists.

The user can still get back to history via the breadcrumb (`LAN`), so removing the explicit `← Sprint History` button is safe.

### `+ New Team` deduplication

`templates/home.html` currently renders `+ New Team` at line ~36 (bottom of team list). Remove that block; the identity-bar version is always present.

### `_breadcrumbs` helper

In `src/routes/pages.py`, add a helper:

```python
def _breadcrumbs(*pairs):
    """Build a breadcrumbs list. Each pair is (label, href). Pass None as href for the last (current) entry."""
    return [{"label": label, "href": href} for label, href in pairs]
```

Each route handler builds its own breadcrumbs and adds them to the template context. Examples:

```python
# /teams/X/sprints
breadcrumbs = _breadcrumbs(("Home", "/"), (team["name"], None))
team_sub_nav_active = "sprints"

# /sprint/X
breadcrumbs = _breadcrumbs(
    ("Home", "/"),
    (team["name"], f"/teams/{team['id']}/sprints"),
    (display_name(sprint["name"]), None),
)
team_sub_nav_active = "sprints"
```

The `_ctx(...)` helper passes both into every template via kwargs, so all templates have `breadcrumbs` and `team_sub_nav_active` available without each handler doing it manually. We extend `_ctx` to accept these as parameters with sensible defaults (`breadcrumbs=[]`, `team_sub_nav_active=None`).

### Mobile behavior

Building on the @480px CSS from Sub-project 1:

- Identity bar: `+ New Team` becomes `+` (icon-only) under 480px to save space.
- Breadcrumbs: middle levels truncate with `…` if total width exceeds container (`Home › … › Sprint 8`). Implementation: CSS `text-overflow: ellipsis` on middle items, plus a max-width on each crumb.
- Team sub-nav: scrolls horizontally if it doesn't fit (`overflow-x: auto`).
- Sprint nav (prev/next): stack vertically on mobile, full-width buttons.

## Verification (scry)

| Item | Scry test |
|---|---|
| Top bar identity | `scry.evaluate` on `/`, assert nav contains `Sprint Reporter` and `+ New Team`, does NOT contain `ANI`/`CNW`/`LAN`/`WAN` as top-nav links |
| Breadcrumbs render | Visit each route, evaluate `.breadcrumbs` content, assert correct labels in correct order |
| Breadcrumb links navigate | scry.click on a non-last breadcrumb (e.g. `LAN` from `/sprint/8`), assert URL changes to `/teams/1/sprints` |
| Sub-nav active state | On `/teams/1/trends`, evaluate `.team-sub-nav .tab.active`, assert label is `Trends` |
| Sub-nav cross-section | scry.click `Settings` from `/teams/1/sprints`, assert URL `/teams/1/settings`, assert active tab is `Settings` |
| Sprint detail belongs to History | On `/sprint/8`, assert active tab is `Sprint History` |
| Prev sprint | On `/sprint/8`, scry.click `← Sprint 7`, assert URL `/sprint/7` |
| Disabled prev | On the *earliest* sprint, the `← Earlier` element exists with `aria-disabled="true"` |
| `+ New Team` dedup | On `/`, count elements with text `+ New Team` — should be 1, not 2 |
| Mobile responsive | scry.responsive at 360px on `/`, `/teams/1/sprints`, `/sprint/8` — issueCount stays 0/no page-overflow |

## Edge Cases

- **Team has only one sprint** → both prev and next are disabled, both rendered as inert spans.
- **Team has no sprints** → user can't reach a sprint detail page, so no prev/next concern.
- **Breadcrumb labels with parens** in old DB rows (already addressed in sub-project 1 by display_name filter — we apply it to breadcrumb sprint labels too).
- **Breadcrumb truncation order** at narrow widths: keep first (`Home`), keep last (current), truncate middles. Standard ellipsis-from-middle pattern.
- **Removing the team-list from top nav**: users with bookmarks to specific team pages still work (URLs unchanged). Discoverability via Home is the new path.

## Distribution

Six files change: `base.html`, two new component templates, `pages.py`, two sprint detail templates, `home.html`, `style.css`. All ride along on the next deploy bundle. No backend logic changes beyond the breadcrumb-builder helper. No DB migration.

## Testing

Manual via the scry verification table above. No new automated tests — these are layout/rendering changes whose correctness is best confirmed by clicking through the running app, which is what scry is for.
