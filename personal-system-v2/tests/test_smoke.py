import json

import database


def _empty_backup():
    return {
        "meta": {
            "exported_at": "2026-01-01 00:00:00",
            "version": "1.0",
            "tables": list(database.IMPORT_TABLES),
        },
        "goals": [],
        "projects": [],
        "tasks": [],
        "reviews": [],
        "assets": [],
        "capability_entries": [],
    }


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_changelog_api(client):
    response = client.get("/api/changelog")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["current"] == "v1.12.2"
    assert isinstance(payload["data"]["entries"], list)


def test_list_goals_api(client):
    response = client.get("/api/goals")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)


def test_delete_goal_success(client):
    create = client.post(
        "/api/goals",
        json={"name": "测试目标", "type": "年度"},
    )
    goal_id = create.get_json()["data"]["id"]

    response = client.delete(f"/api/goals/{goal_id}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["deleted"] is True

    goals = client.get("/api/goals").get_json()["data"]
    assert all(goal["id"] != goal_id for goal in goals)


def test_delete_goal_not_found(client):
    response = client.delete("/api/goals/99999")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert "不存在" in payload["error"]


def test_import_empty_backup(client):
    response = client.post(
        "/api/import",
        json=_empty_backup(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["imported"] == 0
    assert payload["data"]["skipped"] == 0
    assert payload["data"]["failed"] == 0


def test_import_roundtrip(client):
    goal = client.post(
        "/api/goals",
        json={"name": "导入测试", "type": "季度"},
    ).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "导入项目"},
    ).get_json()["data"]
    client.post(
        "/api/tasks",
        json={"project_id": project["id"], "name": "导入任务"},
    )

    export_response = client.get("/api/export")
    backup = json.loads(export_response.data)

    client.delete(f"/api/goals/{goal['id']}")
    assert client.get("/api/goals").get_json()["data"] == []

    import_response = client.post("/api/import", json=backup)
    assert import_response.status_code == 200
    stats = import_response.get_json()["data"]
    assert stats["imported"] >= 3
    assert stats["failed"] == 0

    goals = client.get("/api/goals").get_json()["data"]
    assert len(goals) == 1
    assert goals[0]["name"] == "导入测试"


def test_import_invalid_json_body(client):
    response = client.post(
        "/api/import",
        data="not-json",
        content_type="application/json",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False


def test_import_invalid_backup_structure(client):
    response = client.post(
        "/api/import",
        json={"meta": {"version": "9.9"}},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]