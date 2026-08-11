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
    VerificationError,
    migrate_legacy_database,
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
