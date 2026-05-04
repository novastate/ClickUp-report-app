# Deploy Bundle Workflow

## Context

The app is developed on one Mac and runs live on a second Mac. The user wants a manual but reliable way to push code changes from dev to live without:

- overwriting the live database (`sprint_data.db`)
- leaking or overwriting `.env` (contains the ClickUp API key)
- leaving the live machine in a half-deployed state if something interrupts the copy

GitHub remains in the loop as **backup**, but is not the transport. Code moves from dev → live as a single zip file, AirDropped manually.

## Problem

Today the only way to "deploy" is AirDropping individual files. It works for one or two files but does not scale: when several files change, the user has to remember exactly what changed, and there is no protection against accidentally including `sprint_data.db` or `.env` in the AirDrop.

## Goal

Two scripts and a five-click workflow:

- `./make-deploy-bundle.sh` on the dev Mac → produces `deploy-bundle.zip`
- AirDrop the zip to the live Mac
- `./apply-deploy.sh` on the live Mac → stops the app, unpacks the bundle, reinstalls dependencies if needed, restarts the app

DB and `.env` on the live Mac are guaranteed untouched **by construction** — they are not in the bundle, so `unzip` cannot overwrite them.

## Non-Goals

- No automated deploy, no CI/CD, no `git pull` flow on live. The user explicitly chose manual transport.
- No incremental/differential deploy. Each bundle is a full snapshot of the code; `unzip -o` overwrites whatever is on live.
- No removal of files that exist on live but not in the new bundle. Documented as a manual step in `docs/DEPLOY.md` (see below).
- No rollback automation beyond a pre-deploy DB backup. If a bundle is bad, the user re-deploys an older bundle.

## Bundle Contents

### Included (code)

- `src/` (entire directory)
- `templates/`, `static/`
- `app.py`, `requirements.txt`
- `start.sh`, `stop.sh`
- `apply-deploy.sh` (so updates to the deploy script itself reach live)
- `clickup-api-discovery.md` (root-level reference doc)
- `docs/features.md` (user-facing feature description)
- `.env.example` (only contains placeholders, safe to ship)

### Excluded

| Excluded | Reason |
|---|---|
| `sprint_data.db`, `sprint_data.db.backup` | Live data — overwriting would destroy it |
| `.env` | Live secrets (API key) |
| `.pid`, `app.log` | Runtime state, machine-specific |
| `.venv/` | Recreated by `start.sh` if missing; large |
| `__pycache__/`, `.pytest_cache/` | Build artifacts |
| `.git/` | Live doesn't need history; large |
| `.DS_Store` | macOS Finder artifact |
| `.claude/`, `.superpowers/`, `docs/superpowers/` | Dev-only; planning docs and tooling |
| `tests/` | Live runs the app, not tests |
| `make-deploy-bundle.sh` | Only needed on dev |
| `deploy-bundle.zip` | The bundle itself (avoid recursion) |

### Format

`deploy-bundle.zip` in the project root, single file. macOS unpacks zips natively (Finder double-click, or `unzip` CLI).

## Design

### `make-deploy-bundle.sh` (on dev Mac)

1. `cd` to the script's directory.
2. **Git-state warning** (informational, non-blocking): if `git status --porcelain` shows uncommitted changes, print a warning so the user is aware the bundle includes work-in-progress that isn't on GitHub.
3. **Print summary header**: last commit hash + subject (so the user can verify the bundle reflects what they expect).
4. **Build the bundle**: `zip -r deploy-bundle.zip` with explicit `-x` exclusion patterns matching the table above. Overwrite any previous `deploy-bundle.zip`.
5. **Print result**: bundle path, size, file count.
6. **Print next-step hint**: "AirDrop deploy-bundle.zip to the live Mac, then run ./apply-deploy.sh there."

### `apply-deploy.sh` (on live Mac)

1. `cd` to the script's directory.
2. Verify `deploy-bundle.zip` exists. If not → print "Hittar inte deploy-bundle.zip i den här mappen. Lägg zip-filen här först." and exit 1.
3. **Pre-deploy DB backup** (defensive): `cp sprint_data.db "sprint_data.db.before-deploy-$(date +%Y%m%d-%H%M%S)"` (only if `sprint_data.db` exists).
4. **Capture old `requirements.txt` hash** before unzip, for the dependency-change check below.
5. **Stop the app**: `./stop.sh` (the new worker-aware version we already shipped).
6. **Unpack**: `unzip -o deploy-bundle.zip` (`-o` = overwrite without prompting). Files in the zip overwrite their counterparts on disk. Files not in the zip are left alone (so `sprint_data.db`, `.env`, etc. are untouched).
7. **Restore execute bits**: `chmod +x start.sh stop.sh apply-deploy.sh` (safe even if zip preserved them).
8. **Conditional `pip install`**: compute new `requirements.txt` hash; if it differs from the captured pre-unzip hash → `.venv/bin/pip install -r requirements.txt`. (Idempotent enough to skip when unchanged, since reinstalling 8 already-installed packages still takes a couple of seconds.)
9. **Start the app**: `./start.sh` — which already polls `/health` and prints the URL/PID line.
10. **Cleanup**: leave `deploy-bundle.zip` in place. The user can delete it manually, or it gets overwritten by the next deploy.

### `docs/DEPLOY.md`

A short user-facing checklist covering:

- The five-click workflow (numbered, with exact commands).
- How to delete a file on live (since `unzip -o` won't): SSH/AirDrop in, `rm path/to/file`, restart.
- How to roll back: keep older `deploy-bundle.zip` versions in a folder, re-run `apply-deploy.sh` against an older one. The pre-deploy DB backup means even a bad code rollback won't lose data.
- How to recover if `apply-deploy.sh` fails partway: stop is idempotent, start is idempotent, manual `unzip -o deploy-bundle.zip` is safe — just rerun `./apply-deploy.sh`.

## Edge Cases

- **Live Mac has uncommitted local changes.** Will be silently overwritten by `unzip -o`. Acceptable: live shouldn't have local edits. The pre-deploy DB backup is the safety net for the only thing that matters.
- **Zip transferred but corrupted.** `unzip` errors out before touching most files; `./stop.sh` already ran in step 5, so the app is down. User re-AirDrops the zip and reruns `apply-deploy.sh`. (Documented in `DEPLOY.md`.)
- **`requirements.txt` removes a package.** `pip install -r` doesn't uninstall removed packages, but they don't break the app. Acceptable for this workflow.
- **New Python version required.** Out of scope — would need manual venv recreation.
- **Bundle accidentally includes a secret.** Mitigated by the explicit exclusion list. The `.env.example` file is the only `.env*` we ship and it has placeholders.

## Distribution Path

Both new scripts (`make-deploy-bundle.sh`, `apply-deploy.sh`) need to reach the live Mac at least once to start using them. After that they stay in sync via the bundle itself (since `apply-deploy.sh` is included). Bootstrap on live: AirDrop `apply-deploy.sh` once, `chmod +x apply-deploy.sh`. From then on every bundle includes its own latest copy.

## Testing

Manual on the dev Mac (everything except step 5 can be exercised here without touching the live Mac):

1. **Bundle creation:** `./make-deploy-bundle.sh` → bundle exists, `unzip -l deploy-bundle.zip` shows code files but no `sprint_data.db`, no `.env`, no `.git/`, no `.venv/`.
2. **Bundle hygiene:** grep the zip's listing for `sprint_data.db`, `.env`, `.git/`, `.venv/`, `__pycache__`, `.DS_Store` — all should produce zero matches.
3. **Apply on a fresh sandbox:** in a `/tmp/sandbox` directory, copy `sprint_data.db` and `.env` (or stand-ins), drop `deploy-bundle.zip` in, run `./apply-deploy.sh` (after copying it there too). Verify: app starts on port 8000, the original DB and `.env` are byte-identical to before, `sprint_data.db.before-deploy-*` backup file exists.
4. **Re-deploy idempotence:** in the sandbox, run `./apply-deploy.sh` a second time with the same bundle. Should succeed; new DB backup is created; app restarts cleanly.
5. **Live target (real test):** repeat step 3's flow on the actual live Mac, against a known DB. Verify DB hash unchanged before/after, app reachable, existing teams/sprints visible.
