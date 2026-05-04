# Audit Bugs Fix (Sub-project 1)

## Context

A scry-driven audit of Sprint Reporter surfaced 23 issues across four categories: bugs, navigation, view-purpose, and polish. We split the work into four sub-projects to keep each iteration tight and verifiable. **This spec covers Sub-project 1 — the five concrete bugs.** Navigation, view-purpose, and polish each get their own spec next.

The bugs were found by driving the live app at `http://localhost:8000` with the scry MCP plugin: opening pages, calling `scry.probe`, taking screenshots, and checking `consoleErrors`. All five reproduce reliably.

## Problem

Five bugs in the running app:

1. **`Day None of 14`** appears under the STATUS card on closed sprint detail pages. The intent of "Day X of N" is for in-progress sprints; for a closed sprint the value is meaningless and renders the literal string `None`.
2. **Burndown chart stops at Day 6** even though the sprint is 14 days long. The cause is missing daily_progress rows for Day 7–14 (snapshots stopped before the sprint ended). Today the chart silently shows a stunted X-axis, leaving the user unsure whether the sprint was 6 days long or whether data is missing.
3. **Inconsistent date format inside sprint names** — `Sprint 8 (4/6 - 4/19)` is M/D, `Iteration 1 (4/5 - 17/5)` is D/M. The names come from ClickUp lists and we can't control how users format them there. Sprint history already has a separate DATES column with ISO dates, so the parenthetical is redundant *and* inconsistent.
4. **Mobile layout (360px) is broken.** `scry.responsive` reported 8 issues at 360px — page overflow plus seven `x-overflow` warnings on `nav`, `.content`, `.grid-2`, and three `.panel` elements. The sprint detail page in particular requires horizontal scrolling.
5. **Sync Sprints has zero visible feedback.** Backend already returns `{synced: N, sprints: [...]}`; frontend ignores it and runs `location.reload()`. User has no way to know whether sync succeeded, what was added, or whether nothing changed.

## Goal

Five small, verifiable fixes that close the bugs without introducing scope creep. Each fix is verified by re-running the same scry scenario that found the bug, and the verification result is part of the task itself.

## Non-Goals

- The four navigation, view-purpose, and polish issues from the audit are out of scope here. Each gets its own spec.
- We do not change the underlying daily_progress capture logic (Bug 2 is purely a presentation fix). If the user wants a robust scheduler that catches up on missed days, that's a separate piece of work.
- We do not normalize sprint names in the database. Bug 3 is a presentation fix.
- We do not redesign the toast/notification system into a full framework. We add the smallest helper that solves Bug 5 and is reusable for the other three buttons (`Refresh`, `Close Forecast`, `Close Sprint`) that share the same pattern.

## Design

### Bug 1 — Closed sprints show "Day None of 14"

**File:** `templates/components/kpi_cards.html:33`

Problem: `{{ sprint_day|default('?') }}` only fires for *undefined* in Jinja2; passing `None` from the route handler renders the literal string `None`. And anyway, a closed sprint shouldn't show "Day X of N" — that label is for an in-progress sprint.

Fix: replace the line with a three-way branch.

```jinja
<div class="sub">
  {% if sprint.closed_at %}Closed
  {% elif sprint_day is none %}Not started
  {% else %}Day {{ sprint_day }} of {{ team.sprint_length_days }}
  {% endif %}
</div>
```

`sprint` is already in the template context (the surrounding `kpi_cards.html` uses `{{ summary.* }}`, but the parent template has `sprint` available — we'll pass it in as a parameter to `{% include "components/kpi_cards.html" %}` if it isn't already, and verify in the implementation).

### Bug 2 — Burndown axis stops at Day 6 instead of sprint length

**File:** `templates/components/burndown_chart.html`

The chart is rendered with Chart.js (or similar) using labels generated from the data. We need:

1. The X-axis labels to always run `Day 0 .. Day {{ team.sprint_length_days }}` regardless of how many actual data rows exist.
2. The actual data line to plot only the available points (so it visibly stops at Day 6 rather than being interpolated).
3. A small caption under the chart, shown only when the sprint is closed AND the last data day < sprint_length_days:
   `Last snapshot: Day {{ last_data_day }}. No data captured for the remaining days.`

Implementation will read the existing chart-rendering JS (we know it uses an `idealLabels.push('Day ' + i)` loop — line 15 of the component). The fix extends that loop to `team.sprint_length_days` and ensures the actual-data dataset can be shorter than the labels.

### Bug 3 — Date format inconsistent inside sprint names

**File:** `app.py` (Jinja env setup), all templates that render `sprint.name`.

The names live in ClickUp; we keep them as-is in the DB. The fix is presentational: register a Jinja filter `display_name` that strips a trailing `(…)` block from the name.

```python
import re
def display_name(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip() if name else name
app.jinja_env.filters["display_name"] = display_name
```

Then change every `{{ sprint.name }}` (and `{{ s.sprint_name }}` in `team_trends.html`) to `{{ sprint.name|display_name }}`.

A grep in implementation will find every occurrence (we've already counted ~10). Safer than rewriting the DB.

**Edge cases:**
- `"Sprint 8 (4/6 - 4/19)"` → `"Sprint 8"` ✓
- `"Iteration 1 (4/5 - 17/5)"` → `"Iteration 1"` ✓
- `"Q3 (refactor) sprint"` (parens not at end) → unchanged ✓
- `"Sprint 8"` (no parens) → unchanged ✓
- `None` / empty → unchanged ✓

### Bug 4 — Mobile (360px) overflow

**File:** `static/style.css`

The file has a `@media (max-width: 768px)` block at line 244 but nothing tighter. We add a `@media (max-width: 480px)` block that handles:

1. **KPI row** (`.kpi-row`): switch from horizontal flex to a 2-column grid. KPI-cards keep size, just wrap.
2. **Top nav**: `overflow-x: auto` + `white-space: nowrap` on the nav list so team names scroll horizontally instead of overflowing the page.
3. **`.grid-2`** (Burndown + Scope Changes side-by-side): collapse to a single column.
4. **`.panel`** elements: smaller padding, ensure `width: 100%; box-sizing: border-box`.
5. **Tasks table**: hide the `HOURS` column under 480px (lowest signal-to-real-estate ratio); truncate assignee names with ellipsis.

Verification target: `scry.responsive` at width 360 reports `issueCount: 0` for both `/teams/1/sprints` and `/sprint/8`.

### Bug 5 — Sync Sprints (and friends) have no feedback

**Files:** `static/dashboard.js`, `static/style.css`, `templates/base.html` (or wherever the global container is — we'll find it).

Add a small toast helper:

1. **CSS** in `style.css`:

   ```css
   .toast-container { position: fixed; top: 16px; right: 16px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; }
   .toast { padding: 10px 16px; border-radius: 6px; background: #2d3748; color: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.15); animation: toast-in 0.2s ease-out; max-width: 360px; }
   .toast.success { background: #38a169; }
   .toast.error { background: #e53e3e; }
   @keyframes toast-in { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
   ```

2. **JS** in `dashboard.js`:

   ```javascript
   function showToast(message, kind) {
     const key = "pending_toast";
     // If we're about to reload, persist for next page
     if (kind === "deferred") {
       sessionStorage.setItem(key, JSON.stringify({ message, kind: "success" }));
       return;
     }
     let container = document.querySelector(".toast-container");
     if (!container) {
       container = document.createElement("div");
       container.className = "toast-container";
       document.body.appendChild(container);
     }
     const toast = document.createElement("div");
     toast.className = "toast " + (kind || "info");
     toast.textContent = message;
     container.appendChild(toast);
     setTimeout(() => toast.remove(), 4000);
   }

   // On every page load, drain a pending toast (set before location.reload())
   document.addEventListener("DOMContentLoaded", () => {
     const pending = sessionStorage.getItem("pending_toast");
     if (pending) {
       sessionStorage.removeItem("pending_toast");
       try {
         const { message, kind } = JSON.parse(pending);
         showToast(message, kind);
       } catch {}
     }
   });
   ```

3. **Update `syncSprints`**:

   ```javascript
   async function syncSprints(teamId) {
     const btn = document.getElementById('sync-btn');
     btn.textContent = 'Syncing...'; btn.disabled = true;
     try {
       const resp = await fetch(`/teams/${teamId}/sync-sprints`, { method: 'POST' });
       if (!resp.ok) {
         showToast("Sync misslyckades", "error");
         btn.disabled = false; btn.textContent = '🔄 Sync Sprints';
         return;
       }
       const data = await resp.json();
       const count = data.synced || 0;
       const msg = count === 0
         ? "Inga nya sprintar hittades."
         : `✓ Sync klar — ${count} ${count === 1 ? "sprint" : "sprintar"} synkade.`;
       sessionStorage.setItem("pending_toast", JSON.stringify({ message: msg, kind: "success" }));
       location.reload();
     } catch (e) {
       showToast("Sync misslyckades: " + e.message, "error");
       btn.disabled = false; btn.textContent = '🔄 Sync Sprints';
     }
   }
   ```

4. **Update `refreshSprint`, `closeForecast`, `closeSprint`** with the same `sessionStorage`-defer-then-reload pattern (or `showToast` directly when no reload is needed). Each gets a tailored success message:
   - `refreshSprint`: `"✓ Refresh klar"`
   - `closeForecast`: `"✓ Forecast låst"`
   - `closeSprint`: `"✓ Sprint stängd"`

5. **Toast-container is created lazily** so we don't need to edit `base.html`. The first `showToast` call appends it to `document.body`.

## Verification Strategy (scry)

After each task lands and is committed, we run a targeted scry session. Each task ends with its own scry verification step before commit, and the result is recorded in the task's report.

| Task | Scry verification |
|---|---|
| Bug 1 | `scry.open /sprint/8` → `scry.snapshot inline:true` → grep visual for "Closed" not "Day None"; same for `/sprint/9` (planning, sprint_day=None) → "Not started" |
| Bug 2 | `scry.open /sprint/8` → `scry.evaluate` to read X-axis labels → assert max label is `Day 14` |
| Bug 3 | `scry.open /teams/1/sprints` → `scry.snapshot` → grep visual + DOM for `(4/`, `(5/` → 0 hits |
| Bug 4 | `scry.responsive /sprint/8` widths=[360,768,1024] → all `issueCount: 0`. Same for `/teams/1/sprints` |
| Bug 5 | `scry.open /teams/1/sprints` → `scry.click "🔄 Sync Sprints"` → wait for reload → `scry.snapshot` → see toast text on screen |

Between tasks: `scry.close` to discard browser state and start the next verification clean.

## Edge Cases & Risks

- **Bug 2's "Last snapshot…" caption needs `last_data_day`** in the route context. If `progress_history` is empty (sprint hasn't started or no snapshots ever), no caption shown — current behavior preserved.
- **Bug 3's display_name filter** could surprise someone who searches the UI for a literal `(4/19)` and finds nothing. Acceptable — DB is the source of truth and search isn't a feature here.
- **Bug 4's mobile media query** at 480px overlaps slightly with the 768px block — the cascade order means 480px wins for screens under 480 (correct) and 768 wins for 480–768 (also correct). We add the new block AFTER the existing 768 block to keep the cascade simple.
- **Bug 5's sessionStorage**: in private-browsing, sessionStorage may behave differently. The `try/catch` around the JSON parse means worst case we just don't show a toast.
- **Bug 5's reload race**: between `sessionStorage.setItem` and `location.reload()`, both execute synchronously, so the value is committed before the reload. Tested pattern.

## Distribution

Five small files change: one HTML component, one JS file, one CSS file, plus a few-line edit to `app.py` for the Jinja filter, plus a sweep of templates that reference `sprint.name`. All travel via the next `make-deploy-bundle.sh` + `apply-deploy.sh` cycle. No DB migration. No new dependencies.

## Testing

Manual via the scry verification table above. No new automated tests — these are visual/layout fixes whose correctness is best confirmed by looking at the rendered page, which is exactly what scry is for.
