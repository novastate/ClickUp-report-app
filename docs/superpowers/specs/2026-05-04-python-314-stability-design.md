# Python 3.14 Stability

> **Implementation note (post-hoc):** During implementation we discovered that the Homebrew Python 3.14.4 build on this Mac has a broken `pyexpat` C extension (linked against an older system `libexpat`), which makes `pip install` fail and `venv` recreation unsafe. Rather than chase a system-level fix, we **downgraded `.venv` to Python 3.12.12** — pure Python, well-supported, no Homebrew bug. Consequence: the `pytest-asyncio` bump (Change 2 below) is no longer needed — 0.24.0 works fine on Python 3.12 — and was reverted. Only the `app.py` lifespan migration was actually applied. Test failures attributable to Python 3.14 are gone by virtue of not running Python 3.14. Pre-existing test failures from `src/ ↔ tests/` signature drift remain (separate workstream).

## Context

The project's `.venv` is built with Python 3.14. Two things in the codebase produce deprecation warnings or outright failures on this Python version:

1. **`app.py:72,77`** uses `@app.on_event("startup")` and `@app.on_event("shutdown")` — deprecated in FastAPI since ~0.93.0 (in favor of the `lifespan` context manager). The decorators still work today but produce `DeprecationWarning` on every app start, and FastAPI documents them as "subject to removal in a future release."

2. **`pytest-asyncio==0.24.0`** (pinned in `requirements.txt`) calls `asyncio.get_event_loop_policy()`, a function that has been **removed in Python 3.14**. This causes 17 of 22 tests to fail with `AttributeError: 'coroutine'…` and a flood of `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited`.

Verified that the 17 test failures are **pre-existing** — they reproduce on commit `d9dd971` (last commit before any of this session's work). They are not regressions from the start/stop or deploy work.

## Problem

- Runtime: deprecation warnings on every startup, with eventual removal looming.
- Tests: a third of the test suite is unrunnable on the dev Mac, which means we have no automated sanity check before deploying. This blocks any future test-suite cleanup (#3 in the larger optimization roadmap).

## Goal

Ship a Python 3.14-compatible runtime and test environment in a single focused change. After this:

- App starts with no `DeprecationWarning` from our code in `app.log`.
- `pytest -q` runs to completion without `AttributeError` from `pytest-asyncio`'s removed-API calls. Some tests may still fail due to unrelated signature drift between `src/` and `tests/`, but those failures will be **about the test code itself**, not about the runner.

## Non-Goals

- **Fixing the test signature drift** (e.g. `test_create_sprint`'s `TypeError: create_t…`). That is the separate "test debt" workstream (#3).
- **Refactoring `app.py`** beyond the lifespan migration. The current ordering of imports, scheduler setup, router includes, and static-files mount stays exactly as is.
- **Touching `scheduler` / `daily_snapshot_job`.** It works today; out of scope.
- **Downgrading Python.** Sticking with 3.14 — moving forward, not pinning to 3.12.

## Design

### Change 1: `app.py` — migrate to `lifespan`

Replace this block (lines 72–79):

```python
@app.on_event("startup")
def startup():
    init_db(DB_PATH)
    scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()
```

…with a `lifespan` async context manager declared **before** `app = FastAPI(...)`:

```python
from contextlib import asynccontextmanager

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

Two notes on the order of operations:

- `lifespan` must be declared before `app = FastAPI(...)` so it can be passed in at construction. The current `app.py` builds `app` at the top, then defines `daily_snapshot_job` (which references `app`), then attaches event handlers. After this change, `app` is still constructed near the top — just on a single line that now also takes `lifespan=...`. No reordering of `daily_snapshot_job`, scheduler setup, or routers is needed.
- The function `lifespan` must be defined **above** the `app = FastAPI(...)` line. We will move the `app = FastAPI(...)` assignment a few lines down so this works without forward references.

### Change 2: `requirements.txt` — bump `pytest-asyncio`

Single line change:

```diff
-pytest-asyncio==0.24.0
+pytest-asyncio==1.3.0
```

`pytest-asyncio==1.3.0` declares Python 3.14 support in its PyPI classifiers and uses the modern `asyncio.new_event_loop()` API instead of the removed `get_event_loop_policy()`.

### Change 3: Apply the new dependency to the existing `.venv`

```bash
.venv/bin/pip install -r requirements.txt
```

This is an in-place upgrade. We are not recreating the venv (Python 3.14's `ensurepip` bug means recreation is not currently safe on this Mac).

If pip itself reports errors during the upgrade, fall back to:

```bash
.venv/bin/pip install --upgrade pytest-asyncio==1.3.0
```

### `pytest-asyncio` 0.x → 1.x compatibility

Major-version bump, so API breaks are possible. The largest behavior change in 1.x is that `@pytest.mark.asyncio` is required on async tests in `strict` mode (the new default).

- During implementation, grep `tests/` for `@pytest.mark.asyncio`. If existing async tests use it, no further action. If not, either add it to those tests **or** set `asyncio_mode = auto` in a `pytest.ini` / `pyproject.toml`.
- Either way, this only affects tests that were *already* failing — we cannot make the test suite worse.

## Verification

Run on the dev Mac:

1. **App startup:** `./stop.sh && ./start.sh`. Then `grep -i 'DeprecationWarning' app.log | grep -v 'pytest_asyncio'`. Expected: no matches from `app.py`. (Warnings from third-party packages are out of scope.)

2. **Health endpoint still works:** `curl -s http://localhost:8000/health` → `{"status":"ok"}`.

3. **Lifespan ran startup:** confirm DB tables exist and scheduler is running. `sqlite3 sprint_data.db ".tables"` shows the expected tables; logs show no scheduler errors.

4. **Lifespan runs shutdown cleanly:** `./stop.sh`. App stops within 5s; no scheduler-shutdown error in `app.log`.

5. **pytest works:** `.venv/bin/pytest -q`. Expected: zero occurrences of `AttributeError: 'coroutine'` and zero `RuntimeWarning: coroutine '…' was never awaited` related to `pytest-asyncio`. Some test failures may remain (signature-drift) — those are out of scope and we report them but do not fix them.

6. **DB integrity:** `shasum sprint_data.db` before and after the app restart cycle — must be identical (we don't expect lifespan to write anything to the DB outside `init_db`'s idempotent ALTER TABLE block).

## Edge Cases

- **`app.py` import order.** `app = FastAPI(...)` is currently at line 15. After this change it moves a few lines further down (after `lifespan` is defined). The router includes and `app.mount(...)` calls following it must continue to work — no reordering of those needed.
- **The `daily_snapshot_job` async function** at the top of `app.py` references `app` only indirectly (through the scheduler). It does not need to be moved.
- **`FastAPI` is already imported** at the top of `app.py`. No additional import needed beyond `from contextlib import asynccontextmanager`.
- **Pre-existing test failures unrelated to this change** (signature drift on `create_team`, `test_teams_table_columns`, etc.) will remain. They are out of scope and documented as the deferred "test debt" workstream.
- **`pip install --dry-run` crashes on Python 3.14.** Already observed during reconnaissance — unrelated to this change. Real `pip install -r requirements.txt` works (verified during the deploy-bundle sandbox tests).

## Distribution

Two files change: `app.py` and `requirements.txt`. Both will travel to the live Mac via the next `./make-deploy-bundle.sh` + `./apply-deploy.sh` cycle. `apply-deploy.sh` already detects `requirements.txt` changes and runs `pip install -r requirements.txt` in the live venv automatically. No special distribution steps needed.
