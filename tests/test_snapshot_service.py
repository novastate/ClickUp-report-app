import pytest
from src.database import init_db, get_connection
from src.services.team_service import create_team
from src.services.sprint_service import create_sprint_from_list, close_forecast
from src.services.snapshot_service import (
    save_forecast_snapshot,
    get_forecast_snapshot,
    record_daily_progress,
    detect_scope_changes,
    get_scope_changes,
    get_daily_progress_history,
)

def _make_tasks(ids_and_statuses):
    return [
        {"task_id": tid, "task_name": f"Task {tid}", "task_status": status,
         "assignee_name": "Anna", "points": 2, "hours": 1}
        for tid, status in ids_and_statuses
    ]

def test_save_and_get_forecast_snapshot(test_db):
    team = create_team("T", "ws_test", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    save_forecast_snapshot(sprint["id"], tasks)
    snapshot = get_forecast_snapshot(sprint["id"])
    assert len(snapshot) == 3
    assert {t["task_id"] for t in snapshot} == {"t1", "t2", "t3"}

def test_record_daily_progress(test_db):
    team = create_team("T", "ws_test", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    record_daily_progress(sprint["id"], total_tasks=10, completed_tasks=3,
                          total_points=20, completed_points=6,
                          total_hours=40, completed_hours=12)
    history = get_daily_progress_history(sprint["id"])
    assert len(history) == 1
    assert history[0]["completed_tasks"] == 3

def test_detect_scope_changes_added(test_db):
    team = create_team("T", "ws_test", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do"), ("t2", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    current_tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    changes = detect_scope_changes(sprint["id"], current_tasks)
    assert len(changes) == 1
    assert changes[0]["change_type"] == "added"
    assert changes[0]["task_id"] == "t3"

def test_detect_scope_changes_removed(test_db):
    team = create_team("T", "ws_test", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    current_tasks = _make_tasks([("t1", "to do"), ("t2", "to do")])
    changes = detect_scope_changes(sprint["id"], current_tasks)
    assert len(changes) == 1
    assert changes[0]["change_type"] == "removed"
    assert changes[0]["task_id"] == "t3"

def test_closed_sprint_task_list_reconstruction(test_db):
    team = create_team("T", "ws_test", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do"), ("t2", "to do"), ("t3", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    current_tasks = _make_tasks([("t1", "complete"), ("t2", "in progress"), ("t4", "to do")])
    detect_scope_changes(sprint["id"], current_tasks)
    snapshot = get_forecast_snapshot(sprint["id"])
    changes = get_scope_changes(sprint["id"])
    added_ids = {c["task_id"] for c in changes if c["change_type"] == "added"}
    removed_ids = {c["task_id"] for c in changes if c["change_type"] == "removed"}
    assert "t4" in added_ids
    assert "t3" in removed_ids
    assert len(snapshot) == 3
    all_ids = {t["task_id"] for t in snapshot} | added_ids
    assert all_ids == {"t1", "t2", "t3", "t4"}

def test_detect_scope_changes_no_duplicates(test_db):
    team = create_team("T", "ws_test", "s", "f")
    sprint = create_sprint_from_list(team["id"], "l1", "Iteration 1 (1/1 - 14/1)")
    forecast_tasks = _make_tasks([("t1", "to do")])
    save_forecast_snapshot(sprint["id"], forecast_tasks)
    current_tasks = _make_tasks([("t1", "to do"), ("t2", "to do")])
    detect_scope_changes(sprint["id"], current_tasks)
    changes = detect_scope_changes(sprint["id"], current_tasks)
    assert len(changes) == 0
    all_changes = get_scope_changes(sprint["id"])
    assert len(all_changes) == 1
