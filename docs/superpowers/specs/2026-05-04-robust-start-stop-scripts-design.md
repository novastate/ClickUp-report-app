# Robust Start/Stop Scripts

## Context

The app currently starts via `./start.sh` and stops via `./stop.sh`. Both rely on a `.pid` file in the project root. This is intentionally a small, temporary improvement: the app is expected to move to a more central host later, so the goal is **just to make the local Mac scripts reliable until then** — not to introduce LaunchAgents, menu-bar apps, or other macOS UI.

## Problem

Two real-world failures the user hits today:

1. **Stale `.pid`.** When the app crashes, `.pid` remains on disk pointing at a dead PID. `start.sh` then refuses to start ("App verkar redan köra") and the user has to `rm .pid` manually.
2. **Unclear actual state.** The presence of `.pid` does not prove the app is running, and the absence does not prove it is not. The user has no quick way to know whether the app is up.

The user also wants the start script to **show which port** the app is running on so they can click straight into it.

## Goal

Two scripts, no new dependencies, no new tooling. After this change:

- `start.sh` always does the right thing — whether the app is running, dead, or stale.
- `stop.sh` always does the right thing — including cleaning up after a crash.
- Running `./start.sh` doubles as a status check: the output tells you the URL/port and PID, regardless of whether it just started the app or found it already running.

## Non-Goals

- No LaunchAgent / launchd auto-start. (Decided: app is temporary on this Mac.)
- No menu-bar app, no SwiftBar, no `.app` bundle.
- No status.sh / third script. The user explicitly asked for two.
- No changes to `app.py` or anything inside `src/`.

## Design

### `start.sh`

1. `cd` to the script's directory (as today).
2. Determine the port: read `PORT` from `.env` if present, otherwise default to `8000`. Same for `HOST` (default `0.0.0.0`) — only used in messages, the app reads its own config.
3. If `.pid` exists:
   - If `kill -0 $(cat .pid)` succeeds → app is running. Print `Sprint Reporter kör redan på http://localhost:PORT (PID X). Loggar: app.log` and exit 0.
   - Otherwise → print `Städade stale .pid (PID X körde inte).`, `rm .pid`, continue.
4. Sanity check: if `lsof -iTCP:PORT -sTCP:LISTEN` shows something else listening on the port → print a clear warning with the offending process and exit 1. (Avoids starting a second instance that will crash on bind, or attaching to an unrelated process.)
5. Create `.venv` if missing (existing behavior).
6. Start the app exactly as today: `nohup .venv/bin/python app.py > app.log 2>&1 &`. Write the new PID to `.pid`.
7. Wait up to ~5 seconds for `http://localhost:PORT/health` to respond `200`. Poll every ~0.5s. If it never comes up:
   - Print `Appen startade inte inom 5 sekunder. Senaste loggrader:` followed by `tail -n 20 app.log`.
   - Leave `.pid` in place (the user can `./stop.sh` to clean up — covered below).
   - Exit 1.
8. On success: print `Sprint Reporter körs på http://localhost:PORT (PID X). Loggar: app.log`.

### `stop.sh`

1. `cd` to the script's directory.
2. If `.pid` does not exist → print `Sprint Reporter kör inte.` and exit 0.
3. Read `PID=$(cat .pid)`.
4. If `kill -0 $PID` fails → print `Städade stale .pid (PID X körde inte).`, `rm .pid`, exit 0.
5. Otherwise → `kill $PID`. Poll `kill -0 $PID` every ~0.5s for up to ~5s. Once it stops responding (or after timeout, send `kill -9` and wait briefly), `rm .pid`. Print `Stoppade Sprint Reporter (PID X).`.

### Status as a side effect

Running `./start.sh` when the app is already up prints the URL/port/PID line in step 3a and exits without changing anything. That is the user's status check — they don't need a third script.

## Edge Cases

- **`.env` missing or `PORT` not set** → fall back to `8000`. (Mirrors `src/config.py`.)
- **`.env` has `PORT` with surrounding whitespace or quotes** → parse with a small grep/sed, not `source` (avoids accidentally executing `.env`).
- **PID was reused by an unrelated process** after a crash. `kill -0` would still pass and we'd report it as running. Acceptable for this temporary scope — extremely unlikely on a personal Mac, and the port sanity check in step 4 catches the case where the unrelated process happens not to be ours but is on the port. Documenting as a known limitation.
- **App takes longer than 5s to start** → exit 1 with log tail; user can re-run `./start.sh` (which will then see the running PID and exit cleanly). Tunable via constant at top of script if it ever becomes a problem.
- **`lsof` not installed** → ships with macOS, so fine for the stated environment.

## Testing

Manual verification on the user's Mac, since this is shell + a real running FastAPI process:

1. **Cold start:** no `.pid`, port free → `./start.sh` reports running with URL/PID; `curl localhost:PORT/health` → 200.
2. **Already running:** run `./start.sh` again → reports "kör redan" with same PID, no new process.
3. **Stale `.pid`:** simulate by `kill -9 $(cat .pid)` directly, leaving `.pid` behind → `./start.sh` reports "städade stale" and starts cleanly.
4. **Port hijacked:** `python3 -m http.server PORT` in another shell → `./start.sh` reports the conflict and exits 1 without overwriting `.pid`.
5. **Stop while running:** `./stop.sh` → process gone, `.pid` gone, "Stoppade…" message.
6. **Stop with stale `.pid`:** `kill -9 $(cat .pid)`, then `./stop.sh` → "Städade stale…", `.pid` gone.
7. **Stop when nothing running:** `./stop.sh` with no `.pid` → "Sprint Reporter kör inte."
