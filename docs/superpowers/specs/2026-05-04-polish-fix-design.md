# Polish Fix (Sub-project 4)

## Context

This is the final sub-project of the four-part audit-fix sequence. Sub-projects 1 (bugs), 2 (navigation) and 3 (view-purpose) are shipped. This one polishes the remaining four items, but **one is dropped**: item #22 (Sprint vs Iteration name inconsistency) reflects the user's intentional naming in ClickUp — those are their list names, not a presentation bug. Forcing a single format would erase a meaningful distinction.

That leaves three items.

## Problem

Three small UI rough edges from the audit:

1. **KPI cards trap at ~1024px viewport** — `.kpi-row` is a flex row with 6 cards on a closed sprint detail. At narrow desktop widths (laptop screens around 1024px) the last card ("Behind" STATUS) gets clipped. The existing 480px mobile rule fixes phones; nothing handles tablet/laptop widths.

2. **`Delete Team` placed next to `Save Changes`** — both buttons live in the same `.form-actions` row in `templates/team_settings.html:103-104`. Red destructive action one mis-click away from save. Classic "fat finger" trap.

3. **Scope Changes KPI (`+4 / -1`) lacks tooltip** — the big red number in the scope-changes card on sprint detail tells you the count but not what counts as a "scope change". New users guess.

## Goal

Three small targeted fixes. Each verifiable by scry. After this:

- Closed sprint detail at any desktop width shows all 6 KPI cards without clipping.
- Settings page has a visually distinct "Danger zone" section so Delete is intentional, not adjacent to Save.
- Scope Changes KPI has a one-sentence native browser tooltip explaining what the numbers mean.

## Non-Goals

- **No mobile redesign.** Existing @480px rules stay.
- **No backend changes.**
- **No moving Delete to a separate page** (`/teams/X/danger`). Spec'd as a same-page section, simpler.
- **Skip Sprint/Iteration naming normalization** (audit item #22). Not a defect.

## Design

### Item 20 — KPI cards stack at ≤1280px

`static/style.css` already has:
- Default `.kpi-row { display: flex; flex-wrap: wrap; ... }` (works at 1440px+)
- `@media (max-width: 480px)` block that does 2-column grid

Add a middle breakpoint:

```css
@media (max-width: 1280px) and (min-width: 481px) {
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
}
```

At 481–1280px: 6 cards become 2 rows of 3, fits any laptop comfortably.
At ≥1281px: existing flex-row, 6 cards in one line.
At ≤480px: existing 2-col grid (mobile).

Cascade order: append AFTER the existing 480px block. CSS specificity is identical, so source-order matters — but media queries are mutually exclusive (480/481+ are non-overlapping ranges), so cascade isn't a real concern.

### Item 21 — Delete Team danger zone

In `templates/team_settings.html`:

Current structure (around line 95-110):
```html
<div class="form-actions">
  <button type="submit" class="btn btn-primary">Save Changes</button>
  <a href="..." class="btn btn-secondary">Cancel</a>
  {% if team %}
  <button type="button" class="btn btn-danger" id="delete-btn" style="margin-left:auto;" onclick="deleteTeam(...)">Delete Team</button>
  {% endif %}
</div>
```

New structure:
```html
<div class="form-actions">
  <button type="submit" class="btn btn-primary">Save Changes</button>
  <a href="..." class="btn btn-secondary">Cancel</a>
</div>
{% if team %}
<div class="danger-zone">
  <h4>Danger zone</h4>
  <p>Deleting this team removes all sprint history, snapshots, and scope changes. This cannot be undone.</p>
  <button type="button" class="btn btn-danger" id="delete-btn" onclick="deleteTeam({{ team.id }})">Delete Team</button>
</div>
{% endif %}
```

Plus CSS:
```css
.danger-zone {
  margin-top: 32px;
  padding: 20px;
  border-top: 1px solid #fed7d7;
  border-radius: 0;
  background: #fff5f5;
}
.danger-zone h4 {
  margin: 0 0 8px 0;
  color: #c53030;
  font-size: 15px;
}
.danger-zone p {
  margin: 0 0 12px 0;
  color: #4a5568;
  font-size: 13px;
  line-height: 1.5;
}
```

The existing `confirm()` prompt in `deleteTeam(teamId)` (`team_settings.html:309`) stays — defense in depth.

### Item 23 — Scope Changes tooltip

In `templates/components/kpi_cards.html`, the scope-changes card is around line 12:

```html
<div class="kpi-card" data-filter="scope_changes">
  <div class="value red">+{{ summary.scope_added|default(0) }} / -{{ summary.scope_removed|default(0) }}</div>
  <div class="label">Scope Changes</div>
  <div class="sub">added / removed</div>
</div>
```

Add a `title` attribute:

```html
<div class="kpi-card" data-filter="scope_changes"
     title="Tasks added (+) or removed (−) after the forecast was locked. Counts are independent — added tasks may include items completed before the sprint ended.">
  ...
</div>
```

Native browser tooltip — no JS, no library, no extra CSS. Hover-only (desktop), as-designed.

## Verification (scry)

| Item | Test |
|---|---|
| 20 | `scry.responsive` on `/sprint/8` at widths `[1024, 1280, 1440]` → all KPI cards visible (no `x-overflow` on `.kpi-row` element). At 1024 expect a 3×2 grid; at 1440 expect a single row. |
| 21 | `scry.evaluate` on `/teams/1/settings` → `document.querySelector('.danger-zone')` exists; `.form-actions` contains only Save and Cancel (no Delete inside). |
| 23 | `scry.evaluate` on `/sprint/8` → `.kpi-card[data-filter="scope_changes"]` has `title` attribute containing the words `added` and `removed`. |

## Edge Cases

- **Item 20**: A team that uses `metric_type=task_count` may have only 5 KPI cards (no Unfinished); 5 in a 3-col grid renders fine (last row has 2 cards).
- **Item 21**: New team form (`/teams/new`) — `team` is None, the `{% if team %}` block isn't rendered, so no danger zone shown. Existing behavior preserved.
- **Item 23**: Mobile users don't see tooltips — acceptable per spec.

## Distribution

Three small files change: `static/style.css` (CSS append), `templates/team_settings.html` (re-arrange), `templates/components/kpi_cards.html` (one attribute). No backend, no DB.

## Testing

Manual via the scry verification table.
