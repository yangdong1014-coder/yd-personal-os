import json

import database


def _goal_backup(goal_id, name="导入目标", goal_type="年度"):
    return {
        "meta": {
            "exported_at": "2026-01-01 00:00:00",
            "version": "1.0",
            "tables": list(database.IMPORT_TABLES),
        },
        "goals": [
            {
                "id": goal_id,
                "name": name,
                "type": goal_type,
                "created_at": "2026-01-01 00:00:00",
            }
        ],
        "projects": [],
        "tasks": [],
        "reviews": [],
        "assets": [],
        "capability_entries": [],
    }


def test_import_creates_new_records(client):
    backup = _goal_backup(5001)
    stats = client.post("/api/import", json=backup).get_json()["data"]

    assert stats["created"] >= 1
    assert stats["updated"] == 0
    assert stats["skipped"] == 0
    assert stats["imported"] == stats["created"] + stats["updated"]
    assert len(client.get("/api/goals").get_json()["data"]) == 1


def test_import_updates_changed_records(client):
    goal = client.post(
        "/api/goals",
        json={"name": "原名", "type": "年度"},
    ).get_json()["data"]
    backup = _goal_backup(goal["id"], name="新名称")

    stats = client.post("/api/import", json=backup).get_json()["data"]
    assert stats["created"] == 0
    assert stats["updated"] >= 1
    assert stats["imported"] == stats["created"] + stats["updated"]

    saved = client.get("/api/goals").get_json()["data"][0]
    assert saved["name"] == "新名称"


def test_import_success_has_no_rolled_back(client):
    backup = _goal_backup(5002)
    stats = client.post("/api/import", json=backup).get_json()["data"]
    assert stats.get("rolled_back") is not True
    assert stats["created"] >= 1
    assert stats["imported"] == stats["created"] + stats["updated"]


def test_import_skips_unchanged_records(client):
    goal = client.post(
        "/api/goals",
        json={"name": "不变目标", "type": "季度"},
    ).get_json()["data"]
    backup = json.loads(client.get("/api/export").data)

    stats = client.post("/api/import", json=backup).get_json()["data"]
    assert stats["created"] == 0
    assert stats["updated"] == 0
    assert stats["skipped"] >= 1
    assert stats["imported"] == 0
    assert client.get("/api/goals").get_json()["data"][0]["id"] == goal["id"]