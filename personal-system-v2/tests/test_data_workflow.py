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


def _set_created_at(table, entity_id, created_at):
    assert table in {"goals", "projects", "tasks"}
    conn = database.get_connection()
    conn.execute(
        f"UPDATE {table} SET created_at = ? WHERE id = ?",
        (created_at, entity_id),
    )
    conn.commit()
    conn.close()


def _seed_dashboard_project(
    client,
    goal_id,
    name,
    task_specs,
    project_created_at="2026-01-01 00:00:00",
):
    project = client.post(
        "/api/projects",
        json={"goal_id": goal_id, "name": name},
    ).get_json()["data"]
    _set_created_at("projects", project["id"], project_created_at)

    tasks = []
    for index, spec in enumerate(task_specs, start=1):
        task = client.post(
            "/api/tasks",
            json={"project_id": project["id"], "name": f"{name}任务{index}"},
        ).get_json()["data"]
        _set_created_at(
            "tasks",
            task["id"],
            spec.get("created_at", "2026-01-01 00:00:00"),
        )
        status = spec.get("status")
        if status and status != task["status"]:
            task = client.patch(
                f"/api/tasks/{task['id']}/status",
                json={"status": status},
            ).get_json()["data"]
        if spec.get("today"):
            task = client.patch(
                f"/api/tasks/{task['id']}/today-progress",
                json={"enabled": True},
            ).get_json()["data"]
        tasks.append(task)

    return project, tasks


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


def test_update_goal_project_task_preserves_relations_and_system_fields(client):
    goal, project, task = _seed_hierarchy(client)

    goal_response = client.patch(
        f"/api/goals/{goal['id']}",
        json={
            "id": 99999,
            "name": "迭代目标",
            "type": "季度",
            "created_at": "1999-01-01 00:00:00",
        },
    )
    assert goal_response.status_code == 200
    updated_goal = goal_response.get_json()["data"]
    assert updated_goal["id"] == goal["id"]
    assert updated_goal["name"] == "迭代目标"
    assert updated_goal["type"] == "季度"
    assert updated_goal["created_at"] == goal["created_at"]

    project_response = client.patch(
        f"/api/projects/{project['id']}",
        json={
            "id": 99999,
            "goal_id": 99999,
            "name": "迭代项目",
            "created_at": "1999-01-01 00:00:00",
        },
    )
    assert project_response.status_code == 200
    updated_project = project_response.get_json()["data"]
    assert updated_project["id"] == project["id"]
    assert updated_project["goal_id"] == goal["id"]
    assert updated_project["name"] == "迭代项目"
    assert updated_project["created_at"] == project["created_at"]

    task_response = client.patch(
        f"/api/tasks/{task['id']}",
        json={
            "id": 99999,
            "project_id": 99999,
            "name": "迭代任务",
            "status": "进行中",
            "created_at": "1999-01-01 00:00:00",
        },
    )
    assert task_response.status_code == 200
    updated_task = task_response.get_json()["data"]
    assert updated_task["id"] == task["id"]
    assert updated_task["project_id"] == project["id"]
    assert updated_task["name"] == "迭代任务"
    assert updated_task["status"] == "进行中"
    assert updated_task["created_at"] == task["created_at"]
    assert updated_task["goal_name"] == "迭代目标"
    assert updated_task["project_name"] == "迭代项目"


def test_update_task_rejects_invalid_status(client):
    _goal, _project, task = _seed_hierarchy(client)
    response = client.patch(
        f"/api/tasks/{task['id']}",
        json={"name": "状态测试", "status": "随便新增状态"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "无效的任务状态" in payload["error"]


def test_dashboard_active_projects_include_old_projects_with_open_tasks(client):
    goal = client.post(
        "/api/goals",
        json={"name": "首页目标", "type": "年度"},
    ).get_json()["data"]
    project, _tasks = _seed_dashboard_project(
        client,
        goal["id"],
        "老项目仍在推进",
        [{"status": "待处理", "created_at": "2026-01-02 00:00:00"}],
        project_created_at="2026-01-01 00:00:00",
    )

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    projects = response.get_json()["data"]["week_projects"]

    assert any(item["id"] == project["id"] for item in projects)


def test_dashboard_active_projects_ordering_and_completed_filter(client):
    goal = client.post(
        "/api/goals",
        json={"name": "排序目标", "type": "年度"},
    ).get_json()["data"]
    completed_project, _ = _seed_dashboard_project(
        client,
        goal["id"],
        "只有完成任务",
        [{"status": "完成"}],
        project_created_at="2026-01-05 00:00:00",
    )
    recent_project, _ = _seed_dashboard_project(
        client,
        goal["id"],
        "最近创建但只有一个待处理",
        [{"status": "待处理"}],
        project_created_at="2026-01-04 00:00:00",
    )
    many_project, _ = _seed_dashboard_project(
        client,
        goal["id"],
        "待处理任务更多",
        [
            {"status": "待处理"},
            {"status": "待处理"},
            {"status": "待处理"},
        ],
        project_created_at="2026-01-03 00:00:00",
    )
    doing_project, _ = _seed_dashboard_project(
        client,
        goal["id"],
        "已有进行中任务",
        [{"status": "进行中"}],
        project_created_at="2026-01-02 00:00:00",
    )
    today_project, _ = _seed_dashboard_project(
        client,
        goal["id"],
        "有今日推进任务",
        [{"status": "待处理", "today": True}],
        project_created_at="2026-01-01 00:00:00",
    )

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    projects = response.get_json()["data"]["week_projects"]
    project_ids = [item["id"] for item in projects]

    assert completed_project["id"] not in project_ids
    assert project_ids[:4] == [
        today_project["id"],
        doing_project["id"],
        many_project["id"],
        recent_project["id"],
    ]


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
