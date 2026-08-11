import hashlib
import sqlite3
from pathlib import Path

import pytest

import auth_service
import database


def _bootstrap_two_users():
    admin = auth_service.bootstrap_admin(
        "owneradmin", "owneradmin@example.com", "correct horse battery"
    )
    user_a, _ = auth_service.create_standard_user("usera", "usera@example.com")
    user_b, _ = auth_service.create_standard_user("userb", "userb@example.com")
    return admin, user_a, user_b


def test_all_sixteen_business_tables_have_required_owner_fk_and_index(test_app):
    conn = database.get_connection()
    try:
        assert set(database.PERSONAL_DATA_TABLES) == {
            "goals", "projects", "tasks", "reviews", "assets",
            "capability_entries", "capability_practice_steps", "opportunities",
            "experiments", "feedback_items", "deliberations",
            "positioning_anchor", "positioning_calibration",
            "positioning_goal_action", "inbox_entries", "inbox_suggestions",
        }
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 220
        for table in database.PERSONAL_DATA_TABLES:
            columns = {
                row["name"]: row
                for row in conn.execute(f'PRAGMA table_info("{table}")')
            }
            assert columns["user_id"]["type"] == "INTEGER", table
            assert columns["user_id"]["notnull"] == 1, table

            foreign_keys = conn.execute(
                f'PRAGMA foreign_key_list("{table}")'
            ).fetchall()
            assert any(
                row["from"] == "user_id" and row["table"] == "users"
                for row in foreign_keys
            ), table

            indexes = conn.execute(f'PRAGMA index_list("{table}")').fetchall()
            indexed = False
            for index in indexes:
                fields = [
                    row["name"]
                    for row in conn.execute(
                        f'PRAGMA index_info("{index["name"]}")'
                    ).fetchall()
                ]
                indexed = indexed or (fields and fields[0] == "user_id")
            assert indexed, table
    finally:
        conn.close()


def test_hard_parent_child_relations_reject_cross_user_links(test_app):
    admin, user_a, user_b = _bootstrap_two_users()
    goal_a = database.create_goal("A goal", "年度", user_id=user_a["id"])
    project_a = database.create_project(
        goal_a["id"], "A project", user_id=user_a["id"]
    )
    calibration_a = database.create_positioning_calibration(
        {"calibrated_at": "2026-08-01"}, user_id=user_a["id"]
    )
    inbox_a = database.create_inbox_entry("A inbox", user_id=user_a["id"])

    conn = database.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO projects (user_id, goal_id, name, created_at)
                VALUES (?, ?, 'cross project', 'now')
                """,
                (user_b["id"], goal_a["id"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO tasks (user_id, project_id, name, created_at)
                VALUES (?, ?, 'cross task', 'now')
                """,
                (user_b["id"], project_a["id"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO positioning_goal_action (
                    user_id, calibration_id, action_type, reason, created_at
                ) VALUES (?, ?, '新建目标', 'cross', 'now')
                """,
                (user_b["id"], calibration_a["id"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO inbox_suggestions (
                    user_id, inbox_entry_id, target_type, title, created_at
                ) VALUES (?, ?, 'goal', 'cross', 'now')
                """,
                (user_b["id"], inbox_a["id"]),
            )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_optional_and_polymorphic_relations_reject_cross_user_links(test_app):
    _admin, user_a, user_b = _bootstrap_two_users()
    goal_a = database.create_goal("A goal", "年度", user_id=user_a["id"])
    project_a = database.create_project(
        goal_a["id"], "A project", user_id=user_a["id"]
    )
    review_a = database.create_review(
        "2026-08-01", "每日", "done", "", "", "", user_id=user_a["id"]
    )
    opportunity_a = database.create_opportunity(
        {"name": "A opportunity"}, user_id=user_a["id"]
    )
    calibration_b = database.create_positioning_calibration(
        {"calibrated_at": "2026-08-02"}, user_id=user_b["id"]
    )

    conn = database.get_connection()
    try:
        statements = (
            (
                """
                INSERT INTO assets (
                    user_id, title, asset_type, source_review_id, created_at
                ) VALUES (?, 'cross asset', '通用资产', ?, 'now')
                """,
                (user_b["id"], review_a["id"]),
            ),
            (
                """
                INSERT INTO experiments (
                    user_id, opportunity_id, name, created_at, updated_at
                ) VALUES (?, ?, 'cross experiment', 'now', 'now')
                """,
                (user_b["id"], opportunity_a["id"]),
            ),
            (
                """
                INSERT INTO feedback_items (
                    user_id, related_type, related_id, title, created_at, updated_at
                ) VALUES (?, 'project', ?, 'cross feedback', 'now', 'now')
                """,
                (user_b["id"], project_a["id"]),
            ),
            (
                """
                INSERT INTO deliberations (
                    user_id, title, problem, initial_judgment, reasoning,
                    assumptions, related_type, related_id, created_at, updated_at
                ) VALUES (?, 'cross', 'problem', 'judgment', 'reason',
                          'assumption', 'project', ?, 'now', 'now')
                """,
                (user_b["id"], project_a["id"]),
            ),
            (
                """
                INSERT INTO positioning_goal_action (
                    user_id, calibration_id, action_type, target_goal_id,
                    reason, created_at
                ) VALUES (?, ?, '降级目标', ?, 'cross', 'now')
                """,
                (user_b["id"], calibration_b["id"], goal_a["id"]),
            ),
        )
        for sql, params in statements:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql, params)
    finally:
        conn.close()


def test_business_row_owner_is_immutable(test_app):
    _admin, user_a, user_b = _bootstrap_two_users()
    goal = database.create_goal("owned", "年度", user_id=user_a["id"])
    conn = database.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="owner is immutable"):
            conn.execute(
                "UPDATE goals SET user_id = ? WHERE id = ?",
                (user_b["id"], goal["id"]),
            )
    finally:
        conn.close()


def test_new_users_only_receive_independent_default_practice_paths(test_app):
    _admin, user_a, user_b = _bootstrap_two_users()
    conn = database.get_connection()
    try:
        for table in set(database.PERSONAL_DATA_TABLES) - {
            "capability_practice_steps"
        }:
            assert conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE user_id IN (?, ?)',
                (user_a["id"], user_b["id"]),
            ).fetchone()[0] == 0, table
    finally:
        conn.close()

    path_a = database.get_capability_practice_path("体系力", user_a["id"])
    path_b = database.get_capability_practice_path("体系力", user_b["id"])
    assert path_a and path_b
    assert {step["id"] for step in path_a}.isdisjoint(step["id"] for step in path_b)

    original_b = path_b[0]["title"]
    database.update_capability_practice_step(
        path_a[0]["id"], title="A 独立路径", user_id=user_a["id"]
    )
    assert database.get_capability_practice_path("体系力", user_a["id"])[0][
        "title"
    ] == "A 独立路径"
    assert database.get_capability_practice_path("体系力", user_b["id"])[0][
        "title"
    ] == original_b

    with pytest.raises(ValueError, match="训练步骤不存在"):
        database.update_capability_practice_step(
            path_a[0]["id"], title="cross", user_id=user_b["id"]
        )


def test_positioning_anchor_and_mainline_normalization_are_per_user(test_app):
    _admin, user_a, user_b = _bootstrap_two_users()
    anchor_a = database.upsert_positioning_anchor(
        {"north_star": "A"}, user_id=user_a["id"]
    )
    anchor_b = database.upsert_positioning_anchor(
        {"north_star": "B"}, user_id=user_b["id"]
    )
    updated_a = database.upsert_positioning_anchor(
        {"north_star": "A2"}, user_id=user_a["id"]
    )
    assert updated_a["id"] == anchor_a["id"]
    assert anchor_a["id"] != anchor_b["id"]
    assert database.get_positioning_anchor(user_a["id"])["north_star"] == "A2"
    assert database.get_positioning_anchor(user_b["id"])["north_star"] == "B"
    conn = database.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO positioning_anchor (user_id, north_star, updated_at)
                VALUES (?, 'duplicate', 'now')
                """,
                (user_b["id"],),
            )
    finally:
        conn.close()

    a1 = database.create_goal("A1", "当前主线", user_id=user_a["id"])
    a2 = database.create_goal("A2", "当前主线", user_id=user_a["id"])
    b1 = database.create_goal("B1", "当前主线", user_id=user_b["id"])
    b2 = database.create_goal("B2", "当前主线", user_id=user_b["id"])
    conn = database.get_connection()
    try:
        assert conn.execute("SELECT type FROM goals WHERE id = ?", (a1["id"],)).fetchone()[0] == "季度"
        assert conn.execute("SELECT type FROM goals WHERE id = ?", (a2["id"],)).fetchone()[0] == "当前主线"
        assert conn.execute("SELECT type FROM goals WHERE id = ?", (b1["id"],)).fetchone()[0] == "季度"
        assert conn.execute("SELECT type FROM goals WHERE id = ?", (b2["id"],)).fetchone()[0] == "当前主线"
    finally:
        conn.close()


def test_init_db_does_not_seed_or_normalize_existing_users(test_app):
    admin = auth_service.bootstrap_admin(
        "admin", "admin@example.com", "correct horse battery"
    )
    conn = database.get_connection()
    try:
        conn.execute(
            "DELETE FROM capability_practice_steps WHERE user_id = ?", (admin["id"],)
        )
        conn.execute(
            """
            INSERT INTO goals (user_id, name, type, created_at)
            VALUES (?, 'mainline one', '当前主线', '2026-01-01')
            """,
            (admin["id"],),
        )
        conn.execute(
            """
            INSERT INTO goals (user_id, name, type, created_at)
            VALUES (?, 'mainline two', '当前主线', '2026-01-02')
            """,
            (admin["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    database.init_db()
    conn = database.get_connection()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM capability_practice_steps WHERE user_id = ?",
            (admin["id"],),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM goals WHERE user_id = ? AND type = '当前主线'",
            (admin["id"],),
        ).fetchone()[0] == 2
    finally:
        conn.close()


def test_init_db_refuses_legacy_schema_without_modifying_it(tmp_path, monkeypatch):
    source = tmp_path / "legacy.db"
    sql = (Path(__file__).parent / "fixtures" / "legacy_v214.sql").read_text(
        encoding="utf-8"
    )
    conn = sqlite3.connect(source)
    conn.executescript(sql)
    conn.close()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    before_stat = source.stat()
    monkeypatch.setattr(database, "DB_PATH", str(source))

    with pytest.raises(database.LegacyMigrationRequired):
        database.init_db()

    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert source.stat().st_size == before_stat.st_size
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns
