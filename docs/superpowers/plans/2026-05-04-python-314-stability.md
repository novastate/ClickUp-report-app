# Python 3.14 Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the runtime and test environment Python 3.14-clean by migrating `@app.on_event` to `lifespan` and bumping `pytest-asyncio` from 0.24.0 to 1.3.0.

**Architecture:** Two file edits (`app.py`, `requirements.txt`) plus an in-place venv upgrade. `app.py` change is structural (`app = FastAPI(...)` moves a few lines down so `lifespan` can be defined first). `requirements.txt` change is one line.

**Tech Stack:** Python 3.14, FastAPI, pytest-asyncio, in-place pip upgrade.

**Spec:** `docs/superpowers/specs/2026-05-04-python-314-stability-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Bump `pytest-asyncio` from 0.24.0 to 1.3.0. |
| `app.py` | Modify | Replace two `@app.on_event` decorators with a single `lifespan` async context manager. Move `app = FastAPI(...)` a few lines down so `lifespan` is in scope. |
| (`.venv/`) | In-place upgrade | Apply the new pinned dependency without recreating the venv (Python 3.14 ensurepip bug makes recreation unsafe). |

No code in `src/`, `tests/`, or anywhere else is touched. The pre-existing test signature drift remains as deferred work.

---

## Task 1: Bump `pytest-asyncio` and capture baseline

**Files:**
- Modify: `requirements.txt:8`
- (`.venv/` in-place upgrade)

This task does *not* touch `app.py`. The point is to first establish a clean test-runner baseline before doing the app change.

- [ ] **Step 1: Capture pre-change failure count**

Run: `.venv/bin/pytest -q 2>&1 | tail -3`

Expected: a line like `17 failed, 5 passed, 907 warnings in 0.29s`. Note both numbers down — they are the baseline.

- [ ] **Step 2: Update `requirements.txt`**

In `/Users/collin/dev/Projects/ClickUp-report-app/requirements.txt`, change exactly this line (currently line 8):

```diff
-pytest-asyncio==0.24.0
+pytest-asyncio==1.3.0
```

Verify: `grep pytest-asyncio requirements.txt` should print `pytest-asyncio==1.3.0`.

- [ ] **Step 3: Apply to existing venv**

Run: `.venv/bin/pip install -r requirements.txt 2>&1 | tail -10`

Expected: `Successfully installed pytest-asyncio-1.3.0` (other packages already at requested versions, so they are skipped). If pip itself errors out (Python 3.14 has known pip bugs on some flags), fall back to:

```bash
.venv/bin/pip install --upgrade pytest-asyncio==1.3.0
```

Verify: `.venv/bin/pip show pytest-asyncio | grep Version` → `Version: 1.3.0`.

- [ ] **Step 4: Run the test suite again**

Run: `.venv/bin/pytest -q 2>&1 | tail -5`

Expected: failure count *should drop* (the 3.14-related `AttributeError` failures are gone). Some failures may remain due to test signature drift (`TypeError: create_t...` etc.) — those are the deferred test-debt issue and are out of scope. Note the new failure count.

- [ ] **Step 5: Verify the specific 3.14 errors are gone**

Run:

```bash
.venv/bin/pytest -q 2>&1 | grep -cE "AttributeError: 'coroutine'|asyncio\.get_event_loop_policy"
```

Expected: `0` (zero matches). The `pytest-asyncio` library is no longer the cause of failures.

- [ ] **Step 6: Spot-check that the strict-mode default did not strand any async tests**

`pytest-asyncio` 1.x defaults to `strict` mode, which requires `@pytest.mark.asyncio` on async tests. Verify that all async test functions are decorated:

```bash
grep -nE "^async def test_" tests/*.py | while IFS=: read file line _; do
    prev=$((line - 1))
    marker=$(sed -n "${prev}p" "$file")
    case "$marker" in
        *@pytest.mark.asyncio*) echo "OK: $file:$line" ;;
        *) echo "MISSING marker: $file:$line — '$marker'" ;;
    esac
done
```

Expected: all `OK:` lines, no `MISSING marker:` lines. (Reconnaissance shows `tests/test_clickup_client.py` already has all four markers in place; this step confirms no other file added an undecorated async test.)

If any `MISSING marker:` appears, **stop and report**. The plan does not cover adding markers to tests; that's test-debt territory.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt
git commit -m "$(cat <<'EOF'
fix(deps): bump pytest-asyncio 0.24 → 1.3 for Python 3.14 support

0.24 calls asyncio.get_event_loop_policy(), removed in Python 3.14,
which was producing 17 test-runner failures plus a flood of "coroutine
was never awaited" warnings. 1.3.0 declares Python 3.14 support in its
PyPI classifiers and uses asyncio.new_event_loop() internally.

Pre-existing test failures from src/ ↔ tests/ signature drift remain;
they're a separate workstream.

Refs spec: docs/superpowers/specs/2026-05-04-python-314-stability-design.md
EOF
)"
```

---

## Task 2: Migrate `app.py` to `lifespan`

**Files:**
- Modify: `app.py:1-15` (add import, move `app = FastAPI(...)` and define `lifespan` before it) and `app.py:72-79` (remove `@app.on_event` blocks).

- [ ] **Step 1: Read current `app.py` to confirm baseline**

Run: `wc -l app.py && grep -nE "(on_event|FastAPI|asynccontextmanager)" app.py`

Expected:
- `87 app.py`
- `app.py:2:from fastapi import FastAPI`
- `app.py:15:app = FastAPI(title="Sprint Reporter")`
- `app.py:72:@app.on_event("startup")`
- `app.py:77:@app.on_event("shutdown")`
- *No* `asynccontextmanager` import yet.

- [ ] **Step 2: Replace the imports + `app` assignment block**

In `app.py`, the current lines 1–15 are:

```python
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import HOST, PORT, DB_PATH
from src.database import init_db
from src.routes import teams, sprints, clickup_proxy, pages
import os
from apscheduler.schedulers.background import BackgroundScheduler
from src.config import DAILY_SNAPSHOT_TIME, get_clickup_api_key
from src.services.snapshot_service import detect_scope_changes, record_daily_progress
from src.clickup_client import ClickUpClient
from src.database import get_connection
import asyncio

app = FastAPI(title="Sprint Reporter")
```

Replace the **entire block (lines 1–15 inclusive)** with:

```python
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import HOST, PORT, DB_PATH
from src.database import init_db
from src.routes import teams, sprints, clickup_proxy, pages
import os
from apscheduler.schedulers.background import BackgroundScheduler
from src.config import DAILY_SNAPSHOT_TIME, get_clickup_api_key
from src.services.snapshot_service import detect_scope_changes, record_daily_progress
from src.clickup_client import ClickUpClient
from src.database import get_connection
import asyncio


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    init_db(DB_PATH)
    scheduler.start()
    yield
    # shutdown
    scheduler.shutdown()


app = FastAPI(title="Sprint Reporter", lifespan=lifespan)
```

Notes:
- The `from contextlib import asynccontextmanager` line is the only new import.
- `lifespan` references `scheduler`, which is defined later (around line 59 of the original file, line ~71 after this edit). That's fine because `lifespan` is only *called* at app startup, by which time `scheduler` is fully defined at module level.

- [ ] **Step 3: Remove the two `@app.on_event` blocks**

The current lines 72–79 are:

```python
@app.on_event("startup")
def startup():
    init_db(DB_PATH)
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()
```

**Delete that entire block** (8 lines). The blank line above and the `@app.get("/health")` line below should stay; the result around that area should look like:

```python
# Only mount static files if the directory exists
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Verify the file parses**

Run: `.venv/bin/python -c "import ast; ast.parse(open('app.py').read()); print('OK')"`

Expected: `OK`. Any `SyntaxError` here means the edit went sideways — stop and re-check the diff.

- [ ] **Step 5: Verify the structure is what we expect**

Run:

```bash
grep -cE "@app\.on_event" app.py        # Expected: 0
grep -cE "asynccontextmanager" app.py   # Expected: 1
grep -cE "lifespan=lifespan" app.py     # Expected: 1
grep -cE "async def lifespan" app.py    # Expected: 1
```

All four counts must match. Anything else means the edit didn't land cleanly.

- [ ] **Step 6: Restart the app via the existing scripts**

```bash
./stop.sh
./start.sh
```

Expected: `start.sh` reports `Sprint Reporter körs på http://localhost:8000 (PID X)` and the `/health` poll succeeds. If it fails, run `tail -30 app.log` and stop.

- [ ] **Step 7: Verify no `DeprecationWarning` from our code**

Run:

```bash
grep -nE 'DeprecationWarning' app.log | grep -v 'pytest' | head -10
```

Expected: zero matches whose path is `app.py`. (Third-party deprecation warnings from packages we don't own are out of scope.)

- [ ] **Step 8: Verify health endpoint and a couple of real routes still work**

```bash
curl -s http://localhost:8000/health
echo ""
curl -s -o /dev/null -w "GET /  → %{http_code}\n" http://localhost:8000/
```

Expected:
- `{"status":"ok"}`
- `GET /  → 200`

- [ ] **Step 9: Verify scheduler started cleanly**

Run: `grep -E "scheduler|APScheduler" app.log | head -5`

Expected: at least one line like `Scheduler started` or `Adding job tentatively`. **No** ERROR or Traceback lines.

- [ ] **Step 10: Test lifespan shutdown path**

Run: `./stop.sh`

Expected: `Stoppade Sprint Reporter (PID X)` and no shutdown-related Traceback in `app.log`. Then verify:

```bash
tail -20 app.log | grep -iE "shutdown|error|traceback" || echo "(clean shutdown)"
```

Expected: `(clean shutdown)` or only an informational APScheduler "Scheduler has been shut down" line — never a Traceback.

- [ ] **Step 11: Re-run pytest to confirm we didn't regress**

Run: `.venv/bin/pytest -q 2>&1 | tail -5`

Expected: failure count is the same as Task 1 step 4 (or lower). Capture the count to compare against Task 1's baseline.

- [ ] **Step 12: Commit**

```bash
git add app.py
git commit -m "$(cat <<'EOF'
refactor(app): migrate @app.on_event to lifespan context manager

@app.on_event has been deprecated in FastAPI since ~0.93.0 and is
documented as subject to removal. The new asynccontextmanager-based
lifespan is the supported replacement.

Functionally equivalent: init_db + scheduler.start on enter, scheduler.shutdown
on exit. No behavior change at runtime; eliminates two DeprecationWarnings
on every app start.

Refs spec: docs/superpowers/specs/2026-05-04-python-314-stability-design.md
EOF
)"
```

---

## Task 3: End-to-end smoke + DB integrity check

This task introduces no new code. It exercises the full restart cycle end-to-end against the *real* DB to confirm nothing was disturbed.

- [ ] **Step 1: Capture DB hash before restart**

```bash
DB_BEFORE=$(shasum sprint_data.db | awk '{print $1}')
echo "Pre-restart DB hash: $DB_BEFORE"
```

- [ ] **Step 2: Stop the app cleanly**

Run: `./stop.sh`

Expected: `Stoppade Sprint Reporter (PID X).` or `Sprint Reporter kör inte.`

- [ ] **Step 3: Start the app fresh**

Run: `./start.sh`

Expected: `Sprint Reporter körs på http://localhost:8000 (PID X). Loggar: app.log`

- [ ] **Step 4: Verify lifespan ran startup successfully**

Run:

```bash
sqlite3 sprint_data.db "SELECT COUNT(*) FROM teams"
sqlite3 sprint_data.db "SELECT COUNT(*) FROM sprints"
curl -s http://localhost:8000/health
```

Expected: nonzero counts on both queries (the existing data is intact), and `{"status":"ok"}` from curl.

- [ ] **Step 5: Stop again and capture DB hash after**

```bash
./stop.sh
DB_AFTER=$(shasum sprint_data.db | awk '{print $1}')
echo "Post-restart DB hash: $DB_AFTER"

[ "$DB_BEFORE" = "$DB_AFTER" ] && echo "✓ DB unchanged across restart" || echo "✗ DB hash changed (was $DB_BEFORE, is now $DB_AFTER)"
```

Expected: ✓ DB unchanged.

(`init_db` runs idempotent `CREATE IF NOT EXISTS` and `ALTER TABLE … ADD COLUMN` in try/except — none should write any rows. There is one `UPDATE scope_changes SET sprint_day = ...` with a `WHERE sprint_day IS NULL` guard, which only writes if there are unfilled rows. If you've already run the app since that migration was added, this guard is satisfied and the UPDATE is a no-op. If the hash *does* change, the diff will be that backfill.)

- [ ] **Step 6: Restart the app for normal use**

Run: `./start.sh`

Expected: app comes up; baseline established for any next session.

- [ ] **Step 7: No commit needed**

This task is verification only.

---

## Self-Review

**Spec coverage:**
- Spec change 1 (`app.py` → lifespan) → Task 2, steps 2–5 implement, steps 6–10 verify. ✓
- Spec change 2 (`requirements.txt` bump) → Task 1, steps 2–3. ✓
- Spec change 3 (in-place venv upgrade) → Task 1, step 3, including pip-fallback note. ✓
- Spec verification 1 (`DeprecationWarning` gone from `app.py`) → Task 2, step 7. ✓
- Spec verification 2 (health endpoint works) → Task 2, step 8 + Task 3, step 4. ✓
- Spec verification 3 (lifespan startup runs DB init + scheduler) → Task 2, step 9 + Task 3, step 4. ✓
- Spec verification 4 (lifespan shutdown clean) → Task 2, step 10. ✓
- Spec verification 5 (pytest works without 3.14 errors) → Task 1, step 5. ✓
- Spec verification 6 (DB integrity across restart) → Task 3, steps 1–5. ✓
- Spec edge case (pytest-asyncio strict mode requires markers) → Task 1, step 6. ✓
- Spec edge case (`pip --dry-run` is broken on 3.14) → Task 1, step 3 includes a pip fallback. ✓
- Spec out-of-scope item (test signature drift) — explicitly noted in Task 1 step 4 and Task 2 step 11 as deferred. ✓

**Placeholder scan:** No "TBD" / "TODO" / "appropriate error handling" / "similar to Task N" / "implement later" anywhere. All commands are concrete, all expected outputs are specific.

**Type/name consistency:** Used `lifespan` consistently as the function name, `asynccontextmanager` consistently as the imported decorator. `app = FastAPI(title="Sprint Reporter", lifespan=lifespan)` is the only `FastAPI(...)` call after the change. The deletion of `@app.on_event("startup")` and `@app.on_event("shutdown")` is described both in absolute terms (line range) and structurally (verification grep counts in step 5).

**Inline fix made during review:** Task 1 step 6 originally had a one-liner shell expression that wasn't quite right; I replaced it with a clearer per-file loop that produces explicit OK / MISSING marker output and added a stop-condition.
