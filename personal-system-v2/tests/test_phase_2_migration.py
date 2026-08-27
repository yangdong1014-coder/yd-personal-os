import hashlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import database
from v22_migration import (
    LEGACY_V214_COLUMNS,
    MigrationError,
    V22_USERS_COLUMNS,
    VerificationError,
    audit_postflight,
    audit_preflight,
    migrate_legacy_database,
    verify_authoritative_envelope,
    verify_migration,
)


FIXTURE_SQL = Path(__file__).parent / "fixtures" / "legacy_v214.sql"


def _create_legacy(path):
    conn = sqlite3.connect(path)
    conn.executescript(FIXTURE_SQL.read_text(encoding="utf-8"))
    conn.close()
    return path


def _migrate(source, staged):
    return migrate_legacy_database(
        source,
        staged,
        admin_username="migration-admin",
        admin_email="migration-admin@example.com",
        admin_password="correct horse battery",
    )


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_migration_preserves_every_table_field_id_json_time_and_sequence(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    before_hash = _digest(source)
    before_stat = source.stat()

    result = _migrate(source, staged)

    assert result["ok"] is True
    assert "correct horse battery" not in repr(result)
    assert "password_hash" not in repr(result)
    assert set(result["row_counts"]) == set(database.PERSONAL_DATA_TABLES)
    assert all(count == 1 for count in result["row_counts"].values())
    report = result["verification"]
    assert report["ok"] is True
    assert report["users_sequence"] == report["admin_id"]
    assert report["integrity_check"] == "ok"
    assert report["foreign_key_check_rows"] == 0
    assert all(count == 0 for count in report["hard_orphans"].values())
    assert all(count == 0 for count in report["soft_orphans"].values())
    for table, details in report["tables"].items():
        assert details["legacy_count"] == details["staged_admin_count"]
        assert details["null_user_id"] == 0
        assert details["other_owner_count"] == 0
        assert details["legacy_except_staged"] == 0
        assert details["staged_except_legacy"] == 0
        assert details["missing_primary_keys"] == 0
        assert details["legacy_sequence"] == details["staged_sequence"], table

    assert _digest(source) == before_hash
    assert source.stat().st_size == before_stat.st_size
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns

    conn = sqlite3.connect(staged)
    conn.row_factory = sqlite3.Row
    try:
        admin_id = report["admin_id"]
        for table, expected_columns in LEGACY_V214_COLUMNS.items():
            columns = {
                row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")')
            }
            assert columns == set(expected_columns) | {"user_id"}
            assert conn.execute(
                f'SELECT COUNT(DISTINCT user_id) FROM "{table}"'
            ).fetchone()[0] == 1
            assert conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE user_id = ?', (admin_id,)
            ).fetchone()[0] == 1
        asset = conn.execute("SELECT * FROM assets WHERE id = 50").fetchone()
        assert asset["fields"] == '{"步骤":["一","二"],"score":3}'
        assert asset["capability_tags"] == '["体系力","AI驾驭力"]'
        assert asset["created_at"] == "2026-01-05T01:02:03+00:00"
        assert conn.execute("SELECT id FROM goals WHERE id = 10").fetchone()
        assert conn.execute("SELECT id FROM inbox_suggestions WHERE id = 160").fetchone()
    finally:
        conn.close()


def test_verify_tool_rechecks_a_completed_staged_database(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)

    report = verify_migration(source, staged)
    assert report["ok"] is True

    script = Path(__file__).parents[1] / "scripts" / "verify-v2.2-migration.py"
    completed = subprocess.run(
        [sys.executable, str(script), str(source), str(staged)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert '"ok": true' in completed.stdout


def test_interrupted_migration_never_changes_source_or_publishes_destination(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    before_hash = _digest(source)
    before_stat = source.stat()

    def fail_after_assets(table, _count):
        if table == "assets":
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        migrate_legacy_database(
            source,
            staged,
            admin_username="migration-admin",
            admin_email="migration-admin@example.com",
            admin_password="correct horse battery",
            failure_hook=fail_after_assets,
        )

    assert not staged.exists()
    assert not list(tmp_path.glob(".staged.db.*.tmp"))
    assert _digest(source) == before_hash
    assert source.stat().st_size == before_stat.st_size
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns


def test_migration_repeats_consistently_on_fresh_legacy_copies(tmp_path):
    original = _create_legacy(tmp_path / "legacy-original.db")
    source_a = tmp_path / "legacy-a.db"
    source_b = tmp_path / "legacy-b.db"
    shutil.copy2(original, source_a)
    shutil.copy2(original, source_b)
    staged_a = tmp_path / "staged-a.db"
    staged_b = tmp_path / "staged-b.db"

    report_a = _migrate(source_a, staged_a)["verification"]
    report_b = _migrate(source_b, staged_b)["verification"]
    assert report_a["tables"] == report_b["tables"]
    assert report_a["soft_orphans"] == report_b["soft_orphans"]

    conn_a = sqlite3.connect(staged_a)
    conn_b = sqlite3.connect(staged_b)
    try:
        for table, columns in LEGACY_V214_COLUMNS.items():
            column_sql = ", ".join(f'"{column}"' for column in columns)
            rows_a = conn_a.execute(
                f'SELECT {column_sql}, user_id FROM "{table}" ORDER BY id'
            ).fetchall()
            rows_b = conn_b.execute(
                f'SELECT {column_sql}, user_id FROM "{table}" ORDER BY id'
            ).fetchall()
            assert rows_a == rows_b, table
    finally:
        conn_a.close()
        conn_b.close()


def test_migration_refuses_in_place_or_existing_destination(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    with pytest.raises(MigrationError, match="同一路径"):
        _migrate(source, source)

    staged = tmp_path / "existing.db"
    staged.write_bytes(b"do not overwrite")
    with pytest.raises(MigrationError, match="目标已存在"):
        _migrate(source, staged)
    assert staged.read_bytes() == b"do not overwrite"


def test_soft_orphan_fails_verification_without_publishing_staged_db(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    conn = sqlite3.connect(source)
    conn.execute(
        """
        UPDATE inbox_suggestions
        SET suggested_payload = '{"goal_id":999999}'
        WHERE id = 160
        """
    )
    conn.commit()
    conn.close()
    before_hash = _digest(source)
    staged = tmp_path / "staged.db"

    with pytest.raises(VerificationError, match="suggested_payload"):
        _migrate(source, staged)

    assert not staged.exists()
    assert _digest(source) == before_hash


@pytest.mark.parametrize(
    "suggested_payload",
    (
        '{"goal_id":"not-an-id"}',
        '{"related_type":"unknown","related_id":10}',
        '{"related_type":"project","related_id":"not-an-id"}',
    ),
)
def test_malformed_suggested_payload_reference_fails_closed(
    tmp_path, suggested_payload
):
    source = _create_legacy(tmp_path / "legacy.db")
    conn = sqlite3.connect(source)
    conn.execute(
        "UPDATE inbox_suggestions SET suggested_payload = ? WHERE id = 160",
        (suggested_payload,),
    )
    conn.commit()
    conn.close()
    before_hash = _digest(source)
    staged = tmp_path / "staged.db"

    with pytest.raises(VerificationError, match="suggested_payload"):
        _migrate(source, staged)

    assert not staged.exists()
    assert _digest(source) == before_hash


def test_multiple_legacy_positioning_anchors_fail_without_data_loss(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    conn = sqlite3.connect(source)
    conn.execute(
        """
        INSERT INTO positioning_anchor (
            id, first_principle, identity_core, flywheel_def,
            current_stage, north_star, updated_at
        ) VALUES (121, 'second', '', '', '', '', '2026-01-13')
        """
    )
    conn.commit()
    conn.close()
    before_hash = _digest(source)
    staged = tmp_path / "staged.db"

    with pytest.raises(MigrationError, match="positioning_anchor 超过一行"):
        _migrate(source, staged)

    assert not staged.exists()
    assert _digest(source) == before_hash


def test_migration_preserves_valid_feedback_source_relation(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    conn = sqlite3.connect(source)
    conn.execute(
        """
        UPDATE assets
        SET source_type = 'feedback', source_id = 100
        WHERE id = 50
        """
    )
    conn.commit()
    conn.close()
    staged = tmp_path / "staged.db"

    result = _migrate(source, staged)
    assert result["ok"] is True
    assert result["repaired_orphans"] == []
    report = result["verification"]
    assert report["ok"] is True
    assert report["soft_orphans"]["assets.source_id.feedback"] == 0

    staged_conn = sqlite3.connect(staged)
    staged_conn.row_factory = sqlite3.Row
    try:
        asset = staged_conn.execute("SELECT * FROM assets WHERE id = 50").fetchone()
        assert asset["source_type"] == "feedback"
        assert asset["source_id"] == 100
    finally:
        staged_conn.close()


def test_migration_cleanses_orphan_feedback_source_relation_with_audit(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    conn = sqlite3.connect(source)
    conn.execute(
        """
        UPDATE assets
        SET source_type = 'feedback', source_id = 99999
        WHERE id = 50
        """
    )
    conn.commit()
    conn.close()
    before_hash = _digest(source)
    staged = tmp_path / "staged.db"

    result = _migrate(source, staged)
    assert result["ok"] is True
    assert _digest(source) == before_hash
    assert len(result["repaired_orphans"]) == 1
    assert result["repaired_orphans"][0] == {
        "table": "assets",
        "record_id": 50,
        "original_source_type": "feedback",
        "original_source_id": 99999,
        "remediation": "cleared_to_null",
        "reason": "referenced_feedback_not_found",
    }
    report = result["verification"]
    assert report["ok"] is True
    assert report["soft_orphans"]["assets.source_id.feedback"] == 0
    assert report["repaired_orphans"] == result["repaired_orphans"]

    staged_conn = sqlite3.connect(staged)
    staged_conn.row_factory = sqlite3.Row
    try:
        asset = staged_conn.execute("SELECT * FROM assets WHERE id = 50").fetchone()
        assert asset["source_type"] == ""
        assert asset["source_id"] is None
        assert asset["title"] == "JSON/Unicode 资产"
        assert asset["fields"] == '{"步骤":["一","二"],"score":3}'
    finally:
        staged_conn.close()


def test_migration_handles_opportunity_experiment_review_sources(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    conn = sqlite3.connect(source)
    # Insert assets pointing to valid and invalid opportunity/experiment/review
    conn.execute(
        """
        INSERT INTO assets (
            id, title, trigger_context, core_content, asset_type,
            capability_tags, source_review_id, created_at, summary,
            fields, reusable_scenario, maturity, reuse_count,
            source_type, source_id, updated_at, asset_level, evidence,
            external_expression, transferable_scene, productization_next_step
        ) VALUES
        (51, 'Valid Opp Asset', '', '', '案例复盘', '[]', NULL, '2026-01-05', '', '{}', '', '', 0, 'opportunity', 80, '2026-01-05', 'L1', '', '', '', ''),
        (52, 'Orphan Opp Asset', '', '', '案例复盘', '[]', NULL, '2026-01-05', '', '{}', '', '', 0, 'opportunity', 88888, '2026-01-05', 'L1', '', '', '', ''),
        (53, 'Valid Exp Asset', '', '', '案例复盘', '[]', NULL, '2026-01-05', '', '{}', '', '', 0, 'experiment', 90, '2026-01-05', 'L1', '', '', '', ''),
        (54, 'Orphan Exp Asset', '', '', '案例复盘', '[]', NULL, '2026-01-05', '', '{}', '', '', 0, 'experiment', 99999, '2026-01-05', 'L1', '', '', '', ''),
        (55, 'Valid Rev Asset', '', '', '案例复盘', '[]', 40, '2026-01-05', '', '{}', '', '', 0, 'review', 40, '2026-01-05', 'L1', '', '', '', ''),
        (56, 'Orphan Rev Asset', '', '', '案例复盘', '[]', NULL, '2026-01-05', '', '{}', '', '', 0, 'review', 44444, '2026-01-05', 'L1', '', '', '', '')
        """
    )
    conn.commit()
    conn.close()
    staged = tmp_path / "staged.db"

    result = _migrate(source, staged)
    assert result["ok"] is True
    repaired = {r["record_id"]: r for r in result["repaired_orphans"]}
    assert set(repaired.keys()) == {52, 54, 56}
    assert repaired[52]["original_source_type"] == "opportunity"
    assert repaired[54]["original_source_type"] == "experiment"
    assert repaired[56]["original_source_type"] == "review"

    report = result["verification"]
    assert report["ok"] is True
    assert all(count == 0 for count in report["soft_orphans"].values())

    staged_conn = sqlite3.connect(staged)
    staged_conn.row_factory = sqlite3.Row
    try:
        # Valid ones retained
        assert staged_conn.execute("SELECT source_type, source_id FROM assets WHERE id = 51").fetchone()["source_id"] == 80
        assert staged_conn.execute("SELECT source_type, source_id FROM assets WHERE id = 53").fetchone()["source_id"] == 90
        assert staged_conn.execute("SELECT source_type, source_id FROM assets WHERE id = 55").fetchone()["source_id"] == 40
        # Orphan ones cleansed
        row_52 = staged_conn.execute("SELECT source_type, source_id FROM assets WHERE id = 52").fetchone()
        assert row_52["source_type"] == "" and row_52["source_id"] is None
        row_54 = staged_conn.execute("SELECT source_type, source_id FROM assets WHERE id = 54").fetchone()
        assert row_54["source_type"] == "" and row_54["source_id"] is None
        row_56 = staged_conn.execute("SELECT source_type, source_id FROM assets WHERE id = 56").fetchone()
        assert row_56["source_type"] == "" and row_56["source_id"] is None
    finally:
        staged_conn.close()


def _setup_valid_migration(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    return source, staged


def test_f22_rejects_extra_table(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("CREATE TABLE unapproved_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="多余未授权表"):
        verify_migration(source, staged)

    res = verify_authoritative_envelope(source, staged)
    assert res["raw_ok"] is False
    assert res["raw_exit"] == 1
    assert any("多余未授权表" in issue for issue in res["issues"])


def test_f22_rejects_missing_table(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("DROP TABLE tasks")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="缺少业务表/用户表"):
        verify_migration(source, staged)


def test_f23_rejects_non_integer_user_id(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("ALTER TABLE tasks RENAME TO tasks_old")
    conn.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待处理',
            priority TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL,
            today_progress INTEGER NOT NULL DEFAULT 0,
            today_progress_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        )
    """)
    conn.execute(
        "INSERT INTO tasks SELECT id, CAST(user_id AS TEXT), project_id, name, status, priority, created_at, today_progress, today_progress_date FROM tasks_old"
    )
    conn.execute("DROP TABLE tasks_old")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="类型不是 INTEGER"):
        verify_migration(source, staged)


def test_f23_rejects_nullable_user_id(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("ALTER TABLE tasks RENAME TO tasks_old")
    conn.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待处理',
            priority TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL,
            today_progress INTEGER NOT NULL DEFAULT 0,
            today_progress_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        )
    """)
    conn.execute(
        "INSERT INTO tasks SELECT id, user_id, project_id, name, status, priority, created_at, today_progress, today_progress_date FROM tasks_old"
    )
    conn.execute("DROP TABLE tasks_old")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="不是 NOT NULL"):
        verify_migration(source, staged)


def test_f23_rejects_unexpected_business_column_drift(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("ALTER TABLE tasks ADD COLUMN unapproved_column TEXT")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="字段集合与权威契约不一致"):
        verify_migration(source, staged)


def test_f24_accepts_required_users_id_fk_plus_composite_fk(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    fks = conn.execute("PRAGMA foreign_key_list(projects)").fetchall()
    conn.close()
    assert len(fks) >= 2
    report = verify_migration(source, staged)
    assert report["ok"] is True


def test_f24_rejects_user_id_to_non_id_target(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("ALTER TABLE tasks RENAME TO tasks_old")
    conn.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待处理',
            priority TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL,
            today_progress INTEGER NOT NULL DEFAULT 0,
            today_progress_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE RESTRICT
        )
    """)
    conn.execute(
        "INSERT INTO tasks SELECT id, user_id, project_id, name, status, priority, created_at, today_progress, today_progress_date FROM tasks_old"
    )
    conn.execute("DROP TABLE tasks_old")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="缺少指向 users\\(id\\) 的外键"):
        verify_migration(source, staged)


def test_f25_rejects_users_column_mismatch(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("ALTER TABLE users ADD COLUMN unapproved_user_col TEXT")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="users 表字段契约不匹配"):
        verify_migration(source, staged)


def test_f28_accepts_legal_source_type_with_null_source_id(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("UPDATE assets SET source_type = 'review', source_id = NULL WHERE id = 50")
    conn.commit()
    conn.close()

    report = verify_migration(source, staged)
    assert report["ok"] is True
    assert report["soft_orphans"]["assets.source_id.review"] == 0


def test_f28_rejects_non_null_dangling_soft_relation(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("UPDATE assets SET source_type = 'review', source_id = 999999 WHERE id = 50")
    conn.commit()
    conn.close()

    with pytest.raises(VerificationError, match="软关联孤儿"):
        verify_migration(source, staged)


def test_u01_diagnostic_source_contains_users_does_not_change_verdict(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0
    assert result["diagnostics"]["legacy_source"]["has_users_table"] is True


def test_u02_diagnostic_source_column_drift_does_not_change_verdict(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(source)
    conn.execute("ALTER TABLE tasks ADD COLUMN extra_legacy_col TEXT")
    conn.commit()
    conn.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0
    assert "tasks" in result["diagnostics"]["legacy_source"]["column_mismatches"]


def test_u03_diagnostic_source_contains_user_id_does_not_change_verdict(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(source)
    conn.execute("ALTER TABLE tasks ADD COLUMN user_id INTEGER")
    conn.commit()
    conn.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0
    assert "tasks" in result["diagnostics"]["legacy_source"]["tables_with_user_id"]


def test_u04_diagnostic_source_positioning_anchor_gt_1_does_not_change_verdict(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(source)
    conn.execute(
        """
        INSERT INTO positioning_anchor (
            id, first_principle, identity_core, flywheel_def,
            current_stage, north_star, updated_at
        ) VALUES (999, 'p', 'i', 'f', 'c', 'n', '2026-01-01')
        """
    )
    conn.commit()
    conn.close()

    conn_staged = sqlite3.connect(staged)
    conn_staged.execute("ALTER TABLE positioning_anchor RENAME TO positioning_anchor_old")
    conn_staged.execute(
        """
        CREATE TABLE positioning_anchor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            first_principle TEXT NOT NULL DEFAULT '',
            identity_core TEXT NOT NULL DEFAULT '',
            flywheel_def TEXT NOT NULL DEFAULT '',
            current_stage TEXT NOT NULL DEFAULT '',
            north_star TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )
    conn_staged.execute("INSERT INTO positioning_anchor SELECT * FROM positioning_anchor_old")
    conn_staged.execute(
        """
        INSERT INTO positioning_anchor (
            id, user_id, first_principle, identity_core, flywheel_def,
            current_stage, north_star, updated_at
        ) VALUES (999, 1, 'p', 'i', 'f', 'c', 'n', '2026-01-01')
        """
    )
    conn_staged.execute("DROP TABLE positioning_anchor_old")
    conn_staged.commit()
    conn_staged.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0
    assert result["diagnostics"]["legacy_source"]["positioning_anchor_count"] == 2


def test_u05_diagnostic_bidirectional_except_does_not_change_verdict(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("UPDATE tasks SET name = 'mutated task name' WHERE id = 30")
    conn.commit()
    conn.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0
    assert result["diagnostics"]["except_checks"]["tasks"]["legacy_except_staged"] == 1


def test_u06_diagnostic_business_table_sequence_drift_does_not_change_verdict(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("UPDATE sqlite_sequence SET seq = 9999 WHERE name = 'tasks'")
    conn.commit()
    conn.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0
    assert result["diagnostics"]["sequence_checks"]["tasks"]["sequence_matches"] is False


def test_u07_diagnostic_hard_relation_custom_sql_does_not_change_verdict(tmp_path, monkeypatch):
    source, staged = _setup_valid_migration(tmp_path)
    import v22_migration
    monkeypatch.setattr(
        v22_migration,
        "_verify_hard_relations",
        lambda conn, staged_tables=None: ({"mock.relation": 1}, ["mock hard relation orphan issue"]),
    )

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0
    assert result["diagnostics"]["hard_orphans"]["counts"]["mock.relation"] == 1


def test_u08_leading_user_index_not_in_blocking_path(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.row_factory = sqlite3.Row
    for row in conn.execute("PRAGMA index_list(tasks)").fetchall():
        conn.execute(f'DROP INDEX IF EXISTS "{row["name"]}"')
    conn.commit()
    conn.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["ok"] is True
    assert result["raw_exit"] == 0


def test_pre_failure_prevents_semantic_db_open(tmp_path):
    source = tmp_path / "corrupt_source.db"
    source.write_bytes(b"NOT A SQLITE FILE HEADER")
    staged = tmp_path / "staged.db"
    staged.write_bytes(b"NOT A SQLITE FILE HEADER")

    def forbidden_db_opener(*args, **kwargs):
        raise AssertionError("DB opener should NOT have been called on PRE failure!")

    result = verify_authoritative_envelope(
        source, staged, db_opener=forbidden_db_opener
    )
    assert result["pre_ok"] is False
    assert result["raw_ok"] is False
    assert result["raw_exit"] == 1
    assert result["semantic_ok"] is False
    assert result["post_ok"] is False


def test_semantic_failure_cannot_skip_post_audit_after_db_access_begins(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    conn = sqlite3.connect(staged)
    conn.execute("CREATE TABLE unapproved_extra_table (id INT)")
    conn.commit()
    conn.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["pre_ok"] is True
    assert result["connection_safety_ok"] is True
    assert result["semantic_ok"] is False
    assert result["post_ok"] is True
    assert result["raw_ok"] is False
    assert result["raw_exit"] == 1


def test_post_failure_forces_raw_fail(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)

    def mutating_db_opener(src, stg):
        sidecar = Path(str(stg) + "-wal")
        sidecar.write_bytes(b"rogue wal file")
        return verify_migration(src, stg)

    result = verify_authoritative_envelope(
        source, staged, db_opener=mutating_db_opener
    )
    assert result["pre_ok"] is True
    assert result["semantic_ok"] is True
    assert result["post_ok"] is False
    assert any("F-36" in issue for issue in result["post_issues"])
    assert result["raw_ok"] is False
    assert result["raw_exit"] == 1


def test_no_diagnostic_can_convert_raw_fail_to_pass(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    # Inject real blocking failure: F-21 wrong user_version
    conn = sqlite3.connect(staged)
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()

    # Also inject diagnostic: source has users table (U-01)
    conn_src = sqlite3.connect(source)
    conn_src.execute("CREATE TABLE users (id INT)")
    conn_src.commit()
    conn_src.close()

    result = verify_authoritative_envelope(source, staged)
    assert result["diagnostics"]["legacy_source"]["has_users_table"] is True
    assert result["semantic_ok"] is False
    assert result["raw_ok"] is False
    assert result["raw_exit"] == 1


def test_preflight_strict_shadow_layout_checks_and_absence(tmp_path):
    source, staged = _setup_valid_migration(tmp_path)
    instance_root = tmp_path / "shadow-01"
    for sub in ("source", "migration", "manifests", "staged"):
        (instance_root / sub).mkdir(parents=True)
    databases_root = tmp_path / "databases"
    databases_root.mkdir(parents=True)

    # Absence targets
    staged_dest = instance_root / "staged" / "yd_os-v22-shadow.db"
    manifest_path = instance_root / "manifests" / "yd_os-v22-shadow.db.manifest.json"

    # 1. When files strictly absent -> pre_ok should pass
    pre_ok, issues, _ = audit_preflight(
        source,
        staged,
        staged_dest=staged_dest,
        manifest_path=manifest_path,
        instance_root=instance_root,
        databases_root=databases_root,
    )
    assert pre_ok is True
    assert issues == []

    # 2. If staged_dest exists -> F-16 failure
    staged_dest.write_bytes(b"existing staged db")
    pre_ok, issues, _ = audit_preflight(
        source,
        staged,
        staged_dest=staged_dest,
        manifest_path=manifest_path,
    )
    assert pre_ok is False
    assert any("F-16" in issue for issue in issues)
    staged_dest.unlink()

    # 3. If manifest exists -> F-18 failure
    manifest_path.write_text("{}", encoding="utf-8")
    pre_ok, issues, _ = audit_preflight(
        source,
        staged,
        staged_dest=staged_dest,
        manifest_path=manifest_path,
    )
    assert pre_ok is False
    assert any("F-18" in issue for issue in issues)
    manifest_path.unlink()

    # 4. If sidecar exists on staged_dest -> F-17 failure
    staged_sidecar = Path(str(staged_dest) + "-wal")
    staged_sidecar.write_bytes(b"wal")
    pre_ok, issues, _ = audit_preflight(
        source,
        staged,
        staged_dest=staged_dest,
        manifest_path=manifest_path,
    )
    assert pre_ok is False
    assert any("F-17" in issue for issue in issues)
    staged_sidecar.unlink()

