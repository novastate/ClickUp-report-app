import pytest
from src.services.team_service import create_team
from src.services.sprint_service import create_sprint_from_list, close_forecast, close_sprint
from src.services.snapshot_service import save_forecast_snapshot, record_daily_progress
from src.services.trend_service import get_team_trends, calculate_on_track_status

def _setup_closed_sprint(team_id, list_id, name, forecast_count, completed_count, points_total, points_done):
    sprint = create_sprint_from_list(team_id, list_id, name)
    tasks = [
        {"task_id": f"{list_id}_t{i}", "task_name": f"Task {i}", "task_status": "to do",
         "assignee_name": "Anna", "points": points_total / forecast_count, "hours": None}
        for i in range(forecast_count)
    ]
    save_forecast_snapshot(sprint["id"], tasks)
    close_forecast(sprint["id"])
    record_daily_progress(sprint["id"], total_tasks=forecast_count, completed_tasks=completed_count,
                          total_points=points_total, completed_points=points_done)
    close_sprint(sprint["id"])
    return sprint

def test_get_team_trends(test_db):
    team = create_team("T", "ws_test", "s", "f")
    _setup_closed_sprint(team["id"], "l1", "Iteration 1 (1/1 - 14/1)", 10, 8, 20, 16)
    _setup_closed_sprint(team["id"], "l2", "Iteration 2 (15/1 - 28/1)", 12, 10, 24, 20)
    trends = get_team_trends(team["id"])
    assert len(trends["sprints"]) == 2
    assert trends["avg_completion_rate"] == pytest.approx(0.817, abs=0.01)

def test_on_track_status():
    assert calculate_on_track_status(remaining=8, ideal_remaining=10) == "ahead"
    assert calculate_on_track_status(remaining=10, ideal_remaining=10) == "on_track"
    assert calculate_on_track_status(remaining=12, ideal_remaining=10) == "behind"
    assert calculate_on_track_status(remaining=9.5, ideal_remaining=10) == "on_track"
