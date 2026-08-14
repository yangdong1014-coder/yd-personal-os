"""Atomic release-pointer switching for a stopped PSY service.

Code and database files live at versioned paths. The only mutable selector is
one small JSON pointer replaced with ``os.replace``. A service launcher must
resolve this pointer before starting the selected code. This prevents a
half-written selector and gives rollback the same atomic operation as rollout.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from database_artifacts import (
    DatabaseArtifactError,
    SUPPORTED_PROFILES,
    _fsync_directory,
    inspect_database,
    read_verified_manifest,
    sha256_file,
    verify_database_artifact,
)


DESCRIPTOR_FORMAT = "psy-release-descriptor/v1"
POINTER_FORMAT = "psy-active-release/v1"
_RELEASE_DESCRIPTOR_MODE = 0o644
_ACTIVE_POINTER_MODE = 0o644
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


class ReleaseSwitchError(RuntimeError):
    """Raised when a release cannot be paired, selected, or resolved safely."""


def _validate_schema_pair(application_version: str, schema_profile: str) -> None:
    if schema_profile == "legacy_v214" and application_version != "v2.1.4":
        raise ReleaseSwitchError("legacy_v214 must be paired with v2.1.4 code")
    if schema_profile == "v22" and not application_version.startswith("v2.2"):
        raise ReleaseSwitchError("v22 must be paired with v2.2 code")


def _canonical_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _absolute(path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ReleaseSwitchError(f"{label} must be an absolute path")
    return candidate


def _existing_file(path, *, label: str) -> Path:
    candidate = _absolute(path, label=label)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ReleaseSwitchError(f"{label} does not exist or is inaccessible") from exc
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ReleaseSwitchError(f"{label} must be a non-empty regular file")
    return resolved


def _existing_directory(path, *, label: str) -> Path:
    candidate = _absolute(path, label=label)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ReleaseSwitchError(f"{label} does not exist or is inaccessible") from exc
    if not resolved.is_dir():
        raise ReleaseSwitchError(f"{label} must be an existing directory")
    return resolved


def _validate_application(application: dict) -> None:
    if set(application) != {
        "version",
        "git_commit",
        "code_root",
        "code_tree_sha256",
        "entrypoint",
        "entrypoint_sha256",
        "config_path",
        "config_sha256",
    }:
        raise ReleaseSwitchError("release application fields are invalid")
    if not str(application["version"] or "").strip():
        raise ReleaseSwitchError("release application version is required")
    if not _COMMIT_RE.fullmatch(str(application["git_commit"] or "")):
        raise ReleaseSwitchError("release git commit must be a lowercase 40-character SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", str(application["entrypoint_sha256"] or "")):
        raise ReleaseSwitchError("code entrypoint hash format is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(application["code_tree_sha256"] or "")):
        raise ReleaseSwitchError("code tree hash format is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(application["config_sha256"] or "")):
        raise ReleaseSwitchError("release config hash format is invalid")
    code_root = _existing_directory(application["code_root"], label="code root")
    if str(code_root) != application["code_root"]:
        raise ReleaseSwitchError("code root must be canonical")
    entrypoint = _existing_file(application["entrypoint"], label="code entrypoint")
    if str(entrypoint) != application["entrypoint"]:
        raise ReleaseSwitchError("code entrypoint must be canonical")
    try:
        entrypoint.relative_to(code_root)
    except ValueError as exc:
        raise ReleaseSwitchError("code entrypoint must be inside code root") from exc
    if sha256_file(entrypoint) != application.get("entrypoint_sha256", ""):
        raise ReleaseSwitchError("code entrypoint hash mismatch")
    if _code_tree_sha256(code_root) != application["code_tree_sha256"]:
        raise ReleaseSwitchError("code tree hash mismatch")
    config_path = _existing_file(application["config_path"], label="release config")
    if str(config_path) != application["config_path"]:
        raise ReleaseSwitchError("release config path must be canonical")
    if sha256_file(config_path) != application["config_sha256"]:
        raise ReleaseSwitchError("release config hash mismatch")


def _code_tree_sha256(code_root: Path) -> str:
    """Hash every release file except known generated/runtime directories."""
    excluded_directories = {
        ".git",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "backups",
        "data",
        "venv",
    }
    digest = hashlib.sha256()
    files = []
    try:
        for candidate in code_root.rglob("*"):
            relative = candidate.relative_to(code_root)
            if any(part in excluded_directories for part in relative.parts):
                continue
            if candidate.is_symlink():
                raise ReleaseSwitchError(
                    f"code root contains unsupported symlink: {relative.as_posix()}"
                )
            if candidate.is_file():
                files.append((relative, candidate))
    except OSError as exc:
        raise ReleaseSwitchError("code tree cannot be enumerated") from exc
    if not files:
        raise ReleaseSwitchError("code root contains no release files")
    for relative, candidate in sorted(files, key=lambda item: item[0].as_posix()):
        relative_bytes = relative.as_posix().encode("utf-8")
        digest.update(len(relative_bytes).to_bytes(8, "big"))
        digest.update(relative_bytes)
        digest.update(bytes.fromhex(sha256_file(candidate)))
    return digest.hexdigest()


def _read_json(path: Path, *, label: str) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseSwitchError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ReleaseSwitchError(f"{label} must be a JSON object")
    return payload, raw


def _write_exclusive(path: Path, content: bytes) -> None:
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(content)
            stream.flush()
            if os.name != "nt":
                os.fchmod(stream.fileno(), _RELEASE_DESCRIPTOR_MODE)
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ReleaseSwitchError(f"refusing to overwrite existing file: {path}") from exc
    except OSError as exc:
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ReleaseSwitchError(f"failed writing file: {path}") from exc


def _set_active_pointer_mode(file_descriptor: int) -> None:
    """Make a root-created pointer readable, but never writable, by the service."""
    if os.name != "nt":
        os.fchmod(file_descriptor, _ACTIVE_POINTER_MODE)


def create_release_descriptor(
    descriptor_path,
    *,
    release_id: str,
    application_version: str,
    git_commit: str,
    code_root,
    code_entrypoint,
    config_path,
    database_path,
    database_manifest_path,
    expected_profile: str,
) -> dict:
    """Create one immutable description of a code/database pair."""
    if not str(release_id or "").strip() or len(str(release_id)) > 128:
        raise ReleaseSwitchError("release_id is required and must be at most 128 chars")
    if expected_profile not in SUPPORTED_PROFILES:
        raise ReleaseSwitchError("release schema profile is unsupported")
    descriptor_path = _absolute(descriptor_path, label="release descriptor path")
    parent = _existing_directory(descriptor_path.parent, label="descriptor directory")
    descriptor_path = parent / descriptor_path.name
    if descriptor_path.exists():
        raise ReleaseSwitchError("release descriptor already exists")
    code_root = _existing_directory(code_root, label="code root")
    entrypoint = _existing_file(code_entrypoint, label="code entrypoint")
    try:
        entrypoint.relative_to(code_root)
    except ValueError as exc:
        raise ReleaseSwitchError("code entrypoint must be inside code root") from exc
    config_path = _existing_file(config_path, label="release config")
    database_path = _existing_file(database_path, label="release database")
    manifest_path = _existing_file(
        database_manifest_path, label="release database manifest"
    )
    try:
        verification = verify_database_artifact(
            database_path,
            manifest_path,
            expected_profile=expected_profile,
        )
    except DatabaseArtifactError as exc:
        raise ReleaseSwitchError(str(exc)) from exc
    manifest_application = verification["application"]
    if (
        manifest_application["git_commit"] != git_commit
        or manifest_application["version"] != application_version
    ):
        raise ReleaseSwitchError(
            "release code metadata does not match the database manifest"
        )
    _validate_schema_pair(application_version, expected_profile)
    descriptor = {
        "format": DESCRIPTOR_FORMAT,
        "release_id": str(release_id),
        "application": {
            "version": str(application_version),
            "git_commit": str(git_commit),
            "code_root": str(code_root),
            "code_tree_sha256": _code_tree_sha256(code_root),
            "entrypoint": str(entrypoint),
            "entrypoint_sha256": sha256_file(entrypoint),
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path),
        },
        "database": {
            "path": str(database_path),
            "manifest_path": str(manifest_path),
            "manifest_sha256": verification["manifest_sha256"],
            "sha256": verification["artifact"]["sha256"],
            "schema_profile": expected_profile,
            "schema_version": verification["artifact"]["schema_version"],
        },
    }
    _validate_application(descriptor["application"])
    _write_exclusive(descriptor_path, _canonical_bytes(descriptor))
    try:
        _fsync_directory(parent)
    except DatabaseArtifactError as exc:
        try:
            descriptor_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ReleaseSwitchError(str(exc)) from exc
    return verify_release_descriptor(
        descriptor_path,
        expected_git_commit=git_commit,
        expected_application_version=application_version,
        verify_immutable_database=True,
    )


def verify_release_descriptor(
    descriptor_path,
    *,
    expected_git_commit: str | None = None,
    expected_application_version: str | None = None,
    verify_immutable_database: bool,
) -> dict:
    """Verify pairing metadata and optionally the pre-activation DB hash."""
    descriptor_path = _existing_file(descriptor_path, label="release descriptor")
    descriptor, raw = _read_json(descriptor_path, label="release descriptor")
    if set(descriptor) != {"format", "release_id", "application", "database"}:
        raise ReleaseSwitchError("release descriptor fields are invalid")
    if descriptor["format"] != DESCRIPTOR_FORMAT:
        raise ReleaseSwitchError("release descriptor format is unsupported")
    if not str(descriptor["release_id"] or "").strip():
        raise ReleaseSwitchError("release descriptor release_id is empty")
    application = descriptor["application"]
    database_info = descriptor["database"]
    _validate_application(application)
    if expected_git_commit is not None and application["git_commit"] != expected_git_commit:
        raise ReleaseSwitchError("release code commit does not match running code")
    if (
        expected_application_version is not None
        and application["version"] != expected_application_version
    ):
        raise ReleaseSwitchError("release application version mismatch")
    if set(database_info) != {
        "path",
        "manifest_path",
        "manifest_sha256",
        "sha256",
        "schema_profile",
        "schema_version",
    }:
        raise ReleaseSwitchError("release database fields are invalid")
    if database_info["schema_profile"] not in SUPPORTED_PROFILES:
        raise ReleaseSwitchError("release database profile is unsupported")
    if not re.fullmatch(r"[0-9a-f]{64}", str(database_info["manifest_sha256"] or "")):
        raise ReleaseSwitchError("release manifest hash format is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(database_info["sha256"] or "")):
        raise ReleaseSwitchError("release database hash format is invalid")
    _validate_schema_pair(
        application["version"], database_info["schema_profile"]
    )
    database_path = _existing_file(database_info["path"], label="release database")
    manifest_path = _existing_file(
        database_info["manifest_path"], label="release database manifest"
    )
    if str(database_path) != database_info["path"]:
        raise ReleaseSwitchError("release database path must be canonical")
    if str(manifest_path) != database_info["manifest_path"]:
        raise ReleaseSwitchError("release manifest path must be canonical")
    if sha256_file(manifest_path) != database_info["manifest_sha256"]:
        raise ReleaseSwitchError("release manifest hash mismatch")
    try:
        manifest = read_verified_manifest(manifest_path)["payload"]
        if manifest["application"] != {
            "git_commit": application["git_commit"],
            "version": application["version"],
        }:
            raise ReleaseSwitchError(
                "release code metadata does not match the database manifest"
            )
        if verify_immutable_database:
            artifact = verify_database_artifact(
                database_path,
                manifest_path,
                expected_profile=database_info["schema_profile"],
            )
            if artifact["artifact"]["sha256"] != database_info["sha256"]:
                raise ReleaseSwitchError("release database hash mismatch")
        else:
            current = inspect_database(
                database_path,
                expected_profile=database_info["schema_profile"],
            )
            invariant_fields = (
                "schema_version",
                "tables",
                "soft_orphans",
                "integrity_check",
                "foreign_key_check_rows",
                "admins_total",
                "active_admins",
            )
            for field in invariant_fields:
                if current[field] != manifest["artifact"][field]:
                    raise ReleaseSwitchError(
                        f"runtime database invariant mismatch: {field}"
                    )
    except DatabaseArtifactError as exc:
        raise ReleaseSwitchError(str(exc)) from exc
    return {
        "ok": True,
        "descriptor": str(descriptor_path),
        "descriptor_sha256": hashlib.sha256(raw).hexdigest(),
        "release_id": descriptor["release_id"],
        "application": application,
        "database": database_info,
    }


def activate_release_pointer(
    descriptor_path,
    active_pointer_path,
    *,
    service_is_stopped: bool,
    expected_git_commit: str,
    expected_application_version: str,
    failure_hook=None,
) -> dict:
    """Atomically select a fully verified release while the service is stopped."""
    if service_is_stopped is not True:
        raise ReleaseSwitchError("service must be confirmed stopped before switching")
    descriptor = verify_release_descriptor(
        descriptor_path,
        expected_git_commit=expected_git_commit,
        expected_application_version=expected_application_version,
        verify_immutable_database=True,
    )
    pointer_path = _absolute(active_pointer_path, label="active release pointer")
    parent = _existing_directory(pointer_path.parent, label="pointer directory")
    pointer_path = parent / pointer_path.name
    pointer = {
        "format": POINTER_FORMAT,
        "descriptor_path": descriptor["descriptor"],
        "descriptor_sha256": descriptor["descriptor_sha256"],
    }
    descriptor_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{pointer_path.name}.", suffix=".tmp", dir=parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor_fd, "wb") as stream:
            descriptor_fd = None
            stream.write(_canonical_bytes(pointer))
            stream.flush()
            _set_active_pointer_mode(stream.fileno())
            os.fsync(stream.fileno())
        if failure_hook is not None:
            failure_hook("before_atomic_replace")
        os.replace(temporary_path, pointer_path)
        try:
            _fsync_directory(parent)
        except DatabaseArtifactError as exc:
            raise ReleaseSwitchError(str(exc)) from exc
        return resolve_active_release(
            pointer_path,
            expected_git_commit=expected_git_commit,
            expected_application_version=expected_application_version,
            verify_immutable_database=True,
        )
    except OSError as exc:
        raise ReleaseSwitchError("atomic release pointer replacement failed") from exc
    finally:
        if descriptor_fd is not None:
            try:
                os.close(descriptor_fd)
            except OSError:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def resolve_active_release(
    active_pointer_path,
    *,
    expected_git_commit: str,
    expected_application_version: str,
    verify_immutable_database: bool,
) -> dict:
    """Resolve one complete pointer and prove it selects matching code and DB."""
    pointer_path = _existing_file(active_pointer_path, label="active release pointer")
    pointer, _raw = _read_json(pointer_path, label="active release pointer")
    if set(pointer) != {"format", "descriptor_path", "descriptor_sha256"}:
        raise ReleaseSwitchError("active release pointer fields are invalid")
    if pointer["format"] != POINTER_FORMAT:
        raise ReleaseSwitchError("active release pointer format is unsupported")
    if not re.fullmatch(r"[0-9a-f]{64}", str(pointer["descriptor_sha256"] or "")):
        raise ReleaseSwitchError("active release descriptor hash format is invalid")
    descriptor_path = _existing_file(
        pointer["descriptor_path"], label="selected release descriptor"
    )
    if str(descriptor_path) != pointer["descriptor_path"]:
        raise ReleaseSwitchError(
            "selected release descriptor path must be canonical"
        )
    if sha256_file(descriptor_path) != pointer["descriptor_sha256"]:
        raise ReleaseSwitchError("selected release descriptor hash mismatch")
    return verify_release_descriptor(
        descriptor_path,
        expected_git_commit=expected_git_commit,
        expected_application_version=expected_application_version,
        verify_immutable_database=verify_immutable_database,
    )
