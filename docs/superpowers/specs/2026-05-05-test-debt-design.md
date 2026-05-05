# Test Debt Cleanup (Initiative 1B)

## Context

The Sprint Reporter app has 17 failing tests in `tests/`. None of them are real bugs — production code is correct. They're all stale test expectations: tests written against earlier signatures and behaviors, never updated as features evolved (workspace_id additions, capacity_mode column, multi-assignee formatting, daily-progress points/hours fields).

Before Initiatives 1A (observability) and 3 (OAuth) shipped, these failures were ignored and the suite ran with `pytest --ignore=` workarounds locally. After OAuth landed, the auth-suite added 65 green tests on top of this baseline, so the team test count is now 17 fail / 65 pass. The 17 reds make CI noise and obscure real regressions in future work.

## Problem

Three concrete pains:

1. **CI signal is broken.** `pytest tests/` exits non-zero on every commit. Future broken tests blend in with the 17 baseline failures and slip through review.
2. **Editing safety is reduced.** When refactoring a service, you can't trust the test suite to flag a regression — too many existing reds, no easy diff.
3. **Newcomer confusion.** A developer running `pytest` locally sees 17 failures and assumes the project is broken, when in reality production code is fine.

## Goal

After this initiative:

1. `pytest tests/` exits 0. All 82 tests pass.
2. No production code changes — the failures are test-side drift.
3. CI signal restored: any new failure is a real regression worth investigating.

## Non-Goals

- **No new test coverage.** Adding tests for carry-over detection, scope-change handling, workspace scoping, assignee-hours JSON, etc. is out of scope. YAGNI — write tests when bugs in those areas surface.
- **No test-framework upgrade.** No move to pytest-mock, no adoption of `respx` for httpx mocking, no test refactor to remove module-reload fixtures.
- **No production code changes** to make tests easier to maintain. If a test is awkward, leave it awkward — out-of-scope for this initiative.
- **No green-by-deletion.** We fix tests, not delete them. (Exception: the one strict-equality column-set assertion that's been brittle across multiple migrations — relaxing it to a subset check is the right design, not deletion.)

## Design

### Failure cluster 1: `create_team` signature drift (11 tests)

Production signature today (`src/services/team_service.py:7`):
```python
def create_team(name: str, workspace_id: str, space_id: str, folder_id: str,
                metric_type: str = "task_count", capacity_mode: str = "individual",
                sprint_length_days: int = 14, workspace_id_new: str | None = None)
```

Tests still call:
```python
create_team("T", "s", "f")           # 3 positional args — missing folder_id
create_team("Test Team", "space1", "folder1")  # 3 positional, same gap
```

**Fix:** add the missing `workspace_id` positional in every test call. Picking a sensible default value (`"ws_test"` or `"workspace_1"`) is fine — these tests don't assert on workspace_id, they're just exercising sprint/snapshot/trend behaviors with a parent team row.

Files touched:
- `tests/test_snapshot_service.py` — 6 calls
- `tests/test_sprint_service.py` — 5 calls
- `tests/test_trend_service.py` — 1 call (and any helper functions in conftest if shared)

### Failure cluster 2: `teams` table column-set assertion (1 test)

`tests/test_database.py::test_teams_table_columns` asserts column equality:
```python
assert columns == {"id", "name", "clickup_space_id", "clickup_folder_id",
                   "metric_type", "sprint_length_days", "created_at"}
```

The `teams` table has accumulated 4 columns since this test was written: `clickup_workspace_id` (existing pre-OAuth), `capacity_mode`, `workspace_id` (Task 1 of OAuth), and the assertion was never updated. Strict equality is brittle for an evolving schema.

**Fix:** relax to `issuperset` — assert that the *required* columns exist, not that the column set is exactly those. This is the right pattern for migration-friendly schemas:

```python
required = {"id", "name", "clickup_space_id", "clickup_folder_id",
            "metric_type", "sprint_length_days", "created_at"}
assert required.issubset(columns)
```

This is the only place we make a structural test-design change; everything else is value updates.

### Failure cluster 3: AsyncMock Python 3.12 incompat (3 tests)

`tests/test_clickup_client.py` has 3 tests that mock httpx like this:
```python
mock_response = AsyncMock()
mock_response.json.return_value = {"teams": [...]}
```

In Python 3.12+, `AsyncMock`'s child attributes are also `AsyncMock` by default — so `mock_response.json()` returns a coroutine, not a dict. Production code calls `response.json()` synchronously (correct, since httpx Response is sync), so the mock chain breaks.

**Fix:** the same pattern we used in Task 7 of OAuth — replace `mock_response.json.return_value = X` with `mock_response.json = MagicMock(return_value=X)`. Add `MagicMock` to the imports.

Affected tests in `tests/test_clickup_client.py`:
- `test_get_spaces`
- `test_get_folder_lists`
- `test_get_list_tasks_handles_pagination`

### Failure cluster 4: multi-assignee format (1 test)

`tests/test_clickup_client.py::test_extract_task_data` constructs a task with two assignees:
```python
"assignees": [{"username": "Anna"}, {"username": "Erik"}]
```
and asserts `extracted["assignee_name"] == "Anna"`.

The production `extract_task_data` (`src/clickup_client.py:149`) joins multi-assignee with `, `: `"Anna, Erik"`. The test was written for single-assignee behavior and never updated when multi-assignee support was added.

**Fix:** update the assertion to `"Anna, Erik"`.

### Failure cluster 5: `record_daily_progress` signature drift (1 test)

`tests/test_snapshot_service.py::test_record_daily_progress` calls:
```python
record_daily_progress(sprint_id, 5, 2)
```

Current signature (`src/services/snapshot_service.py:56`):
```python
def record_daily_progress(sprint_id, total_tasks, completed_tasks,
                          total_points=None, completed_points=None,
                          total_hours=None, completed_hours=None)
```

3 positional args still works (the new fields are kwargs with defaults), so why does this fail? Looking at the failure trace: it's actually a downstream `create_team` call in the same test that fails first. Once cluster 1 is fixed, this test should pass on its own.

**Fix:** no separate change needed — covered by cluster 1.

### Failure cluster recap

After all fixes, the suite should be `82 passed, 0 failed`. The change is mechanical and test-only — production code is untouched.

## Files changed

| File | Action |
|---|---|
| `tests/test_snapshot_service.py` | Add `workspace_id` arg to all `create_team` calls |
| `tests/test_sprint_service.py` | Add `workspace_id` arg to all `create_team` calls |
| `tests/test_trend_service.py` | Add `workspace_id` arg to all `create_team` calls |
| `tests/test_database.py` | Relax `test_teams_table_columns` to `issubset` |
| `tests/test_clickup_client.py` | Switch `.json` mocks to `MagicMock(return_value=…)` (3 tests); update `test_extract_task_data` assertion to `"Anna, Erik"` |

No production code changes. No new dependencies. No new tests.

## Verification

```bash
SESSION_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  ./.venv/bin/pytest tests/ -v
```

Expected: `82 passed, 0 failed, 0 errors`.

## Risk

Low. Test-only changes. If we accidentally introduce a regression, it shows up as a *new* failure in the same suite — easy to spot and revert.

## Distribution

No deploy step. Changes are picked up by next CI run. Local devs see green suite on next pull.
