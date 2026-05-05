import pytest
from datetime import datetime
from src.database import init_db, get_connection
from src.services.team_service import create_team
from src.services.sprint_service import (
    create_sprint_from_list,
    get_sprint,
    get_team_sprints,
    close_forecast,
    close_sprint,
    get_sprint_status,
    parse_iteration_dates,
)

def test_parse_iteration_dates():
    name = "Iteration 6 (9/3 - 22/3)"
    start, end = parse_iteration_dates(name, 2026)
    assert start.month == 3
    assert start.day == 9
    assert end.month == 3
    assert end.day == 22

def test_parse_iteration_dates_cross_year():
    name = "Iteration 1 (23/12 - 5/1)"
    start, end = parse_iteration_dates(name, 2025)
    assert start.month == 12
    assert end.month == 1
    assert end.year == 2026

def test_create_sprint(test_db):
    team = create_team("Test Team", "ws_test", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    assert sprint["name"] == "Iteration 6 (9/3 - 22/3)"
    assert sprint["clickup_list_id"] == "list_1"

def test_sprint_status_planning(test_db):
    team = create_team("Test Team", "ws_test", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    assert get_sprint_status(sprint) == "planning"

def test_close_forecast_changes_status(test_db):
    team = create_team("Test Team", "ws_test", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    updated = close_forecast(sprint["id"])
    assert updated["forecast_closed_at"] is not None
    assert get_sprint_status(updated) == "active"

def test_close_sprint_changes_status(test_db):
    team = create_team("Test Team", "ws_test", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    close_forecast(sprint["id"])
    updated = close_sprint(sprint["id"])
    assert updated["closed_at"] is not None
    assert get_sprint_status(updated) == "closed"

def test_cannot_close_sprint_before_forecast(test_db):
    team = create_team("Test Team", "ws_test", "space1", "folder1")
    sprint = create_sprint_from_list(team["id"], "list_1", "Iteration 6 (9/3 - 22/3)")
    with pytest.raises(ValueError, match="forecast"):
        close_sprint(sprint["id"])
