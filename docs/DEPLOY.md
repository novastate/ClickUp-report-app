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
