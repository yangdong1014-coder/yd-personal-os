"""Verified SQLite artifacts for backup, migration staging, and restore.

The functions in this module never create or migrate an application schema.
They only inspect an explicitly selected database, create a consistent SQLite
backup snapshot, and bind an artifact to a machine-readable manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import database
from v22_migration import LEGACY_V214_COLUMNS


MANIFEST_FORMAT = "psy-sqlite-artifact/v1"
LEGACY_PROFILE = "legacy_v214"
V22_PROFILE = "v22"
SUPPORTED_PROFILES = (LEGACY_PROFILE, V22_PROFILE)

V22_USERS_COLUMNS = (
    "id",
    "username",
    "email",
    "password_hash",
    "role",
    "is_active",
    "must_change_password",
    "auth_version",
    "failed_login_count",
    "locked_until",
    "last_login_at",
    "created_at",
    "updated_at",
)

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


class DatabaseArtifactError(RuntimeError):
    """Raised when an artifact cannot be created or verified safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _require_absolute_path(path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise DatabaseArtifactError(f"{label} must be an absolute path")
    return candidate


def _require_existing_file(path, *, label: str) -> Path:
    candidate = _require_absolute_path(path, label=label)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DatabaseArtifactError(f"{label} does not exist or is inaccessible") from exc
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise DatabaseArtifactError(f"{label} must be a non-empty regular file")
    return resolved


def _require_existing_directory(path, *, label: str) -> Path:
    candidate = _require_absolute_path(path, label=label)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DatabaseArtifactError(f"{label} does not exist or is inaccessible") from exc
    if not resolved.is_dir():
        raise DatabaseArtifactError(f"{label} must be an existing directory")
    return resolved


def _readonly_connection(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            timeout=5,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except sqlite3.Error as exc:
        raise DatabaseArtifactError("database cannot be opened read-only") from exc


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        if not row["name"].startswith("sqlite_")
    }


def _table_columns(connection: sqlite3.Connection, table: str) -> dict:
    if table not in {*database.PERSONAL_DATA_TABLES, "users"}:
        raise DatabaseArtifactError(f"unexpected table identifier: {table}")
    return {
        row["name"]: row
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _sequence_value(connection: sqlite3.Connection, table: str):
    row = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
    ).fetchone()
    return int(row["seq"]) if row is not None else None


def _inspect_connection(
    connection: sqlite3.Connection,
    *,
    expected_profile: str,
) -> dict:
    if expected_profile not in SUPPORTED_PROFILES:
        raise DatabaseArtifactError(
            "expected_profile must be legacy_v214 or v22"
        )

    try:
        integrity_rows = [
            str(row[0])
            for row in connection.execute("PRAGMA integrity_check").fetchall()
        ]
        if integrity_rows != ["ok"]:
            raise DatabaseArtifactError(
                "database integrity_check failed: " + "; ".join(integrity_rows[:3])
            )
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_rows:
            raise DatabaseArtifactError(
                f"database foreign_key_check returned {len(foreign_key_rows)} row(s)"
            )

        table_names = _table_names(connection)
        expected_tables = set(database.PERSONAL_DATA_TABLES)
        expected_version = 0
        if expected_profile == V22_PROFILE:
            expected_tables.add("users")
            expected_version = database.SCHEMA_USER_VERSION
        if table_names != expected_tables:
            missing = sorted(expected_tables - table_names)
            extra = sorted(table_names - expected_tables)
            raise DatabaseArtifactError(
                f"database table set mismatch: missing={missing}, extra={extra}"
            )

        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if user_version != expected_version:
            raise DatabaseArtifactError(
                f"database schema version mismatch: expected={expected_version}, "
                f"actual={user_version}"
            )

        for table in database.PERSONAL_DATA_TABLES:
            columns = _table_columns(connection, table)
            expected_columns = set(LEGACY_V214_COLUMNS[table])
            if expected_profile == V22_PROFILE:
                expected_columns.add("user_id")
            if set(columns) != expected_columns or len(columns) != len(expected_columns):
                raise DatabaseArtifactError(f"{table} column set mismatch")
            if expected_profile == V22_PROFILE:
                user_column = columns["user_id"]
                if int(user_column["notnull"]) != 1:
                    raise DatabaseArtifactError(f"{table}.user_id must be NOT NULL")
                foreign_keys = connection.execute(
                    f'PRAGMA foreign_key_list("{table}")'
                ).fetchall()
                if not any(
                    row["from"] == "user_id" and row["table"] == "users"
                    for row in foreign_keys
                ):
                    raise DatabaseArtifactError(
                        f"{table}.user_id must reference users"
                    )

        users_total = None
        admins_total = None
        active_admins = None
        row_count_tables = list(database.PERSONAL_DATA_TABLES)
        sequence_tables = list(database.PERSONAL_DATA_TABLES)
        if expected_profile == V22_PROFILE:
            users_columns = _table_columns(connection, "users")
            if set(users_columns) != set(V22_USERS_COLUMNS) or len(
                users_columns
            ) != len(V22_USERS_COLUMNS):
                raise DatabaseArtifactError("users column set mismatch")
            admin_row = connection.execute(
                """
                SELECT COUNT(*) AS users_total,
                       SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) AS admins_total,
                       SUM(CASE WHEN role = 'admin' AND is_active = 1 THEN 1 ELSE 0 END)
                           AS active_admins
                FROM users
                """
            ).fetchone()
            users_total = int(admin_row["users_total"] or 0)
            admins_total = int(admin_row["admins_total"] or 0)
            active_admins = int(admin_row["active_admins"] or 0)
            if admins_total != 1 or active_admins != 1:
                raise DatabaseArtifactError(
                    "v22 database must contain exactly one active administrator"
                )
            row_count_tables.append("users")
            sequence_tables.append("users")

        row_counts = {
            table: int(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            for table in row_count_tables
        }
        sequences = {
            table: _sequence_value(connection, table) for table in sequence_tables
        }
        soft_orphans = _soft_orphan_counts(connection, expected_profile)
        if any(soft_orphans.values()):
            raise DatabaseArtifactError(
                "database soft relation verification failed: "
                + ", ".join(
                    f"{name}={count}"
                    for name, count in soft_orphans.items()
                    if count
                )
            )
        return {
            "schema_profile": expected_profile,
            "schema_version": user_version,
            "tables": sorted(table_names),
            "row_counts": row_counts,
            "sqlite_sequences": sequences,
            "soft_orphans": soft_orphans,
            "integrity_check": "ok",
            "foreign_key_check_rows": 0,
            "users_total": users_total,
            "admins_total": admins_total,
            "active_admins": active_admins,
        }
    except sqlite3.Error as exc:
        raise DatabaseArtifactError("database inspection failed") from exc


def _soft_orphan_counts(
    connection: sqlite3.Connection,
    expected_profile: str,
) -> dict:
    """Count every legacy/v2.2 polymorphic or JSON-carried soft relation."""
    owner_join = " AND parent.user_id = child.user_id" if expected_profile == V22_PROFILE else ""
    counts = {}
    polymorphic = {
        "feedback_items": {
            "opportunity": "opportunities",
            "experiment": "experiments",
            "project": "projects",
            "asset": "assets",
            "review": "reviews",
        },
        "deliberations": {
            "project": "projects",
            "opportunity": "opportunities",
        },
    }
    for child_table, targets in polymorphic.items():
        for related_type, parent_table in targets.items():
            key = f"{child_table}.{related_type}"
            counts[key] = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM "{child_table}" child
                    WHERE child.related_type = ? AND child.related_id IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM "{parent_table}" parent
                        WHERE parent.id = child.related_id{owner_join}
                      )
                    """,
                    (related_type,),
                ).fetchone()[0]
            )
        placeholders = ", ".join("?" for _ in targets)
        counts[f"{child_table}.unknown_type"] = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM "{child_table}"
                WHERE related_id IS NOT NULL
                  AND related_type NOT IN ({placeholders})
                """,
                tuple(targets),
            ).fetchone()[0]
        )

    counts["positioning_goal_action.target_goal_id"] = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM positioning_goal_action child
            WHERE child.target_goal_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM goals parent
                WHERE parent.id = child.target_goal_id
                """
            + (" AND parent.user_id = child.user_id" if expected_profile == V22_PROFILE else "")
            + ")"
        ).fetchone()[0]
    )

    asset_targets = {
        "review": "reviews",
        "feedback": "feedback_items",
        "experiment": "experiments",
        "opportunity": "opportunities",
    }
    for source_type, parent_table in asset_targets.items():
        counts[f"assets.source_id.{source_type}"] = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM assets child
                WHERE child.source_type = ? AND child.source_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM "{parent_table}" parent
                    WHERE parent.id = child.source_id{owner_join}
                  )
                """,
                (source_type,),
            ).fetchone()[0]
        )
    placeholders = ", ".join("?" for _ in asset_targets)
    counts["assets.source_id.unknown_type"] = int(
        connection.execute(
            f"""
            SELECT COUNT(*) FROM assets
            WHERE source_id IS NOT NULL AND source_type NOT IN ({placeholders})
            """,
            tuple(asset_targets),
        ).fetchone()[0]
    )

    payload_targets = {
        "goal_id": "goals",
        "project_id": "projects",
        "opportunity_id": "opportunities",
        "source_review_id": "reviews",
    }
    payload_orphans = 0
    payload_columns = "id, suggested_payload"
    if expected_profile == V22_PROFILE:
        payload_columns += ", user_id"
    for row in connection.execute(
        f"SELECT {payload_columns} FROM inbox_suggestions"
    ).fetchall():
        try:
            payload = json.loads(row["suggested_payload"] or "{}")
        except (TypeError, json.JSONDecodeError):
            payload_orphans += 1
            continue
        if not isinstance(payload, dict):
            payload_orphans += 1
            continue
        for field, parent_table in payload_targets.items():
            value = payload.get(field)
            if value in (None, ""):
                continue
            try:
                target_id = int(value)
            except (TypeError, ValueError):
                payload_orphans += 1
                continue
            sql = f'SELECT 1 FROM "{parent_table}" WHERE id = ?'
            params = [target_id]
            if expected_profile == V22_PROFILE:
                sql += " AND user_id = ?"
                params.append(row["user_id"])
            if connection.execute(sql, tuple(params)).fetchone() is None:
                payload_orphans += 1
    counts["inbox_suggestions.suggested_payload"] = payload_orphans
    return counts


def inspect_database(path, *, expected_profile: str) -> dict:
    """Read-only, fail-closed inspection of one explicit SQLite database."""
    database_path = _require_existing_file(path, label="database path")
    connection = _readonly_connection(database_path)
    try:
        report = _inspect_connection(
            connection,
            expected_profile=expected_profile,
        )
    finally:
        connection.close()
    report["path"] = str(database_path)
    report["size_bytes"] = database_path.stat().st_size
    report["sha256"] = sha256_file(database_path)
    return report


def _validate_release_metadata(git_commit: str, application_version: str) -> None:
    if not _COMMIT_RE.fullmatch(str(git_commit or "")):
        raise DatabaseArtifactError("git_commit must be a lowercase 40-character SHA")
    if not str(application_version or "").strip():
        raise DatabaseArtifactError("application_version is required")


def _artifact_payload(report: dict, *, filename: str, kind: str) -> dict:
    return {
        "filename": filename,
        "kind": kind,
        "size_bytes": report["size_bytes"],
        "sha256": report["sha256"],
        "schema_profile": report["schema_profile"],
        "schema_version": report["schema_version"],
        "tables": report["tables"],
        "row_counts": report["row_counts"],
        "sqlite_sequences": report["sqlite_sequences"],
        "soft_orphans": report["soft_orphans"],
        "integrity_check": report["integrity_check"],
        "foreign_key_check_rows": report["foreign_key_check_rows"],
        "users_total": report["users_total"],
        "admins_total": report["admins_total"],
        "active_admins": report["active_admins"],
    }


def _source_payload(report: dict) -> dict:
    return {
        "path": report["path"],
        "size_bytes": report["size_bytes"],
        "sha256": report["sha256"],
        "schema_profile": report["schema_profile"],
        "schema_version": report["schema_version"],
    }


def _make_manifest(
    artifact_report: dict,
    *,
    artifact_filename: str,
    artifact_kind: str,
    source_report: dict,
    git_commit: str,
    application_version: str,
    timestamp: str | None = None,
) -> dict:
    _validate_release_metadata(git_commit, application_version)
    timestamp = timestamp or datetime.now(timezone.utc).isoformat(timespec="microseconds")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatabaseArtifactError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DatabaseArtifactError("timestamp must include a timezone")
    return {
        "format": MANIFEST_FORMAT,
        "timestamp": timestamp,
        "application": {
            "git_commit": git_commit,
            "version": application_version,
        },
        "source": _source_payload(source_report),
        "artifact": _artifact_payload(
            artifact_report,
            filename=artifact_filename,
            kind=artifact_kind,
        ),
    }


def _checksum_path(manifest_path: Path) -> Path:
    return Path(str(manifest_path) + ".sha256")


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise DatabaseArtifactError(f"refusing to overwrite existing target: {path}") from exc
    except OSError as exc:
        raise DatabaseArtifactError(f"failed writing artifact metadata: {path}") from exc


def _publish_no_overwrite(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise DatabaseArtifactError(
            f"refusing to overwrite existing target: {destination}"
        ) from exc
    except OSError as exc:
        raise DatabaseArtifactError(f"failed publishing target: {destination}") from exc


def _fsync_directory(path: Path) -> None:
    """Persist directory entries on the Linux production filesystem."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise DatabaseArtifactError(f"failed syncing artifact directory: {path}") from exc


def _set_read_only(path: Path) -> None:
    try:
        path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    except OSError as exc:
        raise DatabaseArtifactError(f"failed to make artifact read-only: {path}") from exc


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.chmod(stat.S_IREAD | stat.S_IWRITE)
            path.unlink()
    except OSError:
        pass


def _read_manifest(manifest_path: Path) -> tuple[dict, bytes]:
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatabaseArtifactError("manifest cannot be read as UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise DatabaseArtifactError("manifest root must be an object")
    return manifest, raw


def _require_exact_keys(value: dict, expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        raise DatabaseArtifactError(
            f"{label} fields mismatch: expected={sorted(expected)}, actual={sorted(value)}"
        )


def _validate_manifest_structure(manifest: dict) -> None:
    _require_exact_keys(
        manifest,
        {"format", "timestamp", "application", "source", "artifact"},
        label="manifest",
    )
    if manifest["format"] != MANIFEST_FORMAT:
        raise DatabaseArtifactError("unsupported manifest format")
    _require_exact_keys(
        manifest["application"], {"git_commit", "version"}, label="application"
    )
    _validate_release_metadata(
        manifest["application"]["git_commit"], manifest["application"]["version"]
    )
    _require_exact_keys(
        manifest["source"],
        {"path", "size_bytes", "sha256", "schema_profile", "schema_version"},
        label="source",
    )
    _require_exact_keys(
        manifest["artifact"],
        {
            "filename",
            "kind",
            "size_bytes",
            "sha256",
            "schema_profile",
            "schema_version",
            "tables",
            "row_counts",
            "sqlite_sequences",
            "soft_orphans",
            "integrity_check",
            "foreign_key_check_rows",
            "users_total",
            "admins_total",
            "active_admins",
        },
        label="artifact",
    )
    profile = manifest["artifact"]["schema_profile"]
    if profile not in SUPPORTED_PROFILES:
        raise DatabaseArtifactError("manifest schema_profile is unsupported")
    if manifest["source"]["schema_profile"] not in SUPPORTED_PROFILES:
        raise DatabaseArtifactError("manifest source schema_profile is unsupported")
    try:
        parsed = datetime.fromisoformat(
            str(manifest["timestamp"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise DatabaseArtifactError("manifest timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise DatabaseArtifactError("manifest timestamp lacks timezone")


def _verify_manifest_checksum(manifest_path: Path, raw: bytes) -> None:
    checksum_path = _require_existing_file(
        _checksum_path(manifest_path), label="manifest checksum path"
    )
    try:
        expected = checksum_path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise DatabaseArtifactError("manifest checksum cannot be read") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise DatabaseArtifactError("manifest checksum format is invalid")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise DatabaseArtifactError("manifest checksum mismatch")


def _verify_report_against_manifest(report: dict, artifact: dict) -> None:
    expected = {
        "size_bytes": report["size_bytes"],
        "sha256": report["sha256"],
        "schema_profile": report["schema_profile"],
        "schema_version": report["schema_version"],
        "tables": report["tables"],
        "row_counts": report["row_counts"],
        "sqlite_sequences": report["sqlite_sequences"],
        "soft_orphans": report["soft_orphans"],
        "integrity_check": report["integrity_check"],
        "foreign_key_check_rows": report["foreign_key_check_rows"],
        "users_total": report["users_total"],
        "admins_total": report["admins_total"],
        "active_admins": report["active_admins"],
    }
    for key, actual in expected.items():
        if artifact.get(key) != actual:
            raise DatabaseArtifactError(f"artifact manifest mismatch: {key}")


def verify_database_artifact(
    database_path,
    manifest_path,
    *,
    expected_profile: str | None = None,
    require_filename: bool = True,
) -> dict:
    """Verify checksum, size, schema, counts, integrity, and foreign keys."""
    artifact_path = _require_existing_file(database_path, label="artifact database path")
    manifest_report = read_verified_manifest(manifest_path)
    manifest_file = Path(manifest_report["manifest"])
    manifest = manifest_report["payload"]
    artifact = manifest["artifact"]
    if require_filename and artifact["filename"] != artifact_path.name:
        raise DatabaseArtifactError("manifest filename does not match artifact")
    profile = expected_profile or artifact["schema_profile"]
    if profile != artifact["schema_profile"]:
        raise DatabaseArtifactError("manifest schema profile differs from expectation")
    report = inspect_database(artifact_path, expected_profile=profile)
    _verify_report_against_manifest(report, artifact)
    return {
        "ok": True,
        "database": str(artifact_path),
        "manifest": str(manifest_file),
        "manifest_sha256": manifest_report["manifest_sha256"],
        "application": manifest["application"],
        "source": manifest["source"],
        "artifact": artifact,
    }


def read_verified_manifest(manifest_path) -> dict:
    """Verify a manifest's checksum and strict metadata structure."""
    manifest_file = _require_existing_file(manifest_path, label="manifest path")
    manifest, raw = _read_manifest(manifest_file)
    _verify_manifest_checksum(manifest_file, raw)
    _validate_manifest_structure(manifest)
    return {
        "ok": True,
        "manifest": str(manifest_file),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "payload": manifest,
    }


def _write_manifest_pair_no_overwrite(manifest_path: Path, manifest: dict) -> None:
    checksum_path = _checksum_path(manifest_path)
    if manifest_path.exists() or checksum_path.exists():
        raise DatabaseArtifactError("manifest target or checksum already exists")
    raw = _canonical_json_bytes(manifest)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", suffix=".tmp", dir=manifest_path.parent
    )
    os.close(descriptor)
    temporary_manifest = Path(temporary_name)
    temporary_checksum = Path(str(temporary_manifest) + ".sha256")
    published = []
    try:
        with temporary_manifest.open("wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _write_exclusive(
            temporary_checksum,
            (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii"),
        )
        _publish_no_overwrite(temporary_manifest, manifest_path)
        published.append(manifest_path)
        _publish_no_overwrite(temporary_checksum, checksum_path)
        published.append(checksum_path)
        _fsync_directory(manifest_path.parent)
    except Exception:
        for path in reversed(published):
            _safe_unlink(path)
        raise
    finally:
        _safe_unlink(temporary_manifest)
        _safe_unlink(temporary_checksum)


def create_database_manifest(
    database_path,
    manifest_path,
    *,
    expected_profile: str,
    artifact_kind: str,
    source_path,
    source_profile: str,
    git_commit: str,
    application_version: str,
    timestamp: str | None = None,
) -> dict:
    """Bind an existing staged/restored database to an exclusive manifest."""
    artifact_path = _require_existing_file(database_path, label="artifact database path")
    manifest_file = _require_absolute_path(manifest_path, label="manifest path")
    parent = _require_existing_directory(manifest_file.parent, label="manifest directory")
    manifest_file = parent / manifest_file.name
    if manifest_file.exists() or _checksum_path(manifest_file).exists():
        raise DatabaseArtifactError("manifest target or checksum already exists")
    artifact_report = inspect_database(artifact_path, expected_profile=expected_profile)
    source_report = inspect_database(source_path, expected_profile=source_profile)
    manifest = _make_manifest(
        artifact_report,
        artifact_filename=artifact_path.name,
        artifact_kind=artifact_kind,
        source_report=source_report,
        git_commit=git_commit,
        application_version=application_version,
        timestamp=timestamp,
    )
    _write_manifest_pair_no_overwrite(manifest_file, manifest)
    try:
        report = verify_database_artifact(
            artifact_path,
            manifest_file,
            expected_profile=expected_profile,
        )
        _set_read_only(manifest_file)
        _set_read_only(_checksum_path(manifest_file))
        return report
    except Exception:
        _safe_unlink(manifest_file)
        _safe_unlink(_checksum_path(manifest_file))
        raise


def create_verified_backup(
    source_path,
    backup_directory,
    *,
    expected_profile: str,
    git_commit: str,
    application_version: str,
    timestamp: str | None = None,
    failure_hook=None,
) -> dict:
    """Create and verify a consistent SQLite backup without overwriting history."""
    source_path = _require_existing_file(source_path, label="source database path")
    backup_directory = _require_existing_directory(
        backup_directory, label="backup directory"
    )
    _validate_release_metadata(git_commit, application_version)
    now = timestamp or datetime.now(timezone.utc).isoformat(timespec="microseconds")
    try:
        parsed = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatabaseArtifactError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DatabaseArtifactError("timestamp must include a timezone")
    stamp = parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_name = f"{source_path.stem}-{expected_profile}-{stamp}.sqlite3"
    backup_path = backup_directory / backup_name
    manifest_path = backup_directory / f"{backup_name}.manifest.json"
    checksum_path = _checksum_path(manifest_path)
    for candidate in (backup_path, manifest_path, checksum_path):
        if candidate.exists():
            raise DatabaseArtifactError(
                f"refusing to overwrite existing target: {candidate}"
            )

    source_before_stat = source_path.stat()
    source_before_hash = sha256_file(source_path)
    source_connection = _readonly_connection(source_path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{backup_name}.", suffix=".tmp", dir=backup_directory
    )
    os.close(descriptor)
    temporary_database = Path(temporary_name)
    temporary_manifest = Path(str(temporary_database) + ".manifest.tmp")
    temporary_checksum = Path(str(temporary_manifest) + ".sha256")
    published = []
    try:
        source_report = _inspect_connection(
            source_connection,
            expected_profile=expected_profile,
        )
        data_version_before = int(
            source_connection.execute("PRAGMA data_version").fetchone()[0]
        )
        destination_connection = sqlite3.connect(str(temporary_database))
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
        except sqlite3.Error as exc:
            raise DatabaseArtifactError("SQLite backup API failed") from exc
        finally:
            destination_connection.close()
        data_version_after = int(
            source_connection.execute("PRAGMA data_version").fetchone()[0]
        )
        if data_version_before != data_version_after:
            raise DatabaseArtifactError("source database changed during backup")

        if failure_hook is not None:
            failure_hook("after_sqlite_backup")

        source_after_stat = source_path.stat()
        source_after_hash = sha256_file(source_path)
        if (
            source_before_stat.st_size != source_after_stat.st_size
            or source_before_stat.st_mtime_ns != source_after_stat.st_mtime_ns
            or source_before_hash != source_after_hash
        ):
            raise DatabaseArtifactError("source database changed during backup")

        source_report.update(
            {
                "path": str(source_path),
                "size_bytes": source_before_stat.st_size,
                "sha256": source_before_hash,
            }
        )
        artifact_report = inspect_database(
            temporary_database.resolve(), expected_profile=expected_profile
        )
        for key in (
            "schema_profile",
            "schema_version",
            "tables",
            "row_counts",
            "sqlite_sequences",
            "soft_orphans",
            "integrity_check",
            "foreign_key_check_rows",
            "users_total",
            "admins_total",
            "active_admins",
        ):
            if artifact_report[key] != source_report[key]:
                raise DatabaseArtifactError(f"backup snapshot differs from source: {key}")

        manifest = _make_manifest(
            artifact_report,
            artifact_filename=backup_name,
            artifact_kind="sqlite-backup",
            source_report=source_report,
            git_commit=git_commit,
            application_version=application_version,
            timestamp=now,
        )
        raw_manifest = _canonical_json_bytes(manifest)
        with temporary_manifest.open("wb") as stream:
            stream.write(raw_manifest)
            stream.flush()
            os.fsync(stream.fileno())
        _write_exclusive(
            temporary_checksum,
            (hashlib.sha256(raw_manifest).hexdigest() + "\n").encode("ascii"),
        )

        if failure_hook is not None:
            failure_hook("before_publish")

        _publish_no_overwrite(temporary_database, backup_path)
        published.append(backup_path)
        _publish_no_overwrite(temporary_manifest, manifest_path)
        published.append(manifest_path)
        _publish_no_overwrite(temporary_checksum, checksum_path)
        published.append(checksum_path)
        _fsync_directory(backup_directory)

        report = verify_database_artifact(
            backup_path,
            manifest_path,
            expected_profile=expected_profile,
        )
        for path in (backup_path, manifest_path, checksum_path):
            _set_read_only(path)
        report["source_unchanged"] = True
        return report
    except Exception:
        for path in reversed(published):
            _safe_unlink(path)
        raise
    finally:
        source_connection.close()
        _safe_unlink(temporary_database)
        _safe_unlink(temporary_manifest)
        _safe_unlink(temporary_checksum)


def restore_verified_backup(
    backup_path,
    manifest_path,
    restore_path,
    *,
    expected_profile: str,
) -> dict:
    """Restore an already verified backup to a new, never-overwritten path."""
    backup_path = _require_existing_file(backup_path, label="backup database path")
    manifest_path = _require_existing_file(manifest_path, label="manifest path")
    restore_path = _require_absolute_path(restore_path, label="restore path")
    restore_parent = _require_existing_directory(
        restore_path.parent, label="restore directory"
    )
    restore_path = restore_parent / restore_path.name
    if restore_path.exists():
        raise DatabaseArtifactError("restore target already exists")

    verified = verify_database_artifact(
        backup_path,
        manifest_path,
        expected_profile=expected_profile,
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{restore_path.name}.", suffix=".tmp", dir=restore_parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    linked = False
    try:
        with backup_path.open("rb") as source, temporary_path.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        restored_report = inspect_database(
            temporary_path.resolve(), expected_profile=expected_profile
        )
        _verify_report_against_manifest(restored_report, verified["artifact"])
        _publish_no_overwrite(temporary_path, restore_path)
        linked = True
        _fsync_directory(restore_parent)
        final_report = inspect_database(restore_path, expected_profile=expected_profile)
        _verify_report_against_manifest(final_report, verified["artifact"])
        return {
            "ok": True,
            "restore": str(restore_path),
            "sha256": final_report["sha256"],
            "row_counts": final_report["row_counts"],
            "integrity_check": final_report["integrity_check"],
            "foreign_key_check_rows": final_report["foreign_key_check_rows"],
        }
    except Exception:
        if linked:
            _safe_unlink(restore_path)
        raise
    finally:
        _safe_unlink(temporary_path)
