# Robust Start/Stop Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `start.sh` and `stop.sh` so they handle stale `.pid` files automatically, surface the URL/port/PID on every run, and refuse to start when another process already holds the port.

**Architecture:** Two pure-bash scripts in the project root. No new dependencies. Behavior changes only — no Python code, no DB changes, no config schema changes. The scripts read `PORT` from `.env` (fallback 8000), use `kill -0` to verify the PID in `.pid` is alive, use `lsof` for the port sanity check, and use `curl` against the existing `/health` endpoint to confirm a fresh start actually came up.

**Tech Stack:** Bash, macOS-bundled tools (`kill`, `lsof`, `curl`, `grep`, `cut`, `tr`), existing FastAPI app with `/health` endpoint at `app.py:81-83`.

**Spec:** `docs/superpowers/specs/2026-05-04-robust-start-stop-scripts-design.md`

**Testing approach:** The spec defines manual verification (7 scenarios). We do not introduce automated bash tests — that would expand scope beyond a temporary fix the user explicitly framed as "two simple scripts until the app moves to a central host." Instead, each task ends with concrete manual scenarios with exact commands and expected output.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `start.sh` | Modify (full rewrite) | Idempotent start. Reports state if already running, cleans stale `.pid`, refuses on port conflict, verifies health on fresh start. |
| `stop.sh` | Modify (full rewrite) | Idempotent stop. Cleans stale `.pid`, kills + verifies on live process, escalates to `SIGKILL` if needed. |

No other files change.

---

## Task 1: Rewrite `start.sh`

**Files:**
- Modify: `start.sh` (full replacement)

- [ ] **Step 1: Read the existing `start.sh`**

Run: `cat start.sh`

Expected: see the current 21-line script that uses `nohup` + writes `.pid`. Confirms baseline before replacing.

- [ ] **Step 2: Replace `start.sh` with the new version**

Write this exact content to `start.sh`:

```bash
#!/bin/bash
cd "$(dirname "$0")"

# --- Read PORT from .env (fallback 8000) ---
PORT=8000
if [ -f .env ]; then
    ENV_PORT=$(grep -E '^PORT=' .env | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
    if [ -n "$ENV_PORT" ]; then
        PORT=$ENV_PORT
    fi
fi
URL="http://localhost:$PORT"

# --- Already running? ---
if [ -f .pid ]; then
    PID=$(cat .pid)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Sprint Reporter kör redan på $URL (PID $PID). Loggar: app.log"
        exit 0
    else
        echo "Städade stale .pid (PID $PID körde inte)."
        rm -f .pid
    fi
fi

# --- Port sanity check ---
LISTENER=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tail -n +2 | head -n1)
if [ -n "$LISTENER" ]; then
    echo "Något annat lyssnar redan på port $PORT:"
    echo "  $LISTENER"
    echo "Avbryter start. Stoppa den processen eller ändra PORT i .env."
    exit 1
fi

# --- Create venv if missing ---
if [ ! -d .venv ]; then
    echo "Skapar virtuell miljö..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# --- Start the app ---
echo "Startar Sprint Reporter..."
nohup .venv/bin/python app.py > app.log 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > .pid

# --- Wait up to ~5s for /health to return 200 ---
ATTEMPTS=10
i=0
while [ "$i" -lt "$ATTEMPTS" ]; do
    if curl -s -f -o /dev/null "$URL/health"; then
        echo "Sprint Reporter körs på $URL (PID $NEW_PID). Loggar: app.log"
        exit 0
    fi
    if ! kill -0 "$NEW_PID" 2>/dev/null; then
        break  # process died early, stop polling
    fi
    sleep 0.5
    i=$((i + 1))
done

echo "Appen startade inte inom 5 sekunder. Senaste loggrader:"
tail -n 20 app.log
exit 1
```

- [ ] **Step 3: Verify shell syntax is valid**

Run: `bash -n start.sh`

Expected: exits 0 with no output. Any syntax error would print here.

- [ ] **Step 4: Ensure execute bit is set**

Run: `chmod +x start.sh && ls -l start.sh`

Expected: output line begins with `-rwxr-xr-x` (execute bits present).

- [ ] **Step 5: Manual scenario 1 — cold start**

Pre-state: app not running, no `.pid`.

Run:
```
./stop.sh    # ensure clean slate (output may say "kör inte" — that's fine)
ls .pid 2>/dev/null  # should print nothing
./start.sh
```

Expected final line:
```
Sprint Reporter körs på http://localhost:8000 (PID NNNNN). Loggar: app.log
```
And: `cat .pid` shows that PID. `curl -s http://localhost:8000/health` returns `{"status":"ok"}`.

- [ ] **Step 6: Manual scenario 2 — already running**

Pre-state: app running from step 5.

Run: `./start.sh`

Expected:
```
Sprint Reporter kör redan på http://localhost:8000 (PID NNNNN). Loggar: app.log
```
PID matches the one in `.pid`. No new process started (verify with `ps -p $(cat .pid)`).

- [ ] **Step 7: Manual scenario 3 — stale `.pid`**

Pre-state: app from step 5 still running.

Run:
```
kill -9 $(cat .pid)
sleep 1
ls .pid     # .pid still exists, but the process is gone
./start.sh
```

Expected output (in order):
```
Städade stale .pid (PID NNNNN körde inte).
Startar Sprint Reporter...
Sprint Reporter körs på http://localhost:8000 (PID MMMMM). Loggar: app.log
```
(`MMMMM` is a new PID different from `NNNNN`.)

- [ ] **Step 8: Manual scenario 4 — port hijacked**

Pre-state: stop the app first (`./stop.sh`).

Run in one terminal:
```
python3 -m http.server 8000
```
Then in another terminal:
```
./start.sh
```

Expected output:
```
Något annat lyssnar redan på port 8000:
  python3 ... TCP *:8000 (LISTEN)
Avbryter start. Stoppa den processen eller ändra PORT i .env.
```
Exit code 1. No new `.pid` created (`ls .pid` should fail or show old contents only if not cleaned earlier).

Stop the http.server (Ctrl-C) before continuing.

- [ ] **Step 9: Commit**

```bash
git add start.sh
git commit -m "$(cat <<'EOF'
fix(scripts): make start.sh idempotent and self-cleaning

Auto-cleans stale .pid (kill -0 verification), refuses to start when
another process already holds the port, polls /health for up to 5s
to confirm a fresh start actually came up, and prints the URL/PID
on every run so you can use ./start.sh as a status check.

Refs spec: docs/superpowers/specs/2026-05-04-robust-start-stop-scripts-design.md
EOF
)"
```

---

## Task 2: Rewrite `stop.sh`

**Files:**
- Modify: `stop.sh` (full replacement)

- [ ] **Step 1: Read the existing `stop.sh`**

Run: `cat stop.sh`

Expected: see the current 16-line script that does a single `kill` + `rm .pid`.

- [ ] **Step 2: Replace `stop.sh` with the new version**

Write this exact content to `stop.sh`:

```bash
#!/bin/bash
cd "$(dirname "$0")"

# --- Read PORT from .env (fallback 8000) — same as start.sh ---
PORT=8000
if [ -f .env ]; then
    ENV_PORT=$(grep -E '^PORT=' .env | head -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
    if [ -n "$ENV_PORT" ]; then
        PORT=$ENV_PORT
    fi
fi

# --- Helper: wait until a PID dies, escalate to SIGKILL after timeout ---
wait_for_death() {
    local pid="$1"
    local attempts=10
    local i=0
    while [ "$i" -lt "$attempts" ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.5
        i=$((i + 1))
    done
    kill -9 "$pid" 2>/dev/null || true
    sleep 0.5
    return 1   # had to SIGKILL
}

KILLED_MAIN=""
ESCALATED_MAIN=0

# --- Step 1: handle .pid (supervisor process) ---
if [ -f .pid ]; then
    PID=$(cat .pid)
    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
        echo "Städade stale .pid (PID $PID körde inte)."
        rm -f .pid
    else
        kill "$PID"
        if wait_for_death "$PID"; then
            :   # died gracefully
        else
            ESCALATED_MAIN=1
        fi
        rm -f .pid
        KILLED_MAIN="$PID"
    fi
fi

# --- Step 2: port backstop — catch orphan workers ---
ORPHAN_PIDS=$(lsof -ti:"$PORT" 2>/dev/null)
KILLED_ORPHANS=""
if [ -n "$ORPHAN_PIDS" ]; then
    # shellcheck disable=SC2086
    kill $ORPHAN_PIDS 2>/dev/null || true
    for pid in $ORPHAN_PIDS; do
        wait_for_death "$pid" >/dev/null
    done
    KILLED_ORPHANS=$(echo "$ORPHAN_PIDS" | tr '\n' ',' | sed 's/,$//')
fi

# --- Step 3: report ---
if [ -n "$KILLED_MAIN" ] && [ -n "$KILLED_ORPHANS" ]; then
    if [ "$ESCALATED_MAIN" = "1" ]; then
        echo "Stoppade Sprint Reporter med SIGKILL (PID $KILLED_MAIN). Städade även orphan(s) på port $PORT (PID $KILLED_ORPHANS)."
    else
        echo "Stoppade Sprint Reporter (PID $KILLED_MAIN). Städade även orphan(s) på port $PORT (PID $KILLED_ORPHANS)."
    fi
elif [ -n "$KILLED_MAIN" ]; then
    if [ "$ESCALATED_MAIN" = "1" ]; then
        echo "Stoppade Sprint Reporter med SIGKILL (PID $KILLED_MAIN)."
    else
        echo "Stoppade Sprint Reporter (PID $KILLED_MAIN)."
    fi
elif [ -n "$KILLED_ORPHANS" ]; then
    echo "Städade orphan-process(er) på port $PORT (PID $KILLED_ORPHANS)."
else
    echo "Sprint Reporter kör inte."
fi
```

- [ ] **Step 3: Verify shell syntax is valid**

Run: `bash -n stop.sh`

Expected: exits 0 with no output.

- [ ] **Step 4: Ensure execute bit is set**

Run: `chmod +x stop.sh && ls -l stop.sh`

Expected: line begins with `-rwxr-xr-x`.

- [ ] **Step 5: Manual scenario 5 — stop while running**

Pre-state: start the app: `./start.sh`. Confirm `.pid` exists, process is up, and `lsof -ti:8000` returns at least one PID.

Run: `./stop.sh`

Expected one of:
```
Stoppade Sprint Reporter (PID NNNNN).
```
or (if uvicorn's worker survives the supervisor's SIGTERM):
```
Stoppade Sprint Reporter (PID NNNNN). Städade även orphan(s) på port 8000 (PID MMMMM).
```
After: `ls .pid 2>/dev/null` prints nothing. `lsof -ti:8000` returns nothing. `curl -s http://localhost:8000/health` fails (connection refused).

- [ ] **Step 6: Manual scenario 6 — stop with stale `.pid` + orphan worker**

Pre-state: start the app: `./start.sh`. Then simulate a crash that leaves the worker orphaned (this is the realistic failure mode with `reload=True`):
```
kill -9 $(cat .pid)
sleep 1
lsof -ti:8000   # confirm a worker PID still listens
```
The `.pid` file remains but its process is gone; an orphan worker still holds port 8000.

Run: `./stop.sh`

Expected:
```
Städade stale .pid (PID NNNNN körde inte).
Städade orphan-process(er) på port 8000 (PID MMMMM).
```
After: `ls .pid 2>/dev/null` prints nothing. `lsof -ti:8000` returns nothing.

- [ ] **Step 7: Manual scenario 7 — stop when nothing running**

Pre-state: no `.pid` file, nothing on port 8000. Verify: `ls .pid 2>/dev/null` prints nothing AND `lsof -ti:8000` prints nothing.

Run: `./stop.sh`

Expected:
```
Sprint Reporter kör inte.
```
Exit code 0.

- [ ] **Step 7b: Manual scenario 8 — orphan on port without `.pid`**

Pre-state: simulate the case where someone manually deleted `.pid` but a worker is still alive on port 8000:
```
./start.sh
kill -9 $(cat .pid)
rm .pid
sleep 1
lsof -ti:8000   # worker PID still holds the port
```

Run: `./stop.sh`

Expected:
```
Städade orphan-process(er) på port 8000 (PID MMMMM).
```
After: `lsof -ti:8000` returns nothing.

- [ ] **Step 8: Commit**

```bash
git add stop.sh
git commit -m "$(cat <<'EOF'
fix(scripts): make stop.sh idempotent, self-cleaning, and worker-aware

Detects stale .pid (kill -0) and cleans it instead of failing. On a
live process, sends SIGTERM and polls for up to 5s before escalating
to SIGKILL.

Adds a port-based backstop: after handling .pid, checks lsof -ti:PORT
and kills anything still listening. Catches uvicorn's reload-mode
worker process, which survives SIGTERM to the supervisor and would
otherwise block the next ./start.sh.

Refs spec: docs/superpowers/specs/2026-05-04-robust-start-stop-scripts-design.md
EOF
)"
```

---

## Task 3: End-to-end smoke check

This task confirms the two scripts cooperate cleanly across a full lifecycle. No file changes — just verification.

- [ ] **Step 1: Full lifecycle dry run**

Pre-state: app not running, no `.pid`.

Run, in order:
```
./stop.sh        # expect: "Sprint Reporter kör inte."
./start.sh       # expect: "Startar Sprint Reporter..." then "Sprint Reporter körs på http://localhost:8000 (PID X)."
./start.sh       # expect: "Sprint Reporter kör redan på http://localhost:8000 (PID X)." (same PID)
curl -s http://localhost:8000/health   # expect: {"status":"ok"}
./stop.sh        # expect: "Stoppade Sprint Reporter (PID X)."
./stop.sh        # expect: "Sprint Reporter kör inte."
```

All six commands should produce exactly the indicated output and exit 0.

- [ ] **Step 2: Browser sanity check**

Open `http://localhost:8000` after running `./start.sh`. Expected: the Sprint Reporter UI loads and shows existing teams/sprints from `sprint_data.db` (data unchanged from before).

After confirming, run `./stop.sh`.

- [ ] **Step 3: No commit needed**

This task is verification only.

---

## Task 4: Distribution to the second Mac

This task happens **on the second Mac**, not on the dev machine.

- [ ] **Step 1: Take a local DB backup on the target Mac**

Run on the target Mac, in the project directory:
```
cp sprint_data.db sprint_data.db.before-script-update
```

Expected: a copy of the DB file exists. (Optional but cheap insurance.)

- [ ] **Step 2: Stop the currently running app on the target Mac**

Run: `./stop.sh` (the *old* script — works fine, behavior is compatible).

Expected: process stopped, `.pid` cleaned (or message that nothing was running).

- [ ] **Step 3: Copy the new `start.sh` and `stop.sh` to the target Mac**

Pick one transport:
- AirDrop the two files into the project directory.
- Or: `scp start.sh stop.sh user@target-mac.local:~/path/to/ClickUp-report-app/`
- Or: drop them in via iCloud Drive / Dropbox / USB.

Expected: both files are now in the project root on the target Mac, replacing the old versions.

- [ ] **Step 4: Restore execute bit (in case transport stripped it)**

Run on the target Mac: `chmod +x start.sh stop.sh && ls -l start.sh stop.sh`

Expected: both lines begin with `-rwxr-xr-x`.

- [ ] **Step 5: Verify on target Mac**

Run on the target Mac:
```
./start.sh
```

Expected: `Sprint Reporter körs på http://localhost:PORT (PID X). Loggar: app.log` (where `PORT` is whatever the target's `.env` sets, default 8000).

Open the URL in a browser. Expected: existing teams/sprints visible — DB data intact.

- [ ] **Step 6: No commit needed**

Distribution is operational, not a code change. The commits from Tasks 1–2 already capture the file changes in git.

---

## Self-Review

**Spec coverage:**
- Stale `.pid` handling on start → Task 1, step 2 (lines `if [ -f .pid ]` block) and verified in Task 1, step 7.
- Stale `.pid` handling on stop → Task 2, step 2 (the `kill -0` early return) and verified in Task 2, step 6.
- Port sanity check → Task 1, step 2 (lsof block) and verified in Task 1, step 8.
- Health-poll on fresh start → Task 1, step 2 (curl loop) and implicitly verified in Task 1, step 5.
- Show port/URL in output → Task 1, step 2 (every echo) and verified in every Task 1 scenario.
- `.env` parsing without `source` → Task 1, step 2 (`grep | cut | tr` chain).
- `start.sh` doubles as status check → Task 1, step 6 (re-running while up) and Task 3, step 1 (the second `./start.sh`).
- Distribution to second Mac → Task 4 covers all spec points (chmod, optional backup, post-copy verification).

**Placeholder scan:** No "TBD", "TODO", "implement later", or "appropriate error handling" anywhere. All commands and expected outputs are concrete.

**Type/name consistency:** Variable names match across both scripts (`PID`, `PORT`, `URL`, `ATTEMPTS`, `i`, `NEW_PID`). Function names: none — scripts are top-level. File paths consistent: `start.sh`, `stop.sh`, `.pid`, `app.log`, `.env`, `sprint_data.db`.

**Edge case the spec flagged as known limitation:** PID reuse by an unrelated process after a crash. Documented in spec, not handled here intentionally — port sanity check provides a partial backstop.
