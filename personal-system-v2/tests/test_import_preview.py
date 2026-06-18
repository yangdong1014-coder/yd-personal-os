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


def _seed_goal(client):
    return client.post(
        "/api/goals",
        json={"name": "预览目标", "type": "年度"},
    ).get_json()["data"]


def test_import_preview_does_not_modify_database(client):
    goal = _seed_goal(client)
    before = client.get("/api/goals").get_json()["data"]

    backup = json.loads(client.get("/api/export").data)
    response = client.post("/api/import/preview", json=backup)
    assert response.status_code == 200

    after = client.get("/api/goals").get_json()["data"]
    assert len(after) == len(before)
    assert any(item["id"] == goal["id"] for item in after)


def test_import_preview_detects_duplicate_ids(client):
    _seed_goal(client)
    backup = json.loads(client.get("/api/export").data)

    preview = client.post("/api/import/preview", json=backup).get_json()["data"]
    assert preview["will_skip"] >= 1
    assert preview["will_import"] == 0
    assert preview["will_update"] == 0
    assert preview["will_fail"] == 0


def test_import_preview_detects_invalid_structure(client):
    response = client.post(
        "/api/import/preview",
        json={"meta": {"version": "9.9"}},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]


def test_import_preview_detects_foreign_key_errors(client):
    bad_backup = _empty_backup()
    bad_backup["projects"] = [
        {
            "id": 8001,
            "goal_id": 99999,
            "name": "孤立项目",
            "created_at": "2026-01-01 00:00:00",
        }
    ]

    preview = client.post("/api/import/preview", json=bad_backup).get_json()
    assert preview["ok"] is True
    data = preview["data"]
    assert data["will_fail"] >= 1
    assert data["errors"]