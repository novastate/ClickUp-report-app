# ClickUp-Inspired Design Tokens

## Context

User criticized current nav as "under all kritik" and asked for a clean, modern app aligned with ClickUp's accent colors. We captured Linear.app and ClickUp.com via scry to extract design tokens, then synthesized a light-mode palette with ClickUp accent + Linear's typographic discipline.

scry stays in the loop as visual judge — every change verified by snapshot.

## Problem

The current CSS uses ad-hoc colors (`#4299e1` blue, `#1a202c` near-black, etc.) and inconsistent button/nav styles. There's no token system; designers/devs read each rule and guess. Hover states are minimal, active states are inelegant (full-bbox underline on tabs), and the typography (system stack at 16px default) is bland.

## Goal

Introduce a token-driven design system based on ClickUp's accent + Linear's typography, applied first to nav (top bar / breadcrumbs / sub-nav / buttons) as a pilot. After approval, propagate to cards / panels / KPI / tables.

## Tokens (the source of truth)

```css
:root {
  /* Color */
  --accent:           #7b68ee;   /* primary action, active states, links */
  --accent-hover:     #6647f0;   /* deeper purple for hover */
  --accent-strong:    #7612fa;   /* signature CTA — sync button only */
  --accent-blue:      #0091ff;   /* info / secondary link tone */

  --fg:               #292d34;   /* body text */
  --fg-muted:         #646464;   /* secondary text */
  --fg-subtle:        #838383;   /* placeholders, separators */

  --bg:               #ffffff;
  --bg-secondary:     #f7f8f8;   /* Linear's signature subtle off-white */
  --bg-tertiary:      #f0f1f5;   /* slightly darker, for hover states */

  --border:           #e9ebf0;   /* default 1px borders */
  --border-strong:    #d9d9d9;   /* emphasized borders */

  --shell-bg:         #292d34;   /* dark identity bar (replaces #1a202c) */
  --shell-fg:         #ffffff;

  /* Type */
  --font-sans: "Plus Jakarta Sans", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --font-mono: "Sometype Mono", "JetBrains Mono", ui-monospace, monospace;

  /* Spacing scale (Linear's tight rhythm) */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-6:  24px;
  --space-8:  32px;

  /* Radius */
  --radius-sm: 4px;
  --radius:    6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 9999px;

  /* Transition */
  --t: 120ms ease-out;
}
```

## Pilot scope (Iteration 1)

Apply tokens to:

1. **Font import + base** — Google Fonts (Plus Jakarta Sans), set `body { font-family: var(--font-sans); color: var(--fg); }`.
2. **Identity bar** — `--shell-bg`, `--shell-fg`, `font-weight: 510`.
3. **Breadcrumbs** — links in `--accent`, separator `--fg-subtle`, current in `--fg`.
4. **Sub-nav tabs** — active = thin 2px underline **only under the text** (`box-shadow` trick or `::after` pseudo) in `--accent`, color `--fg`. Inactive = `--fg-muted` weight 510, hover = `--fg` + `background: var(--bg-secondary)`.
5. **Buttons**:
   - `btn-primary`: `background: var(--accent)`, hover `--accent-hover`, white text, weight 510.
   - `btn-secondary`: `background: var(--bg)`, `1px solid var(--border-strong)`, color `--fg`, hover `background: var(--bg-secondary)`.
   - `btn-danger`: keep red, but adjust to match the new tone (`#e54d4d`).
   - All: `border-radius: var(--radius)`, `padding: 6px 12px`, `font-weight: 510`, `transition: var(--t)`.
6. **Page header (`.page-header`)** — keep light, but adjust h1 to `--fg`, meta to `--fg-muted`, font scale.

## Out of scope (Iteration 2 — later)

- KPI cards, panels, tables, charts, badges, scope timeline. Apply tokens after Iteration 1 lands and we've verified the foundation looks right.

## Verification (scry as judge)

For each pilot iteration:

1. `scry.snapshot inline:true` of `/teams/1/sprints` (busiest page).
2. Compare visually against `.refs/linear/screenshots/full.png` — ask: does our app feel like a sibling of Linear's polish?
3. Check `consoleErrors`: 0 (Plus Jakarta Sans loads cleanly).
4. After all changes: snapshot the same page user originally complained about and confirm the issues they flagged are gone.

If something looks off (active tab too prominent, button too dim, font hierarchy weird), we iterate the CSS in a follow-up commit. Same task, multiple commits if needed.

## Distribution

Two files: `static/style.css` (replace top of file with tokens block + replace targeted rules), `templates/base.html` (add Google Fonts `<link>`). Bundle ships normally.
