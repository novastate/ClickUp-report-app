import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.clickup_client import ClickUpClient

@pytest.mark.asyncio
async def test_get_spaces():
    mock_response = AsyncMock()
    mock_response.json = MagicMock(return_value={"teams": [{"id": "123", "name": "SGIT"}]})
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        client = ClickUpClient("fake_key")
        result = await client.get_workspaces()
        assert result[0]["name"] == "SGIT"
        mock_get.assert_called_once()

@pytest.mark.asyncio
async def test_get_folder_lists():
    mock_response = AsyncMock()
    mock_response.json = MagicMock(return_value={
        "lists": [
            {"id": "list_1", "name": "Iteration 5 (23/2 - 8/3)", "task_count": 10},
            {"id": "list_2", "name": "Backlog", "task_count": 20},
        ]
    })
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        client = ClickUpClient("fake_key")
        result = await client.get_folder_lists("folder_1")
        assert len(result) == 2
        assert result[0]["name"] == "Iteration 5 (23/2 - 8/3)"

@pytest.mark.asyncio
async def test_get_list_tasks_handles_pagination():
    page_0 = AsyncMock()
    page_0.json = MagicMock(return_value={"tasks": [{"id": f"t{i}"} for i in range(100)]})
    page_0.raise_for_status = lambda: None

    page_1 = AsyncMock()
    page_1.json = MagicMock(return_value={"tasks": [{"id": "t100"}]})
    page_1.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", side_effect=[page_0, page_1]):
        client = ClickUpClient("fake_key")
        result = await client.get_list_tasks("list_1")
        assert len(result) == 101

@pytest.mark.asyncio
async def test_extract_task_data():
    client = ClickUpClient("fake_key")
    raw_task = {
        "id": "abc123",
        "name": "Fix bug",
        "status": {"status": "in progress"},
        "assignees": [{"username": "Anna"}, {"username": "Erik"}],
        "points": 3.0,
        "time_estimate": 7200000,
    }
    extracted = client.extract_task_data(raw_task)
    assert extracted["task_id"] == "abc123"
    assert extracted["task_name"] == "Fix bug"
    assert extracted["task_status"] == "in progress"
    assert extracted["assignee_name"] == "Anna, Erik"
    assert extracted["points"] == 3.0
    assert extracted["hours"] == 2.0  # 7200000ms = 2h


def test_get_system_client_uses_service_key(monkeypatch):
    monkeypatch.setenv("CLICKUP_SERVICE_API_KEY", "pk_service_key")
    monkeypatch.delenv("CLICKUP_API_KEY", raising=False)
    import importlib
    import src.config as cfg
    import src.clickup_client as cu
    importlib.reload(cfg)
    importlib.reload(cu)
    client = cu.get_system_client()
    assert client.headers["Authorization"] == "pk_service_key"


def test_get_user_client_uses_passed_token():
    from src.clickup_client import get_user_client
    client = get_user_client("oauth_token_abc")
    assert client.headers["Authorization"] == "oauth_token_abc"
