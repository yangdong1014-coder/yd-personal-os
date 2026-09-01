import json
from datetime import datetime, timedelta

import database


_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _practice_steps(user_id, module=None):
    conn = database.get_connection()
    try:
        if module is None:
            rows = conn.execute(
                """
                SELECT * FROM capability_practice_steps
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM capability_practice_steps
                WHERE user_id = ? AND module = ?
                ORDER BY step_order ASC, id ASC
                """,
                (user_id, module),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _timestamp_after_boundary(rows):
    latest = max(
        datetime.strptime(row["updated_at"], _TIMESTAMP_FORMAT) for row in rows
    )
    later = latest + timedelta(seconds=2)
    assert (later - latest).total_seconds() > 1
    return later.strftime(_TIMESTAMP_FORMAT)


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


def test_duplicate_import_stays_idempotent_across_timestamp_boundary(
    client, monkeypatch
):
    backup = json.loads(client.get("/api/export").data)
    before = _practice_steps(client.user_id)
    assert len(before) == 32

    first_clock = _timestamp_after_boundary(before)
    second_clock = (
        datetime.strptime(first_clock, _TIMESTAMP_FORMAT) + timedelta(seconds=2)
    ).strftime(_TIMESTAMP_FORMAT)
    assert (
        datetime.strptime(second_clock, _TIMESTAMP_FORMAT)
        - datetime.strptime(first_clock, _TIMESTAMP_FORMAT)
    ).total_seconds() > 1
    clock = {"now": first_clock}
    monkeypatch.setattr(database, "_now", lambda: clock["now"])

    first_response = client.post("/api/import", json=backup)
    assert first_response.status_code == 200
    first = first_response.get_json()["data"]
    assert first["created"] == 0
    assert first["updated"] == 0
    assert first["imported"] == 0
    assert first["failed"] == 0
    assert _practice_steps(client.user_id) == before

    preview_response = client.post("/api/import/preview", json=backup)
    assert preview_response.status_code == 200
    preview = preview_response.get_json()["data"]
    assert preview["will_import"] == 0
    assert preview["will_update"] == 0
    assert preview["will_fail"] == 0

    clock["now"] = second_clock
    second_response = client.post("/api/import", json=backup)
    assert second_response.status_code == 200
    second = second_response.get_json()["data"]
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["imported"] == 0
    assert second["failed"] == 0
    assert _practice_steps(client.user_id) == before


def test_practice_step_normalizer_only_writes_changed_order(client, monkeypatch):
    module = database.CAPABILITY_MODULES[0]
    before = _practice_steps(client.user_id, module)
    assert [row["step_order"] for row in before] == [1, 2, 3, 4]

    later = _timestamp_after_boundary(before)
    monkeypatch.setattr(database, "_now", lambda: later)

    conn = database.get_connection()
    try:
        database._normalize_practice_step_order(conn, module, client.user_id)
        assert conn.total_changes == 0
    finally:
        conn.close()
    assert _practice_steps(client.user_id, module) == before

    changed_id = before[-1]["id"]
    conn = database.get_connection()
    try:
        conn.execute(
            """
            UPDATE capability_practice_steps
            SET step_order = 9
            WHERE id = ? AND user_id = ?
            """,
            (changed_id, client.user_id),
        )
        conn.commit()
    finally:
        conn.close()

    conn = database.get_connection()
    try:
        database._normalize_practice_step_order(conn, module, client.user_id)
        assert conn.total_changes == 1
        conn.commit()
    finally:
        conn.close()

    after = _practice_steps(client.user_id, module)
    assert [row["step_order"] for row in after] == [1, 2, 3, 4]
    for original, normalized in zip(before, after):
        expected_updated_at = (
            later if original["id"] == changed_id else original["updated_at"]
        )
        assert normalized["updated_at"] == expected_updated_at
