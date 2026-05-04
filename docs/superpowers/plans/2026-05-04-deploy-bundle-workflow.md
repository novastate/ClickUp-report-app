# Deploy Bundle Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `make-deploy-bundle.sh` (dev) + `apply-deploy.sh` (live) + `docs/DEPLOY.md` so code can be transported from dev Mac to live Mac as a single zip without ever overwriting `sprint_data.db` or `.env`.

**Architecture:** Two pure-bash scripts and one markdown file. Bundle is a `zip -r ... -x` of code-only files; deploy is `stop → unzip -o → conditional pip install → start`. DB/env safety is by construction (excluded from bundle, so `unzip` cannot touch them) plus a defensive timestamped DB backup pre-deploy.

**Tech Stack:** Bash, macOS-bundled tools (`zip`, `unzip`, `shasum`, `cp`, `git`), the existing `start.sh` / `stop.sh` we already shipped.

**Spec:** `docs/superpowers/specs/2026-05-04-deploy-bundle-workflow-design.md`

**Testing approach:** Manual sandbox test on the dev Mac plus zip-content inspection. We do not introduce automated tests for the same reason as the start/stop scripts: this is shell tooling for a temporary deploy flow, and the spec defines explicit manual verification.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `make-deploy-bundle.sh` | Create | Build `deploy-bundle.zip` from the project, excluding data/runtime/dev-only files. |
| `apply-deploy.sh` | Create | On live: backup DB → stop → unzip → conditional pip install → start. |
| `docs/DEPLOY.md` | Create | User-facing checklist: workflow, deletion, rollback, recovery. |
| `.gitignore` | Modify | Add `deploy-bundle.zip` and `sprint_data.db.before-deploy-*` so they don't get committed. |

No code in `src/`, `app.py`, or `requirements.txt` is touched.

---

## Task 1: Add `make-deploy-bundle.sh`

**Files:**
- Create: `make-deploy-bundle.sh`

- [ ] **Step 1: Create `make-deploy-bundle.sh`**

Write this exact content:

```bash
#!/bin/bash
cd "$(dirname "$0")"

BUNDLE="deploy-bundle.zip"

# --- Git-state warning (informational, non-blocking) ---
if [ -d .git ]; then
    DIRTY=$(git status --porcelain 2>/dev/null)
    if [ -n "$DIRTY" ]; then
        echo "⚠️  Varning: arbetskatalogen har ouncommittade ändringar."
        echo "   Bundlen kommer att inkludera dessa, men de finns inte på GitHub."
        echo ""
    fi
    LAST_COMMIT=$(git log -1 --oneline 2>/dev/null)
    if [ -n "$LAST_COMMIT" ]; then
        echo "Senaste commit: $LAST_COMMIT"
    fi
fi

# --- Remove any previous bundle ---
rm -f "$BUNDLE"

# --- Build the bundle ---
echo "Bygger $BUNDLE..."
zip -rq "$BUNDLE" \
    src \
    templates \
    static \
    app.py \
    requirements.txt \
    start.sh \
    stop.sh \
    apply-deploy.sh \
    clickup-api-discovery.md \
    docs/features.md \
    .env.example \
    -x "*/__pycache__/*" \
       "*/.pytest_cache/*" \
       "*.pyc" \
       "*/.DS_Store" \
       ".DS_Store"

# --- Print result ---
SIZE=$(du -h "$BUNDLE" | awk '{print $1}')
COUNT=$(unzip -l "$BUNDLE" | tail -n1 | awk '{print $2}')
echo ""
echo "Bundle klar: $BUNDLE ($SIZE, $COUNT filer)"
echo ""
echo "Nästa steg:"
echo "  1. AirDrop $BUNDLE till live-Macen."
echo "  2. På live: flytta filen till projektmappen och kör ./apply-deploy.sh"
```

- [ ] **Step 2: Verify shell syntax**

Run: `bash -n make-deploy-bundle.sh`

Expected: exits 0 with no output.

- [ ] **Step 3: Make executable**

Run: `chmod +x make-deploy-bundle.sh && ls -l make-deploy-bundle.sh`

Expected: line begins with `-rwxr-xr-x`.

- [ ] **Step 4: Smoke-test the bundle creation**

Run: `./make-deploy-bundle.sh`

Expected output:
```
Senaste commit: <hash> <subject>
Bygger deploy-bundle.zip...

Bundle klar: deploy-bundle.zip (XXXk, NN filer)

Nästa steg:
  1. AirDrop deploy-bundle.zip till live-Macen.
  2. På live: flytta filen till projektmappen och kör ./apply-deploy.sh
```

(`apply-deploy.sh` does not exist yet — `zip` will simply skip it with a warning, which is fine.)

After: `ls -la deploy-bundle.zip` exists.

- [ ] **Step 5: Verify hygiene of the bundle**

Run:
```bash
echo "=== Should NOT match (zero results each) ==="
unzip -l deploy-bundle.zip | grep -E '(sprint_data\.db|^\.env$|/\.env$|\.git/|\.venv/|__pycache__|\.pytest_cache|\.DS_Store|docs/superpowers/|tests/|\.claude/|\.superpowers/)' && echo "FAIL: forbidden file in bundle" || echo "OK: no forbidden files"

echo ""
echo "=== Should match (each must appear) ==="
for f in app.py requirements.txt start.sh stop.sh "src/" "templates/" "static/" .env.example; do
    unzip -l deploy-bundle.zip | grep -q "$f" && echo "OK: $f present" || echo "FAIL: $f missing"
done
```

Expected: every line either prints `OK: ...` or `OK: no forbidden files`. Any `FAIL` line must be investigated and the script's `-x` patterns adjusted.

- [ ] **Step 6: Commit**

```bash
git add make-deploy-bundle.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add make-deploy-bundle.sh

Builds deploy-bundle.zip with code-only files (src/, templates/,
static/, app.py, requirements.txt, start.sh, stop.sh,
apply-deploy.sh, .env.example, two reference docs). Explicitly
excludes the DB, .env, .venv, .git, build caches, and dev-only
docs/superpowers/ + tests/.

Refs spec: docs/superpowers/specs/2026-05-04-deploy-bundle-workflow-design.md
EOF
)"
```

---

## Task 2: Add `apply-deploy.sh`

**Files:**
- Create: `apply-deploy.sh`

- [ ] **Step 1: Create `apply-deploy.sh`**

Write this exact content:

```bash
#!/bin/bash
cd "$(dirname "$0")"

BUNDLE="deploy-bundle.zip"

# --- Verify bundle exists ---
if [ ! -f "$BUNDLE" ]; then
    echo "Hittar inte $BUNDLE i den här mappen."
    echo "Lägg zip-filen här först (drag-och-släpp från Downloads)."
    exit 1
fi

echo "=== Sprint Reporter: applying deploy ==="
echo ""

# --- Pre-deploy DB backup ---
if [ -f sprint_data.db ]; then
    BACKUP="sprint_data.db.before-deploy-$(date +%Y%m%d-%H%M%S)"
    cp sprint_data.db "$BACKUP"
    echo "DB-backup: $BACKUP"
fi

# --- Capture pre-unzip requirements.txt hash ---
OLD_REQ_HASH=""
if [ -f requirements.txt ]; then
    OLD_REQ_HASH=$(shasum requirements.txt | awk '{print $1}')
fi

# --- Stop the app ---
echo ""
echo "Stoppar appen..."
./stop.sh

# --- Unpack the bundle ---
echo ""
echo "Packar upp $BUNDLE..."
unzip -oq "$BUNDLE"

# --- Restore execute bits ---
chmod +x start.sh stop.sh apply-deploy.sh 2>/dev/null

# --- Conditional pip install ---
NEW_REQ_HASH=""
if [ -f requirements.txt ]; then
    NEW_REQ_HASH=$(shasum requirements.txt | awk '{print $1}')
fi
if [ "$OLD_REQ_HASH" != "$NEW_REQ_HASH" ]; then
    echo ""
    echo "requirements.txt har ändrats — installerar dependencies..."
    if [ -d .venv ]; then
        .venv/bin/pip install -r requirements.txt
    else
        echo "Ingen .venv — start.sh skapar en ny och installerar."
    fi
fi

# --- Start the app ---
echo ""
echo "Startar appen..."
./start.sh
START_EXIT=$?

echo ""
if [ "$START_EXIT" = "0" ]; then
    echo "=== Deploy klar ==="
else
    echo "=== Deploy klar, men start.sh misslyckades. Se app.log. ==="
    exit "$START_EXIT"
fi
```

- [ ] **Step 2: Verify shell syntax**

Run: `bash -n apply-deploy.sh`

Expected: exits 0 with no output.

- [ ] **Step 3: Make executable**

Run: `chmod +x apply-deploy.sh && ls -l apply-deploy.sh`

Expected: line begins with `-rwxr-xr-x`.

- [ ] **Step 4: Sandbox test (apply-deploy in isolation)**

This simulates a live-Mac deploy without touching the real live machine.

Setup:
```bash
SANDBOX=/tmp/sprint-reporter-sandbox
rm -rf "$SANDBOX"
mkdir -p "$SANDBOX"

# Stage in fake live state: existing DB + .env, plus the old start/stop scripts
cp sprint_data.db "$SANDBOX/sprint_data.db"
echo "FAKE_API_KEY=pk_fake" > "$SANDBOX/.env"
echo "PORT=8765" >> "$SANDBOX/.env"   # use a non-default port to avoid collisions
cp start.sh stop.sh apply-deploy.sh "$SANDBOX/"

# Build a fresh bundle and copy it into the sandbox
./make-deploy-bundle.sh
cp deploy-bundle.zip "$SANDBOX/"

# Capture DB hash before
DB_BEFORE=$(shasum "$SANDBOX/sprint_data.db" | awk '{print $1}')
ENV_BEFORE=$(shasum "$SANDBOX/.env" | awk '{print $1}')
echo "Pre-deploy DB hash: $DB_BEFORE"
echo "Pre-deploy .env hash: $ENV_BEFORE"
```

Run apply:
```bash
cd "$SANDBOX" && ./apply-deploy.sh
```

Expected output (key lines):
- `DB-backup: sprint_data.db.before-deploy-YYYYMMDD-HHMMSS`
- `Stoppar appen...` then `Sprint Reporter kör inte.` (nothing was running)
- `Packar upp deploy-bundle.zip...`
- `Startar appen...` then `Sprint Reporter körs på http://localhost:8765 (PID X)`
- `=== Deploy klar ===`

Verify:
```bash
DB_AFTER=$(shasum sprint_data.db | awk '{print $1}')
ENV_AFTER=$(shasum .env | awk '{print $1}')
[ "$DB_BEFORE" = "$DB_AFTER" ] && echo "✓ DB unchanged" || echo "✗ DB CHANGED — FAIL"
[ "$ENV_BEFORE" = "$ENV_AFTER" ] && echo "✓ .env unchanged" || echo "✗ .env CHANGED — FAIL"
ls sprint_data.db.before-deploy-* >/dev/null 2>&1 && echo "✓ Backup file exists" || echo "✗ no backup — FAIL"
curl -s http://localhost:8765/health
```

Expected: all three checkmarks, `{"status":"ok"}` from curl.

Cleanup:
```bash
./stop.sh
cd -
rm -rf "$SANDBOX"
rm -f deploy-bundle.zip
```

- [ ] **Step 5: Re-deploy idempotence**

Re-create the sandbox by re-running step 4's setup, then run `./apply-deploy.sh` **twice** in a row, with the same bundle. Expected: second run succeeds, creates a second `sprint_data.db.before-deploy-*` backup with a different timestamp, app restarts cleanly. Cleanup as in step 4.

- [ ] **Step 6: Commit**

```bash
git add apply-deploy.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add apply-deploy.sh

Runs on the live Mac after the bundle has been AirDropped in.
Backs up the DB with a timestamp, stops the app, unzips the bundle
(code-only — DB/env are excluded by construction), conditionally
reinstalls dependencies if requirements.txt changed, and starts
the app via the existing start.sh.

Refs spec: docs/superpowers/specs/2026-05-04-deploy-bundle-workflow-design.md
EOF
)"
```

---

## Task 3: Update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Read the current `.gitignore`**

Run: `cat .gitignore`

Expected: see the current 8-line file (`.env`, `*.db`, etc.).

- [ ] **Step 2: Append deploy artifacts**

Append these two lines to `.gitignore`:

```
deploy-bundle.zip
sprint_data.db.before-deploy-*
```

After: `cat .gitignore` should show 10 lines.

- [ ] **Step 3: Verify git ignores them**

Pre-step: `./make-deploy-bundle.sh` so a bundle exists for the check.

Run: `git status`

Expected: `deploy-bundle.zip` does NOT appear in the untracked-files list. (`sprint_data.db.before-deploy-*` similarly won't appear since none exist yet — but the rule will protect against future ones being committed accidentally.)

Cleanup: `rm -f deploy-bundle.zip`

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "$(cat <<'EOF'
chore: ignore deploy-bundle.zip and pre-deploy DB backups

The bundle is regenerated on every deploy and the timestamped
backups are local-only safety copies. Neither belongs in git.
EOF
)"
```

---

## Task 4: Add `docs/DEPLOY.md`

**Files:**
- Create: `docs/DEPLOY.md`

- [ ] **Step 1: Create `docs/DEPLOY.md`**

Write this exact content:

```markdown
# Deploy Workflow

This is the manual deploy flow from the dev Mac to the live Mac. The bundle approach guarantees that `sprint_data.db` and `.env` on the live Mac are never overwritten — they are excluded from the bundle by construction.

## Prerequisites (one-time, on live Mac)

The first time, `apply-deploy.sh` doesn't exist on the live Mac yet. Bootstrap it:

1. AirDrop `apply-deploy.sh` from the dev Mac to the live Mac.
2. Move it into the project directory (next to `start.sh`).
3. `chmod +x apply-deploy.sh`

After that, every bundle includes its own latest `apply-deploy.sh`, so updates ride along automatically.

## Standard deploy flow

**On the dev Mac:**

1. (Optional) `git push` — backup to GitHub.
2. `./make-deploy-bundle.sh` — produces `deploy-bundle.zip` in the project root.
3. AirDrop `deploy-bundle.zip` to the live Mac. (It lands in `~/Downloads`.)

**On the live Mac:**

4. Move `deploy-bundle.zip` from `~/Downloads` into the project directory.
5. `./apply-deploy.sh`

That's it. The script will:
- Take a timestamped backup of `sprint_data.db`.
- Stop the running app.
- Unpack the new code on top of the old (without touching the DB or `.env`).
- Run `pip install -r requirements.txt` if `requirements.txt` changed.
- Start the app and print the URL.

## Removing a file

`unzip -o` adds and overwrites — it never deletes. If you removed a file on dev, it will linger on live until you delete it manually:

```bash
rm path/to/removed-file.py
./stop.sh && ./start.sh   # restart so the change takes effect
```

## Rolling back

There is no rollback script — but rollback is just a re-deploy of an older bundle:

1. Keep recent bundles in a folder, e.g. `~/SprintReporter-deploys/2026-05-04.zip`.
2. To roll back: copy the older zip into the project dir as `deploy-bundle.zip`, run `./apply-deploy.sh`.
3. Your DB stays intact across rollbacks (it's outside the bundle), and the pre-deploy backup gives you another safety net.

## Recovering from a failed deploy

If `apply-deploy.sh` errors out partway:

- The DB backup from step 1 is already on disk. Worst case, restore it with `cp sprint_data.db.before-deploy-YYYYMMDD-HHMMSS sprint_data.db`.
- Both `stop.sh` and `start.sh` are idempotent — re-running them is safe.
- Re-running `apply-deploy.sh` itself is safe: it will take *another* DB backup, stop (already stopped), unzip again, restart.

If the zip is corrupted, AirDrop a fresh one and rerun.

## What gets sent (and what doesn't)

**Sent:** `src/`, `templates/`, `static/`, `app.py`, `requirements.txt`, `start.sh`, `stop.sh`, `apply-deploy.sh`, `clickup-api-discovery.md`, `docs/features.md`, `.env.example`.

**Not sent:** `sprint_data.db`, `sprint_data.db.backup`, `.env`, `.pid`, `app.log`, `.venv/`, `.git/`, `__pycache__/`, `.pytest_cache/`, `tests/`, `docs/superpowers/`, `make-deploy-bundle.sh`.

The exclusion list is hardcoded in `make-deploy-bundle.sh`'s `zip -x` flags.
```

- [ ] **Step 2: Verify the file rendered correctly**

Run: `cat docs/DEPLOY.md | head -5`

Expected: starts with `# Deploy Workflow`.

- [ ] **Step 3: Commit**

```bash
git add docs/DEPLOY.md
git commit -m "$(cat <<'EOF'
docs: add DEPLOY.md with deploy workflow checklist

Covers the standard 5-click flow, removing files (since unzip
won't), rollback by re-deploying older bundles, and recovery
from failed deploys.
EOF
)"
```

---

## Task 5: Full end-to-end dry run on dev Mac

This task does NOT touch the live Mac. It exercises the entire flow against a sandbox to confirm both scripts work together.

- [ ] **Step 1: Build a fresh bundle**

Run: `./make-deploy-bundle.sh`

Expected: bundle created, exclusion-hygiene verified by re-running step 5 from Task 1.

- [ ] **Step 2: Verify the bundle includes the latest `apply-deploy.sh`**

Run: `unzip -p deploy-bundle.zip apply-deploy.sh | head -5`

Expected: prints the first 5 lines of the script (i.e. `apply-deploy.sh` is in the bundle).

- [ ] **Step 3: Sandbox a fake live state**

Run:
```bash
SANDBOX=/tmp/sprint-reporter-sandbox-e2e
rm -rf "$SANDBOX"
mkdir -p "$SANDBOX"

# Use real DB (read-only check; we'll preserve it via backup)
cp sprint_data.db "$SANDBOX/sprint_data.db"
echo "CLICKUP_API_KEY=pk_fake_for_test" > "$SANDBOX/.env"
echo "PORT=8765" >> "$SANDBOX/.env"

# Start with an OLD apply-deploy.sh (simulate that we've already done the bootstrap)
cp apply-deploy.sh "$SANDBOX/"
chmod +x "$SANDBOX/apply-deploy.sh"

# Drop the bundle in
cp deploy-bundle.zip "$SANDBOX/"

DB_BEFORE=$(shasum "$SANDBOX/sprint_data.db" | awk '{print $1}')
ENV_BEFORE=$(shasum "$SANDBOX/.env" | awk '{print $1}')
echo "Sandbox ready at $SANDBOX"
echo "DB hash:  $DB_BEFORE"
echo "ENV hash: $ENV_BEFORE"
```

Expected: setup completes, two hashes printed.

- [ ] **Step 4: Apply the deploy in the sandbox**

Run:
```bash
(cd "$SANDBOX" && ./apply-deploy.sh)
```

Expected output (verifies ordering):
- `DB-backup: sprint_data.db.before-deploy-YYYYMMDD-HHMMSS`
- `Stoppar appen...` → `Sprint Reporter kör inte.`
- `Packar upp deploy-bundle.zip...`
- `Startar appen...` → `Sprint Reporter körs på http://localhost:8765 (PID X). Loggar: app.log`
- `=== Deploy klar ===`

- [ ] **Step 5: Verify post-deploy invariants**

Run:
```bash
DB_AFTER=$(shasum "$SANDBOX/sprint_data.db" | awk '{print $1}')
ENV_AFTER=$(shasum "$SANDBOX/.env" | awk '{print $1}')

[ "$DB_BEFORE" = "$DB_AFTER" ] && echo "✓ DB unchanged" || echo "✗ DB CHANGED"
[ "$ENV_BEFORE" = "$ENV_AFTER" ] && echo "✓ .env unchanged" || echo "✗ .env CHANGED"
ls "$SANDBOX"/sprint_data.db.before-deploy-* >/dev/null 2>&1 && echo "✓ DB backup created" || echo "✗ no backup"
curl -s http://localhost:8765/health
ls "$SANDBOX/src/routes/pages.py" >/dev/null && echo "✓ src/ deployed" || echo "✗ src/ missing"
ls "$SANDBOX/sprint_data.db" >/dev/null && echo "✓ DB still present" || echo "✗ DB lost"
```

Expected: four `✓` checks plus `{"status":"ok"}`.

- [ ] **Step 6: Cleanup**

Run:
```bash
(cd "$SANDBOX" && ./stop.sh)
rm -rf "$SANDBOX"
rm -f deploy-bundle.zip
```

Expected: app stopped, sandbox removed, no `deploy-bundle.zip` left in dev project.

- [ ] **Step 7: No commit needed**

This task is verification only.

---

## Self-Review

**Spec coverage:**
- "Innehåll i bundlen" → Task 1 step 1 (the `zip -r` arg list) and verified in step 5.
- "Exklusioner" → Task 1 step 1 (the `-x` flags) and explicitly grepped in step 5.
- `make-deploy-bundle.sh` design → Task 1 step 1 implements all four bullets (git warning, last-commit print, build, result print).
- `apply-deploy.sh` design → Task 2 step 1 implements all 10 bullets (verify, backup, hash capture, stop, unzip, chmod, conditional pip install, start, cleanup, exit-status handling).
- DB safety → Task 2 step 4 hashes DB before/after to prove no change. Task 5 step 5 repeats it as a final invariant check.
- `docs/DEPLOY.md` → Task 4 covers all four sub-bullets (workflow, deletion, rollback, recovery).
- Edge case "live Mac has uncommitted changes" → Acceptable per spec (overwritten silently); not handled in code.
- Edge case "corrupted zip" → `unzip` exit code is non-zero; Task 2 step 1's exit handling propagates the failure.
- Edge case "secret in bundle" → Task 1 step 5 greps the bundle for `\.env$` and friends; will fail loudly.
- Distribution Path bootstrap → Task 4 step 1 (DEPLOY.md "Prerequisites" section).

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "appropriate error handling" / "similar to Task N" anywhere. All commands and expected outputs are concrete.

**Type/name consistency:** Variable names are consistent (`BUNDLE`, `OLD_REQ_HASH`, `NEW_REQ_HASH`, `BACKUP`). Filenames consistent across all tasks: `make-deploy-bundle.sh`, `apply-deploy.sh`, `deploy-bundle.zip`, `sprint_data.db.before-deploy-*`. The exclusion list in DEPLOY.md (Task 4) matches the `-x` flags in make-deploy-bundle.sh (Task 1) — checked side by side.

**One inline fix made:** Task 1's smoke test (step 4) notes that `apply-deploy.sh` may not exist yet at first run; documented that `zip` will skip it with a warning instead of failing.
