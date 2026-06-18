import json

import pytest

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


def _seed_hierarchy(client):
    goal = client.post(
        "/api/goals",
        json={"name": "级联目标", "type": "年度"},
    ).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "级联项目"},
    ).get_json()["data"]
    task = client.post(
        "/api/tasks",
        json={"project_id": project["id"], "name": "级联任务"},
    ).get_json()["data"]
    return goal, project, task


def _seed_review_with_asset(client):
    review = client.post(
        "/api/reviews",
        json={
            "review_date": "2026-06-18",
            "type": "每日",
            "what_done": "做了事",
            "stuck": "",
            "next_adjust": "",
            "depositable": "可沉淀",
        },
    ).get_json()["data"]
    asset = client.post(
        "/api/assets",
        json={
            "title": "关联卡片",
            "trigger_context": "",
            "core_content": "内容",
            "asset_type": "本质洞察",
            "fields": {"底层本质": "测试内容"},
            "capability_tags": [],
            "source_review_id": review["id"],
        },
    ).get_json()["data"]
    return review, asset


def test_delete_project_success(client):
    goal, project, _task = _seed_hierarchy(client)
    response = client.delete(f"/api/projects/{project['id']}")
    assert response.status_code == 200
    assert response.get_json()["data"]["deleted"] is True
    projects = client.get(f"/api/projects?goal_id={goal['id']}").get_json()["data"]
    assert projects == []


def test_delete_task_success(client):
    _goal, project, task = _seed_hierarchy(client)
    response = client.delete(f"/api/tasks/{task['id']}")
    assert response.status_code == 200
    tasks = client.get("/api/tasks").get_json()["data"]
    assert all(item["id"] != task["id"] for item in tasks)


def test_delete_review_success(client):
    review, _asset = _seed_review_with_asset(client)
    response = client.delete(f"/api/reviews/{review['id']}")
    assert response.status_code == 200
    reviews = client.get("/api/reviews").get_json()["data"]
    assert reviews == []


def test_delete_asset_success(client):
    asset = client.post(
        "/api/assets",
        json={
            "title": "待删卡片",
            "trigger_context": "",
            "core_content": "内容",
            "asset_type": "本质洞察",
            "fields": {"底层本质": "测试内容"},
            "capability_tags": [],
        },
    ).get_json()["data"]
    response = client.delete(f"/api/assets/{asset['id']}")
    assert response.status_code == 200
    assets = client.get("/api/assets").get_json()["data"]
    assert assets == []


def test_delete_capability_entry_success(client):
    entry = client.post(
        "/api/capability-entries",
        json={
            "module": "本质力",
            "entry_date": "2026-06-18",
            "content": "测试记录",
            "source_project": "",
            "level_type": "能力层",
        },
    ).get_json()["data"]
    response = client.delete(f"/api/capability-entries/{entry['id']}")
    assert response.status_code == 200
    entries = client.get("/api/capability-entries").get_json()["data"]
    assert entries == []


def test_delete_goal_cascades_projects_and_tasks(client):
    goal, project, task = _seed_hierarchy(client)
    response = client.delete(f"/api/goals/{goal['id']}")
    assert response.status_code == 200
    cascaded = response.get_json()["data"]["cascaded"]
    assert cascaded["projects"] == 1
    assert cascaded["tasks"] == 1
    assert client.get("/api/projects").get_json()["data"] == []
    assert client.get("/api/tasks").get_json()["data"] == []
    assert client.get(f"/api/projects?goal_id={goal['id']}").get_json()["data"] == []
    assert all(item["id"] != project["id"] for item in client.get("/api/projects").get_json()["data"])
    assert all(item["id"] != task["id"] for item in client.get("/api/tasks").get_json()["data"])


def test_delete_project_cascades_tasks(client):
    _goal, project, task = _seed_hierarchy(client)
    response = client.delete(f"/api/projects/{project['id']}")
    assert response.status_code == 200
    assert response.get_json()["data"]["cascaded"]["tasks"] == 1
    tasks = client.get("/api/tasks").get_json()["data"]
    assert all(item["id"] != task["id"] for item in tasks)


def test_delete_review_clears_asset_source_review_id(client):
    review, asset = _seed_review_with_asset(client)
    response = client.delete(f"/api/reviews/{review['id']}")
    assert response.status_code == 200
    assert response.get_json()["data"]["cleared_asset_links"] == 1
    assets = client.get("/api/assets").get_json()["data"]
    assert len(assets) == 1
    assert assets[0]["id"] == asset["id"]
    assert assets[0]["source_review_id"] is None


def test_import_duplicate_skips_without_duplicating(client):
    _seed_hierarchy(client)
    backup = json.loads(client.get("/api/export").data)

    first = client.post("/api/import", json=backup).get_json()["data"]
    assert first["failed"] == 0

    second = client.post("/api/import", json=backup).get_json()["data"]
    assert second["imported"] == 0
    assert second["skipped"] >= 3
    assert second["failed"] == 0

    assert len(client.get("/api/goals").get_json()["data"]) == 1
    assert len(client.get("/api/projects").get_json()["data"]) == 1
    assert len(client.get("/api/tasks").get_json()["data"]) == 1


def test_import_foreign_key_failure_rolls_back(client):
    goal = client.post(
        "/api/goals",
        json={"name": "保留目标", "type": "季度"},
    ).get_json()["data"]
    before_goals = client.get("/api/goals").get_json()["data"]

    bad_backup = _empty_backup()
    bad_backup["projects"] = [
        {
            "id": 9001,
            "goal_id": 99999,
            "name": "孤立项目",
            "created_at": "2026-01-01 00:00:00",
        }
    ]

    response = client.post("/api/import", json=bad_backup)
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    data = payload["data"]
    assert data["rolled_back"] is True
    assert data["created"] == 0
    assert data["updated"] == 0
    assert data["imported"] == 0
    assert data["failed"] >= 1
    assert data["message"]

    after_goals = client.get("/api/goals").get_json()["data"]
    assert len(after_goals) == len(before_goals)
    assert any(item["id"] == goal["id"] for item in after_goals)


def test_import_invalid_structure_rolls_back(client):
    client.post(
        "/api/goals",
        json={"name": "结构测试", "type": "年度"},
    )
    before_count = len(client.get("/api/goals").get_json()["data"])

    response = client.post(
        "/api/import",
        json={"meta": {"version": "1.0"}, "goals": "not-a-list"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    data = payload["data"]
    assert data["rolled_back"] is True
    assert data["created"] == 0
    assert data["updated"] == 0
    assert data["imported"] == 0
    assert data["message"]
    assert len(client.get("/api/goals").get_json()["data"]) == before_count


@pytest.mark.parametrize(
    "path",
    [
        "/api/goals/99999",
        "/api/projects/99999",
        "/api/tasks/99999",
        "/api/reviews/99999",
        "/api/assets/99999",
        "/api/capability-entries/99999",
    ],
)
def test_delete_not_found_returns_404(client, path):
    response = client.delete(path)
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert "不存在" in payload["error"]