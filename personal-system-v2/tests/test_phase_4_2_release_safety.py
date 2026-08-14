import hashlib
import importlib.util
import json
import os
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import auth_service
import database
import production
import release_switch
from database_artifacts import (
    DatabaseArtifactError,
    create_database_manifest,
    create_verified_backup,
    inspect_database,
    restore_verified_backup,
    verify_database_artifact,
)
from release_switch import (
    ReleaseSwitchError,
    activate_release_pointer,
    create_release_descriptor,
    resolve_active_release,
    verify_release_descriptor,
)
from v22_migration import (
    LEGACY_V214_COLUMNS,
    MigrationError,
    VerificationError,
    migrate_legacy_database,
    verify_migration,
)


FIXTURE_SQL = Path(__file__).parent / "fixtures" / "legacy_v214.sql"
HEAD_COMMIT = "fa7f01486cb36e765544b8f55c60c145a83df0ae"
LEGACY_COMMIT = "1" * 40
STRONG_SECRET = "K9vQ2mL7xR4cT8pN5wD3jH6sF1zB0yG8uC4aE7rM2kP9nV5q"
STRONG_PROXY_TOKEN = "R7wK4nT9pL2xV6cH1mQ8sD5fJ3zB0yG9uN4aE7rM2kP6vC8q"


def _create_legacy(path):
    connection = sqlite3.connect(path)
    connection.executescript(FIXTURE_SQL.read_text(encoding="utf-8"))
    connection.close()
    return Path(path)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _migrate(source, staged):
    return migrate_legacy_database(
        source,
        staged,
        admin_username="migration-admin",
        admin_email="migration-admin@example.com",
        admin_password="correct horse battery",
    )


def _manifest_for_staged(source, staged, manifest):
    return create_database_manifest(
        staged.resolve(),
        manifest.resolve(),
        expected_profile="v22",
        artifact_kind="migration-staged",
        source_path=source.resolve(),
        source_profile="legacy_v214",
        git_commit=HEAD_COMMIT,
        application_version="v2.2.0",
    )


def _make_code_release(tmp_path, name, marker):
    code_root = tmp_path / name
    code_root.mkdir()
    entrypoint = code_root / "production.py"
    config_path = code_root / "runtime.env"
    entrypoint.write_text(f"# {marker} entrypoint\n", encoding="utf-8")
    config_path.write_text(f"APP_VERSION={marker}\n", encoding="utf-8")
    return code_root, entrypoint, config_path


def _make_v22_descriptor_inputs(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    manifest = tmp_path / "staged.manifest.json"
    _manifest_for_staged(source, staged, manifest)
    code_root, entrypoint, config_path = _make_code_release(
        tmp_path, "v22-code", "descriptor-mode"
    )
    return {
        "release_id": "descriptor-mode-test",
        "application_version": "v2.2.0",
        "git_commit": HEAD_COMMIT,
        "code_root": code_root.resolve(),
        "code_entrypoint": entrypoint.resolve(),
        "config_path": config_path.resolve(),
        "database_path": staged.resolve(),
        "database_manifest_path": manifest.resolve(),
        "expected_profile": "v22",
    }


def _legacy_backup(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = create_verified_backup(
        source.resolve(),
        backup_dir.resolve(),
        expected_profile="legacy_v214",
        git_commit=LEGACY_COMMIT,
        application_version="v2.1.4",
    )
    return source, backup


def _load_backup_script():
    script = Path(__file__).resolve().parents[2] / "scripts" / "backup-db.py"
    spec = importlib.util.spec_from_file_location("phase42_backup_cli", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_environment(monkeypatch, db_path):
    monkeypatch.setattr(config_module(), "_PRODUCTION_PREFLIGHT_PATH", None)
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.setenv("PERSONAL_OS_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_HOSTS", "psy.example.test")
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    monkeypatch.setenv("PERSONAL_OS_PROXY_TOKEN", STRONG_PROXY_TOKEN)
    monkeypatch.setenv("YD_OS_DB_PATH", str(Path(db_path).resolve()))
    monkeypatch.setenv("SECRET_KEY", STRONG_SECRET)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)


def config_module():
    import config

    return config


def test_verified_backup_manifest_and_restore_are_complete_and_private(tmp_path):
    source, backup = _legacy_backup(tmp_path)
    manifest = json.loads(Path(backup["manifest"]).read_text(encoding="utf-8"))

    assert backup["source_unchanged"] is True
    assert manifest["format"] == "psy-sqlite-artifact/v1"
    assert manifest["source"]["path"] == str(source.resolve())
    assert manifest["application"] == {
        "git_commit": LEGACY_COMMIT,
        "version": "v2.1.4",
    }
    artifact = manifest["artifact"]
    assert artifact["size_bytes"] > 0
    assert len(artifact["sha256"]) == 64
    assert artifact["schema_profile"] == "legacy_v214"
    assert artifact["schema_version"] == 0
    assert set(artifact["tables"]) == set(database.PERSONAL_DATA_TABLES)
    assert set(artifact["row_counts"]) == set(database.PERSONAL_DATA_TABLES)
    assert all(value == 1 for value in artifact["row_counts"].values())
    assert artifact["users_total"] is None
    assert artifact["integrity_check"] == "ok"
    assert artifact["foreign_key_check_rows"] == 0
    serialized = json.dumps(manifest, ensure_ascii=False).casefold()
    for forbidden in (
        "password_hash",
        "secret_key",
        "session",
        "correct horse battery",
        "保留主线 id",
        "json/unicode 资产",
    ):
        assert forbidden not in serialized

    restored = tmp_path / "restored-v214.db"
    restore = restore_verified_backup(
        Path(backup["database"]),
        Path(backup["manifest"]),
        restored.resolve(),
        expected_profile="legacy_v214",
    )
    assert restore["ok"] is True
    assert restore["sha256"] == artifact["sha256"]
    assert restore["row_counts"] == artifact["row_counts"]


def test_backup_cli_requires_explicit_absolute_paths(tmp_path, capsys):
    module = _load_backup_script()
    source = _create_legacy(tmp_path / "legacy.db")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    with pytest.raises(DatabaseArtifactError, match="absolute"):
        module.backup_database(
            Path("legacy.db"),
            backup_dir.resolve(),
            expected_profile="legacy_v214",
            git_commit=LEGACY_COMMIT,
            application_version="v2.1.4",
        )
    exit_code = module.main(
        [
            "create",
            "--source",
            str(source.resolve()),
            "--backup-dir",
            str(backup_dir.resolve()),
            "--schema-profile",
            "legacy_v214",
            "--git-commit",
            LEGACY_COMMIT,
            "--app-version",
            "v2.1.4",
        ]
    )
    assert exit_code == 0
    assert '"ok": true' in capsys.readouterr().out


def test_manifest_and_switch_cli_help_are_available():
    root = Path(__file__).resolve().parents[2]
    for script_name in ("manifest-db.py", "switch-release.py"):
        completed = subprocess.run(
            [sys.executable, str(root / "scripts" / script_name), "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "usage:" in completed.stdout.casefold()


def test_backup_targets_are_never_overwritten_and_write_failures_publish_nothing(
    tmp_path,
):
    source = _create_legacy(tmp_path / "legacy.db")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    timestamp = "2026-08-13T01:02:03.123456+00:00"
    first = create_verified_backup(
        source.resolve(),
        backup_dir.resolve(),
        expected_profile="legacy_v214",
        git_commit=LEGACY_COMMIT,
        application_version="v2.1.4",
        timestamp=timestamp,
    )
    before_hash = _digest(first["database"])
    with pytest.raises(DatabaseArtifactError, match="overwrite"):
        create_verified_backup(
            source.resolve(),
            backup_dir.resolve(),
            expected_profile="legacy_v214",
            git_commit=LEGACY_COMMIT,
            application_version="v2.1.4",
            timestamp=timestamp,
        )
    assert _digest(first["database"]) == before_hash

    failed_dir = tmp_path / "failed"
    failed_dir.mkdir()

    def fail_before_publish(stage):
        if stage == "before_publish":
            raise OSError("simulated disk write failure")

    with pytest.raises(OSError, match="simulated disk"):
        create_verified_backup(
            source.resolve(),
            failed_dir.resolve(),
            expected_profile="legacy_v214",
            git_commit=LEGACY_COMMIT,
            application_version="v2.1.4",
            failure_hook=fail_before_publish,
        )
    assert list(failed_dir.iterdir()) == []


def test_backup_detects_source_change_during_snapshot(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    def mutate_source(stage):
        if stage == "after_sqlite_backup":
            connection = sqlite3.connect(source)
            connection.execute("UPDATE goals SET name = 'concurrent write' WHERE id = 10")
            connection.commit()
            connection.close()

    with pytest.raises(DatabaseArtifactError, match="changed during backup"):
        create_verified_backup(
            source.resolve(),
            backup_dir.resolve(),
            expected_profile="legacy_v214",
            git_commit=LEGACY_COMMIT,
            application_version="v2.1.4",
            failure_hook=mutate_source,
        )
    assert list(backup_dir.iterdir()) == []


@pytest.mark.parametrize("target", ["manifest", "database"])
def test_manifest_or_backup_tampering_fails_closed(tmp_path, target):
    _source, backup = _legacy_backup(tmp_path)
    artifact = Path(backup["database"])
    manifest = Path(backup["manifest"])
    target_path = manifest if target == "manifest" else artifact
    target_path.chmod(0o600)
    with target_path.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(
        DatabaseArtifactError,
        match="checksum|mismatch|integrity|cannot be read",
    ):
        verify_database_artifact(
            artifact,
            manifest,
            expected_profile="legacy_v214",
        )


def test_manifest_checksum_tampering_fails_closed(tmp_path):
    _source, backup = _legacy_backup(tmp_path)
    checksum = Path(str(backup["manifest"]) + ".sha256")
    checksum.chmod(0o600)
    checksum.write_text("0" * 64 + "\n", encoding="ascii")
    with pytest.raises(DatabaseArtifactError, match="checksum mismatch"):
        verify_database_artifact(
            Path(backup["database"]),
            Path(backup["manifest"]),
            expected_profile="legacy_v214",
        )


def test_manifest_row_counts_table_set_and_profile_are_enforced(tmp_path):
    source, backup = _legacy_backup(tmp_path)
    manifest = Path(backup["manifest"])
    checksum = Path(str(manifest) + ".sha256")
    manifest.chmod(0o600)
    checksum.chmod(0o600)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifact"]["row_counts"]["goals"] = 999
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    manifest.write_bytes(raw)
    checksum.write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")
    with pytest.raises(DatabaseArtifactError, match="row_counts"):
        verify_database_artifact(
            Path(backup["database"]),
            manifest,
            expected_profile="legacy_v214",
        )

    with pytest.raises(DatabaseArtifactError, match="schema version|table set"):
        inspect_database(source.resolve(), expected_profile="v22")


def test_corrupt_legacy_and_staged_databases_fail_closed(tmp_path):
    corrupt_legacy = tmp_path / "corrupt-legacy.db"
    corrupt_legacy.write_bytes(b"not a sqlite database")
    with pytest.raises(DatabaseArtifactError):
        inspect_database(corrupt_legacy.resolve(), expected_profile="legacy_v214")
    with pytest.raises((MigrationError, sqlite3.DatabaseError)):
        _migrate(corrupt_legacy, tmp_path / "never.db")

    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    staged.write_bytes(b"not a staged database")
    with pytest.raises((VerificationError, sqlite3.DatabaseError)):
        verify_migration(source, staged)


def test_migration_interruption_and_existing_staged_preserve_source(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    before_hash = _digest(source)
    before_stat = source.stat()
    interrupted = tmp_path / "interrupted.db"

    def fail_after_first(table, _count):
        if table == "goals":
            raise RuntimeError("simulated migration interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        migrate_legacy_database(
            source,
            interrupted,
            admin_username="migration-admin",
            admin_email="migration-admin@example.com",
            admin_password="correct horse battery",
            failure_hook=fail_after_first,
        )
    assert not interrupted.exists()
    assert _digest(source) == before_hash
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns

    existing = tmp_path / "existing.db"
    existing.write_bytes(b"do-not-overwrite")
    with pytest.raises(MigrationError, match="目标已存在"):
        _migrate(source, existing)
    assert existing.read_bytes() == b"do-not-overwrite"


def test_full_migration_backup_preflight_and_application_smoke(
    tmp_path, monkeypatch
):
    source = _create_legacy(tmp_path / "legacy.db")
    source_hash = _digest(source)
    source_bytes = source.read_bytes()
    source_stat = source.stat()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = create_verified_backup(
        source.resolve(),
        backup_dir.resolve(),
        expected_profile="legacy_v214",
        git_commit=LEGACY_COMMIT,
        application_version="v2.1.4",
    )
    staged = tmp_path / "staged-v22.db"
    migration = _migrate(source, staged)
    verification = verify_migration(source, staged)
    staged_manifest = tmp_path / "staged-v22.db.manifest.json"
    _manifest_for_staged(source, staged, staged_manifest)

    assert source.read_bytes() == source_bytes
    assert _digest(source) == source_hash
    assert source.stat().st_size == source_stat.st_size
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns
    assert backup["artifact"]["row_counts"] == {
        table: 1 for table in database.PERSONAL_DATA_TABLES
    }
    assert migration["verification"]["tables"] == verification["tables"]
    assert migration["verification"]["hard_orphans"] == verification["hard_orphans"]
    assert migration["verification"]["soft_orphans"] == verification["soft_orphans"]
    assert verification["users_total"] == 1
    assert verification["active_admins"] == 1
    assert verification["integrity_check"] == "ok"
    assert verification["foreign_key_check_rows"] == 0
    assert all(value == 0 for value in verification["hard_orphans"].values())
    assert all(value == 0 for value in verification["soft_orphans"].values())
    for report in verification["tables"].values():
        assert report["legacy_count"] == report["staged_admin_count"]
        assert report["null_user_id"] == report["other_owner_count"] == 0
        assert report["legacy_except_staged"] == 0
        assert report["staged_except_legacy"] == 0
        assert report["missing_primary_keys"] == 0
        assert report["legacy_sequence"] == report["staged_sequence"]

    connection = sqlite3.connect(staged)
    connection.row_factory = sqlite3.Row
    try:
        admin_id = verification["admin_id"]
        goal = connection.execute(
            "SELECT id, name, created_at, user_id FROM goals WHERE id = 10"
        ).fetchone()
        asset = connection.execute(
            "SELECT id, fields, capability_tags, created_at, user_id "
            "FROM assets WHERE id = 50"
        ).fetchone()
        assert dict(goal) == {
            "id": 10,
            "name": "保留主线 ID",
            "created_at": "2026-01-01T01:02:03+00:00",
            "user_id": admin_id,
        }
        assert asset["fields"] == '{"步骤":["一","二"],"score":3}'
        assert asset["capability_tags"] == '["体系力","AI驾驭力"]'
        assert asset["created_at"] == "2026-01-05T01:02:03+00:00"
        assert asset["user_id"] == admin_id
    finally:
        connection.close()

    monkeypatch.setattr(database, "DB_PATH", str(staged.resolve()))
    _production_environment(monkeypatch, staged)
    preflight = production.run_preflight(require_release_context=False)
    assert preflight["schema_version"] == 220
    assert preflight["active_admins"] == 1

    smoke_script = """
import json
import production

application = production.create_app(require_release_context=False)
application.config.update(TESTING=True)
response = application.test_client().get(
    '/api/health',
    headers={'Host': '127.0.0.1'},
    environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
)
assert response.status_code == 200, response.get_data(as_text=True)
assert response.get_json() == {'ok': True, 'data': {'status': 'up'}}
print(json.dumps({'ok': True, 'status': response.status_code}))
"""
    smoke = subprocess.run(
        [sys.executable, "-c", smoke_script],
        cwd=Path(__file__).parents[1],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert smoke.returncode == 0, smoke.stderr
    assert json.loads(smoke.stdout)["ok"] is True

    admin = auth_service.get_user(verification["admin_id"])
    assert database.get_goal(10, admin.id)["name"] == "保留主线 ID"
    assert database.get_asset(50, admin.id)["title"] == "JSON/Unicode 资产"
    new_user, _temporary = auth_service.create_standard_user(
        "empty-user", "empty-user@example.com"
    )
    for table in set(database.PERSONAL_DATA_TABLES) - {
        "capability_practice_steps"
    }:
        connection = database.get_connection()
        try:
            assert connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE user_id = ?',
                (new_user["id"],),
            ).fetchone()[0] == 0
        finally:
            connection.close()


def test_migration_verifier_rejects_disabled_bootstrap_admin(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    connection = sqlite3.connect(staged)
    connection.execute("UPDATE users SET is_active = 0 WHERE role = 'admin'")
    connection.commit()
    connection.close()
    with pytest.raises(VerificationError, match="启用"):
        verify_migration(source, staged)


def test_production_preflight_rejects_sqlite_integrity_failure(tmp_path, monkeypatch):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    raw = bytearray(staged.read_bytes())
    raw[100:108] = b"BADPAGE!"
    staged.write_bytes(raw)
    monkeypatch.setattr(database, "DB_PATH", str(staged.resolve()))
    _production_environment(monkeypatch, staged)
    with pytest.raises(production.ProductionPreflightError):
        production.run_preflight(require_release_context=False)


def test_artifact_and_production_preflight_reject_soft_orphans(tmp_path, monkeypatch):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    connection = sqlite3.connect(staged)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        "UPDATE inbox_suggestions "
        "SET suggested_payload = '{\"goal_id\":999999}' WHERE id = 160"
    )
    connection.commit()
    connection.close()
    with pytest.raises(DatabaseArtifactError, match="soft relation"):
        inspect_database(staged.resolve(), expected_profile="v22")
    monkeypatch.setattr(database, "DB_PATH", str(staged.resolve()))
    _production_environment(monkeypatch, staged)
    with pytest.raises(production.ProductionPreflightError, match="软关联"):
        production.run_preflight(require_release_context=False)


@pytest.mark.parametrize(
    "mutation,match",
    (
        ("wrong_version", "schema"),
        ("no_admin", "administrator|admin"),
        ("multiple_admins", "administrator|admin"),
        ("fk_violation", "foreign_key"),
        ("extra_table", "table set"),
    ),
)
def test_invalid_v22_candidates_fail_artifact_and_production_preflight(
    tmp_path, monkeypatch, mutation, match
):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "candidate.db"
    _migrate(source, staged)
    connection = sqlite3.connect(staged)
    try:
        if mutation == "wrong_version":
            connection.execute("PRAGMA user_version = 219")
        elif mutation == "no_admin":
            connection.execute("UPDATE users SET role = 'user'")
        elif mutation == "multiple_admins":
            connection.execute(
                """
                INSERT INTO users (
                    username, email, password_hash, role, is_active,
                    must_change_password, auth_version, failed_login_count,
                    created_at, updated_at
                ) VALUES ('other-admin', 'other@example.com', 'hash', 'admin', 1,
                          0, 1, 0, 'now', 'now')
                """
            )
        elif mutation == "fk_violation":
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("UPDATE tasks SET project_id = 999999 WHERE id = 30")
        else:
            connection.execute("CREATE TABLE unexpected_release_table (id INTEGER)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(DatabaseArtifactError, match=match):
        inspect_database(staged.resolve(), expected_profile="v22")
    monkeypatch.setattr(database, "DB_PATH", str(staged.resolve()))
    _production_environment(monkeypatch, staged)
    with pytest.raises(production.ProductionPreflightError):
        production.run_preflight(require_release_context=False)


def test_production_preflight_rejects_missing_relative_empty_and_legacy(
    tmp_path, monkeypatch
):
    import config

    _production_environment(monkeypatch, tmp_path / "missing.db")
    monkeypatch.setattr(database, "DB_PATH", str((tmp_path / "missing.db").resolve()))
    with pytest.raises(production.ProductionPreflightError, match="不存在|访问"):
        production.run_preflight(require_release_context=False)

    monkeypatch.setenv("YD_OS_DB_PATH", "relative.db")
    with pytest.raises((production.ProductionPreflightError, RuntimeError), match="绝对"):
        production.run_preflight(require_release_context=False)

    empty = tmp_path / "empty.db"
    empty.touch()
    monkeypatch.setenv("YD_OS_DB_PATH", str(empty.resolve()))
    monkeypatch.setattr(database, "DB_PATH", str(empty.resolve()))
    with pytest.raises(production.ProductionPreflightError, match="非空"):
        production.run_preflight(require_release_context=False)

    legacy = _create_legacy(tmp_path / "legacy.db")
    monkeypatch.setenv("YD_OS_DB_PATH", str(legacy.resolve()))
    monkeypatch.setattr(database, "DB_PATH", str(legacy.resolve()))
    config._PRODUCTION_PREFLIGHT_PATH = None
    with pytest.raises(production.ProductionPreflightError, match="v2.2"):
        production.run_preflight(require_release_context=False)


def test_release_descriptor_sets_0644_before_file_fsync(tmp_path, monkeypatch):
    descriptor = (tmp_path / "release.json").resolve()
    inputs = _make_v22_descriptor_inputs(tmp_path)
    real_os = release_switch.os
    events = []

    class PosixModeOS:
        name = "posix"

        def __getattr__(self, name):
            return getattr(real_os, name)

        def fchmod(self, file_descriptor, mode):
            events.append(("fchmod", mode))
            if hasattr(real_os, "fchmod"):
                real_os.fchmod(file_descriptor, mode)

        def fsync(self, file_descriptor):
            events.append(("fsync", None))
            real_os.fsync(file_descriptor)

    monkeypatch.setattr(release_switch, "os", PosixModeOS())
    report = create_release_descriptor(descriptor, **inputs)

    assert events == [("fchmod", 0o644), ("fsync", None)]
    assert events[0][1] & (stat.S_IWGRP | stat.S_IWOTH) == 0
    assert report["descriptor"] == str(descriptor)
    assert len(report["descriptor_sha256"]) == 64
    with pytest.raises(ReleaseSwitchError, match="already exists"):
        create_release_descriptor(descriptor, **inputs)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode verification requires POSIX")
def test_release_descriptor_is_0644_under_umask_077(tmp_path):
    descriptor = (tmp_path / "release.json").resolve()
    inputs = _make_v22_descriptor_inputs(tmp_path)
    previous_umask = os.umask(0o077)
    try:
        create_release_descriptor(descriptor, **inputs)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(descriptor.stat().st_mode) == 0o644


def test_release_descriptor_fchmod_failure_publishes_no_artifact(
    tmp_path, monkeypatch
):
    descriptor = (tmp_path / "release.json").resolve()
    inputs = _make_v22_descriptor_inputs(tmp_path)
    real_os = release_switch.os
    events = []

    class FailingFchmodOS:
        name = "posix"

        def __getattr__(self, name):
            return getattr(real_os, name)

        @staticmethod
        def fchmod(_file_descriptor, _mode):
            events.append("fchmod")
            raise OSError("simulated descriptor fchmod failure")

        def fsync(self, file_descriptor):
            events.append("fsync")
            real_os.fsync(file_descriptor)

    monkeypatch.setattr(release_switch, "os", FailingFchmodOS())
    with pytest.raises(ReleaseSwitchError, match="failed writing file"):
        create_release_descriptor(descriptor, **inputs)

    assert events == ["fchmod"]
    assert not descriptor.exists()
    with pytest.raises(ReleaseSwitchError, match="does not exist"):
        verify_release_descriptor(
            descriptor,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )


def test_malformed_or_non_regular_release_descriptor_fails_closed(tmp_path):
    malformed = (tmp_path / "malformed-release.json").resolve()
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ReleaseSwitchError, match="not valid UTF-8 JSON"):
        verify_release_descriptor(
            malformed,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )

    non_regular = (tmp_path / "release-directory").resolve()
    non_regular.mkdir()
    with pytest.raises(ReleaseSwitchError, match="non-empty regular file"):
        verify_release_descriptor(
            non_regular,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )


def test_atomic_switch_interruption_wrong_pair_and_manifest_mismatch_fail_closed(
    tmp_path, monkeypatch
):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    staged_manifest = tmp_path / "staged.manifest.json"
    _manifest_for_staged(source, staged, staged_manifest)
    code_root, entrypoint, config_path = _make_code_release(
        tmp_path, "v22-code", "v2.2.0"
    )
    descriptor = tmp_path / "v22-release.json"
    create_release_descriptor(
        descriptor.resolve(),
        release_id="v22-test-release",
        application_version="v2.2.0",
        git_commit=HEAD_COMMIT,
        code_root=code_root.resolve(),
        code_entrypoint=entrypoint.resolve(),
        config_path=config_path.resolve(),
        database_path=staged.resolve(),
        database_manifest_path=staged_manifest.resolve(),
        expected_profile="v22",
    )
    real_os = release_switch.os
    fchmod_calls = []
    pointer_events = []

    class PosixModeOS:
        name = "posix"

        def __getattr__(self, name):
            return getattr(real_os, name)

        def fchmod(self, file_descriptor, mode):
            fchmod_calls.append((file_descriptor, mode))
            pointer_events.append(("fchmod", mode))
            if hasattr(real_os, "fchmod"):
                real_os.fchmod(file_descriptor, mode)

        def replace(self, source, destination):
            pointer_events.append(("replace", None))
            real_os.replace(source, destination)

    monkeypatch.setattr(release_switch, "os", PosixModeOS())
    pointer = tmp_path / "active-release.json"
    activate_release_pointer(
        descriptor.resolve(),
        pointer.resolve(),
        service_is_stopped=True,
        expected_git_commit=HEAD_COMMIT,
        expected_application_version="v2.2.0",
    )
    assert [mode for _file_descriptor, mode in fchmod_calls] == [0o644]
    assert pointer_events == [("fchmod", 0o644), ("replace", None)]
    assert fchmod_calls[0][1] & (stat.S_IWGRP | stat.S_IWOTH) == 0
    if os.name != "nt":
        assert stat.S_IMODE(pointer.stat().st_mode) == 0o644
    old_pointer = pointer.read_bytes()

    with pytest.raises(ReleaseSwitchError, match="stopped"):
        activate_release_pointer(
            descriptor.resolve(),
            pointer.resolve(),
            service_is_stopped=False,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
        )

    def interrupt(_stage):
        raise RuntimeError("simulated switch interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        activate_release_pointer(
            descriptor.resolve(),
            pointer.resolve(),
            service_is_stopped=True,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            failure_hook=interrupt,
        )
    assert pointer.read_bytes() == old_pointer

    with pytest.raises(ReleaseSwitchError, match="commit"):
        resolve_active_release(
            pointer.resolve(),
            expected_git_commit="f" * 40,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )

    wrong_pointer = tmp_path / "wrong-active.json"
    wrong_pointer.write_text(
        json.dumps(
            {
                "format": "psy-active-release/v1",
                "descriptor_path": str((tmp_path / "missing-release.json").resolve()),
                "descriptor_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseSwitchError, match="does not exist"):
        resolve_active_release(
            wrong_pointer.resolve(),
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )

    staged.chmod(0o600)
    connection = sqlite3.connect(staged)
    connection.execute("UPDATE goals SET name = 'tampered staged' WHERE id = 10")
    connection.commit()
    connection.close()
    with pytest.raises(ReleaseSwitchError, match="mismatch"):
        resolve_active_release(
            pointer.resolve(),
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )


def test_release_descriptor_or_code_tampering_fails_closed(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    manifest = tmp_path / "staged.manifest.json"
    _manifest_for_staged(source, staged, manifest)
    code_root, entrypoint, config_path = _make_code_release(
        tmp_path, "v22-code", "trusted-code"
    )
    original_entrypoint = entrypoint.read_text(encoding="utf-8")
    descriptor = tmp_path / "release.json"
    create_release_descriptor(
        descriptor.resolve(),
        release_id="candidate",
        application_version="v2.2.0",
        git_commit=HEAD_COMMIT,
        code_root=code_root.resolve(),
        code_entrypoint=entrypoint.resolve(),
        config_path=config_path.resolve(),
        database_path=staged.resolve(),
        database_manifest_path=manifest.resolve(),
        expected_profile="v22",
    )
    pointer = tmp_path / "active.json"
    activate_release_pointer(
        descriptor.resolve(),
        pointer.resolve(),
        service_is_stopped=True,
        expected_git_commit=HEAD_COMMIT,
        expected_application_version="v2.2.0",
    )
    entrypoint.write_text("# tampered code marker\n", encoding="utf-8")
    with pytest.raises(ReleaseSwitchError, match="entrypoint hash"):
        resolve_active_release(
            pointer.resolve(),
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )

    entrypoint.write_text(original_entrypoint, encoding="utf-8")
    # The original bytes are not enough because this descriptor bound the
    # entire tree; mutate the paired configuration and confirm restart fails.
    config_path.write_text("APP_VERSION=tampered\n", encoding="utf-8")
    with pytest.raises(ReleaseSwitchError, match="code tree|config hash"):
        resolve_active_release(
            pointer.resolve(),
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )


def test_release_pointer_tampering_fails_closed(tmp_path):
    source = _create_legacy(tmp_path / "legacy.db")
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    manifest = tmp_path / "staged.manifest.json"
    _manifest_for_staged(source, staged, manifest)
    code_root, entrypoint, config_path = _make_code_release(
        tmp_path, "v22-code", "v22"
    )
    descriptor = tmp_path / "release.json"
    create_release_descriptor(
        descriptor.resolve(),
        release_id="candidate",
        application_version="v2.2.0",
        git_commit=HEAD_COMMIT,
        code_root=code_root.resolve(),
        code_entrypoint=entrypoint.resolve(),
        config_path=config_path.resolve(),
        database_path=staged.resolve(),
        database_manifest_path=manifest.resolve(),
        expected_profile="v22",
    )
    pointer = tmp_path / "active.json"
    activate_release_pointer(
        descriptor.resolve(),
        pointer.resolve(),
        service_is_stopped=True,
        expected_git_commit=HEAD_COMMIT,
        expected_application_version="v2.2.0",
    )
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    payload["descriptor_sha256"] = "0" * 64
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReleaseSwitchError, match="descriptor hash"):
        resolve_active_release(
            pointer.resolve(),
            expected_git_commit=HEAD_COMMIT,
            expected_application_version="v2.2.0",
            verify_immutable_database=True,
        )


def test_full_cutover_failure_and_rollback_restore_v214_pair(tmp_path):
    source, backup = _legacy_backup(tmp_path)
    source_hash = _digest(source)
    source_stat = source.stat()
    staged = tmp_path / "staged.db"
    _migrate(source, staged)
    staged_manifest = tmp_path / "staged.manifest.json"
    _manifest_for_staged(source, staged, staged_manifest)
    restored_legacy = tmp_path / "rollback-v214.db"
    restore_verified_backup(
        Path(backup["database"]),
        Path(backup["manifest"]),
        restored_legacy.resolve(),
        expected_profile="legacy_v214",
    )

    v214_root, v214_entrypoint, v214_config = _make_code_release(
        tmp_path, "v214-code", "v2.1.4"
    )
    v22_root, v22_entrypoint, v22_config = _make_code_release(
        tmp_path, "v22-code", "v2.2.0"
    )

    rollback_manifest = tmp_path / "rollback-v214.manifest.json"
    create_database_manifest(
        restored_legacy.resolve(),
        rollback_manifest.resolve(),
        expected_profile="legacy_v214",
        artifact_kind="rollback-restore",
        source_path=source.resolve(),
        source_profile="legacy_v214",
        git_commit=LEGACY_COMMIT,
        application_version="v2.1.4",
    )
    v214_descriptor = tmp_path / "release-v214.json"
    v22_descriptor = tmp_path / "release-v22.json"
    create_release_descriptor(
        v214_descriptor.resolve(),
        release_id="rollback-v214",
        application_version="v2.1.4",
        git_commit=LEGACY_COMMIT,
        code_root=v214_root.resolve(),
        code_entrypoint=v214_entrypoint.resolve(),
        config_path=v214_config.resolve(),
        database_path=restored_legacy.resolve(),
        database_manifest_path=rollback_manifest.resolve(),
        expected_profile="legacy_v214",
    )
    create_release_descriptor(
        v22_descriptor.resolve(),
        release_id="candidate-v22",
        application_version="v2.2.0",
        git_commit=HEAD_COMMIT,
        code_root=v22_root.resolve(),
        code_entrypoint=v22_entrypoint.resolve(),
        config_path=v22_config.resolve(),
        database_path=staged.resolve(),
        database_manifest_path=staged_manifest.resolve(),
        expected_profile="v22",
    )
    pointer = tmp_path / "active-release.json"
    selected_v22 = activate_release_pointer(
        v22_descriptor.resolve(),
        pointer.resolve(),
        service_is_stopped=True,
        expected_git_commit=HEAD_COMMIT,
        expected_application_version="v2.2.0",
    )
    assert selected_v22["release_id"] == "candidate-v22"

    # Simulated release failure: stop v2.2, select the restored v2.1.4 pair,
    # then validate the old runtime's exact schema contract before restart.
    selected_v214 = activate_release_pointer(
        v214_descriptor.resolve(),
        pointer.resolve(),
        service_is_stopped=True,
        expected_git_commit=LEGACY_COMMIT,
        expected_application_version="v2.1.4",
    )
    assert selected_v214["release_id"] == "rollback-v214"
    legacy_report = inspect_database(
        Path(selected_v214["database"]["path"]),
        expected_profile="legacy_v214",
    )
    assert legacy_report["sha256"] == backup["artifact"]["sha256"]
    assert legacy_report["row_counts"] == backup["artifact"]["row_counts"]
    assert legacy_report["integrity_check"] == "ok"
    assert legacy_report["foreign_key_check_rows"] == 0
    connection = sqlite3.connect(selected_v214["database"]["path"])
    connection.row_factory = sqlite3.Row
    try:
        assert connection.execute("SELECT name FROM goals WHERE id = 10").fetchone()[
            "name"
        ] == "保留主线 ID"
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "users" not in tables
        for table, expected_columns in LEGACY_V214_COLUMNS.items():
            columns = {
                row["name"]
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            assert columns == set(expected_columns)
            assert "user_id" not in columns
    finally:
        connection.close()
    assert _digest(source) == source_hash
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns


def test_wrong_schema_code_pair_is_rejected(tmp_path):
    source, backup = _legacy_backup(tmp_path)
    code_root, legacy_entrypoint, config_path = _make_code_release(
        tmp_path, "legacy-code", "old-code"
    )
    descriptor = tmp_path / "wrong-pair.json"
    with pytest.raises(ReleaseSwitchError, match="manifest|paired|v2.1.4"):
        create_release_descriptor(
            descriptor.resolve(),
            release_id="wrong-pair",
            application_version="v2.2.0",
            git_commit=HEAD_COMMIT,
            code_root=code_root.resolve(),
            code_entrypoint=legacy_entrypoint.resolve(),
            config_path=config_path.resolve(),
            database_path=Path(backup["database"]),
            database_manifest_path=Path(backup["manifest"]),
            expected_profile="legacy_v214",
        )
