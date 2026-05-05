# ClickUp Design Tokens — Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a token-driven design system based on ClickUp accent + Linear typography, applied to nav + buttons as a pilot. Iterate with scry as visual judge.

**Architecture:** Single CSS file gets a `:root` token block at the top. Targeted rules updated to consume tokens. Plus Jakarta Sans imported via Google Fonts in base.html.

**Spec:** `docs/superpowers/specs/2026-05-05-clickup-design-tokens-design.md`

---

## Task 1: Tokens + font + nav + buttons

**Files:**
- Modify: `templates/base.html` — add Google Fonts `<link>` for Plus Jakarta Sans
- Modify: `static/style.css` — add `:root` tokens; rewrite `.identity-bar`, `.breadcrumbs`, `.team-sub-nav`, `.page-header`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `body` rules

### Step 1: Add Plus Jakarta Sans link in `templates/base.html`

Use `Edit`:

old_string:
```
  <link rel="stylesheet" href="/static/style.css?v=4">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
```

new_string:
```
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css?v=5">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
```

(Bumps cache from v4 → v5.)

### Step 2: Read current `static/style.css` first lines

Run: `head -20 static/style.css`

Confirm there's a `body { ... }` rule near the top.

### Step 3: Prepend `:root` token block to `static/style.css`

Use `Edit` to insert at the very top of the file. Find the first existing rule (likely `*` reset or `body`):

```bash
head -3 static/style.css
```

Insert this `:root` block BEFORE whatever comes first. Use `Edit` with the file's first existing rule as `old_string`, prepending the token block:

If the first lines are something like:
```css
* { box-sizing: border-box; }
body { ... }
```

Use `Edit`:

old_string: (the first 1-3 lines you just read with `head -3`)
new_string: (the token block + same first lines)

The token block to prepend:

```css
:root {
  /* --- Color --- */
  --accent:        #7b68ee;
  --accent-hover:  #6647f0;
  --accent-strong: #7612fa;
  --accent-blue:   #0091ff;

  --fg:            #292d34;
  --fg-muted:      #646464;
  --fg-subtle:     #838383;

  --bg:            #ffffff;
  --bg-secondary:  #f7f8f8;
  --bg-tertiary:   #f0f1f5;

  --border:        #e9ebf0;
  --border-strong: #d9d9d9;

  --shell-bg:      #292d34;
  --shell-fg:      #ffffff;

  --danger:        #e54d4d;
  --danger-hover:  #c53030;

  /* --- Type --- */
  --font-sans: "Plus Jakarta Sans", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", Consolas, monospace;

  /* --- Spacing --- */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;

  /* --- Radius --- */
  --radius-sm: 4px;
  --radius:    6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 9999px;

  /* --- Motion --- */
  --t: 120ms ease-out;
}

```

### Step 4: Update `body` rule

Find the existing `body` rule and update it to use tokens. Use `Edit`:

First read the existing rule:
```bash
grep -nA 6 '^body' static/style.css | head -10
```

Then replace it with:

```css
body {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  color: var(--fg);
  background: var(--bg-secondary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

(The exact `Edit` will depend on what's there — read first, then craft the edit.)

### Step 5: Update `.identity-bar` rules

Find the existing `.identity-bar { ... }` block (added in Sub-project 2). Replace with:

```css
.identity-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 24px;
  background: var(--shell-bg);
  color: var(--shell-fg);
  border-bottom: 1px solid #1a1d23;
}
.identity-bar .brand {
  font-size: 15px;
  font-weight: 600;
  color: var(--shell-fg);
  text-decoration: none;
  letter-spacing: -0.01em;
}
.identity-bar .new-team-btn {
  font-size: 13px;
  padding: 6px 14px;
}
```

### Step 6: Update `.breadcrumbs` rules

Replace existing `.breadcrumbs` block with:

```css
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--fg-muted);
  flex-wrap: wrap;
}
.breadcrumbs a {
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
  transition: color var(--t);
}
.breadcrumbs a:hover {
  color: var(--accent-hover);
  text-decoration: underline;
}
.breadcrumbs .separator {
  color: var(--fg-subtle);
}
.breadcrumbs .current {
  color: var(--fg);
  font-weight: 500;
}
```

### Step 7: Update `.team-sub-nav` rules

Replace existing `.team-sub-nav` block with:

```css
.team-sub-nav {
  display: flex;
  gap: 0;
  padding: 0 24px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  white-space: nowrap;
}
.team-sub-nav .tab {
  position: relative;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 510;
  color: var(--fg-muted);
  text-decoration: none;
  transition: color var(--t), background var(--t);
}
.team-sub-nav .tab:hover {
  color: var(--fg);
  background: var(--bg-secondary);
}
.team-sub-nav .tab.active {
  color: var(--fg);
  font-weight: 600;
}
.team-sub-nav .tab.active::after {
  content: "";
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: -1px;
  height: 2px;
  background: var(--accent);
  border-radius: 1px 1px 0 0;
}
```

(The `::after` pseudo gives us the underline ONLY under the text, not under padding — addresses user's specific complaint.)

### Step 8: Update `.page-header` rules

Replace:

```css
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px 24px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}
.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--fg);
  letter-spacing: -0.01em;
}
.page-header .title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.page-header .meta {
  color: var(--fg-muted);
  font-size: 13px;
}
.page-header .actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
```

### Step 9: Update button rules

Find the existing `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger` blocks. Replace them with:

```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 12px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 510;
  line-height: 1.4;
  border-radius: var(--radius);
  border: 1px solid transparent;
  cursor: pointer;
  text-decoration: none;
  transition: background var(--t), color var(--t), border-color var(--t);
  white-space: nowrap;
}
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}
.btn-secondary {
  background: var(--bg);
  color: var(--fg);
  border-color: var(--border-strong);
}
.btn-secondary:hover {
  background: var(--bg-secondary);
  border-color: var(--fg-subtle);
}
.btn-danger {
  background: var(--danger);
  color: #fff;
  border-color: var(--danger);
}
.btn-danger:hover {
  background: var(--danger-hover);
  border-color: var(--danger-hover);
}
.btn-success {
  background: #38a169;
  color: #fff;
  border-color: #38a169;
}
.btn-success:hover {
  background: #2f855a;
  border-color: #2f855a;
}
.btn.disabled, .btn[aria-disabled="true"] {
  opacity: 0.5;
  cursor: not-allowed;
}
```

### Step 10: Verify CSS still balances

```bash
.venv/bin/python -c "css = open('static/style.css').read(); print('balanced' if css.count('{') == css.count('}') else 'IMBALANCED')"
```

### Step 11: Restart

```bash
./stop.sh && ./start.sh
```

### Step 12: Commit

```bash
git add static/style.css templates/base.html
git commit -m "$(cat <<'EOF'
feat(ui): introduce design tokens — ClickUp accent + Linear typography

Adds a :root token block at the top of style.css with color, type,
spacing, radius, and motion tokens. Imports Plus Jakarta Sans from
Google Fonts. Migrates identity bar, breadcrumbs, sub-nav, page
header, and the four button variants to consume tokens. Sub-nav
active state uses ::after pseudo so the underline sits under the
text only (addressing user's specific complaint about the
full-bbox underline).

Pilot scope — cards/panels/tables/KPI/charts come in a follow-up.

Refs spec: docs/superpowers/specs/2026-05-05-clickup-design-tokens-design.md
EOF
)"
```

## Working Directory: `/Users/collin/dev/Projects/ClickUp-report-app`

## Report

Status: DONE | BLOCKED
- Step 10 CSS balance
- Step 11 start.sh output
- Files changed (must be exactly 2)
- Commit hash
- Any concerns
