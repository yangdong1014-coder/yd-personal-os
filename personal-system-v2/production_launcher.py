"""Resolve one active release and launch its fixed Gunicorn entry point.

This is the stable, systemd-facing control-plane entry point.  It never guesses
an application or database path and it never invokes a shell.  The active
release descriptor selects the code, runtime configuration, and database as one
verified unit; the command line only supplies containment roots and approved
release metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from release_switch import ReleaseSwitchError, resolve_active_release
from shadow_deployment import ShadowDeploymentError, validate_shadow_identity


class ProductionLaunchError(RuntimeError):
    """Raised before Gunicorn starts when the selected release is unsafe."""


REQUIRED_RUNTIME_KEYS = frozenset(
    {
        "PERSONAL_OS_ENV",
        "PERSONAL_OS_REMOTE",
        "PERSONAL_OS_BIND_HOST",
        "PERSONAL_OS_TRUSTED_HOSTS",
        "PERSONAL_OS_TRUSTED_PROXY",
        "PERSONAL_OS_PROXY_TOKEN",
        "SECRET_KEY",
    }
)
OPTIONAL_RUNTIME_KEYS = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_TIMEOUT",
    }
)
RUNTIME_CONFIG_KEYS = REQUIRED_RUNTIME_KEYS | OPTIONAL_RUNTIME_KEYS
_SAFE_PARENT_ENV_KEYS = frozenset(
    {
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TZ",
    }
)
_FORBIDDEN_PARENT_ENV_KEYS = frozenset(
    {
        "FLASK_DEBUG",
        "FLASK_ENV",
        "GUNICORN_CMD_ARGS",
        "PYTHONBREAKPOINT",
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PSY_GUNICORN_BIND_PORT",
    }
)
_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_PORT_RE = re.compile(r"[0-9]+\Z")
_MAX_CONFIG_BYTES = 64 * 1024
DEFAULT_BIND_PORT = 5000
MIN_UNPRIVILEGED_PORT = 1024
MAX_TCP_PORT = 65535
GUNICORN_BIND_PORT_ENV = "PSY_GUNICORN_BIND_PORT"


@dataclass(frozen=True)
class LaunchPlan:
    active_pointer: Path
    descriptor: Path
    descriptor_sha256: str
    release_id: str
    application_version: str
    git_commit: str
    code_root: Path
    entrypoint: Path
    gunicorn_config: Path
    config_path: Path
    database_path: Path
    database_manifest_path: Path
    separated_database_artifacts: bool
    shadow_instance: str | None
    bind_port: int
    runtime_environment: dict[str, str]
    command: tuple[str, ...]
    python_executable: Path | None = None
    venv_path: Path | None = None


def validate_bind_port(value) -> int:
    """Return one strict, non-privileged TCP port or fail closed."""
    if isinstance(value, bool):
        raise ProductionLaunchError("bind port must be a decimal integer")
    raw = str(value)
    if len(raw) > 5 or not _PORT_RE.fullmatch(raw):
        raise ProductionLaunchError("bind port must be a decimal integer")
    port = int(raw, 10)
    if not MIN_UNPRIVILEGED_PORT <= port <= MAX_TCP_PORT:
        raise ProductionLaunchError(
            f"bind port must be between {MIN_UNPRIVILEGED_PORT} and {MAX_TCP_PORT}"
        )
    return port


def _canonical_existing(path, *, label: str, directory: bool) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ProductionLaunchError(f"{label} must be an absolute path")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProductionLaunchError(f"{label} does not exist or is inaccessible") from exc
    if candidate != resolved:
        raise ProductionLaunchError(f"{label} must be canonical and not a symlink")
    if directory and not resolved.is_dir():
        raise ProductionLaunchError(f"{label} must be a directory")
    if not directory and (not resolved.is_file() or resolved.stat().st_size <= 0):
        raise ProductionLaunchError(f"{label} must be a non-empty regular file")
    return resolved


def _require_within(path: Path, root: Path, *, label: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ProductionLaunchError(f"{label} escapes its approved root") from exc
    if not relative.parts:
        raise ProductionLaunchError(f"{label} cannot equal its approved root")


def _strip_optional_quotes(value: str, *, line_number: int) -> str:
    if not value:
        return value
    if value[0] in {'"', "'"}:
        if len(value) < 2 or value[-1] != value[0]:
            raise ProductionLaunchError(
                f"runtime config line {line_number} has unmatched quotes"
            )
        value = value[1:-1]
    elif value[-1:] in {'"', "'"}:
        raise ProductionLaunchError(
            f"runtime config line {line_number} has unmatched quotes"
        )
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ProductionLaunchError(
            f"runtime config line {line_number} contains invalid control data"
        )
    return value


def parse_runtime_config(config_path: Path) -> dict[str, str]:
    """Parse a tiny allowlisted env format without shell evaluation."""
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise ProductionLaunchError("release runtime config cannot be read") from exc
    if len(raw) > _MAX_CONFIG_BYTES:
        raise ProductionLaunchError("release runtime config is too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProductionLaunchError("release runtime config must be UTF-8") from exc

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or "=" not in line:
            raise ProductionLaunchError(
                f"runtime config line {line_number} must use KEY=VALUE"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_optional_quotes(value.strip(), line_number=line_number)
        if not _KEY_RE.fullmatch(key):
            raise ProductionLaunchError(
                f"runtime config line {line_number} has an invalid key"
            )
        if key not in RUNTIME_CONFIG_KEYS:
            raise ProductionLaunchError(
                f"runtime config key is not allowed: {key}"
            )
        if key in values:
            raise ProductionLaunchError(f"runtime config key is duplicated: {key}")
        values[key] = value

    missing = sorted(REQUIRED_RUNTIME_KEYS - values.keys())
    if missing:
        raise ProductionLaunchError(
            "release runtime config is missing required keys: " + ", ".join(missing)
        )
    if values["PERSONAL_OS_ENV"] != "production":
        raise ProductionLaunchError("release runtime must set PERSONAL_OS_ENV=production")
    if values["PERSONAL_OS_REMOTE"] != "1":
        raise ProductionLaunchError("release runtime must set PERSONAL_OS_REMOTE=1")
    if values["PERSONAL_OS_BIND_HOST"] != "127.0.0.1":
        raise ProductionLaunchError(
            "release runtime must bind the application to 127.0.0.1"
        )
    if values["PERSONAL_OS_TRUSTED_PROXY"] != "127.0.0.1":
        raise ProductionLaunchError(
            "release runtime must trust exactly the IPv4 loopback proxy"
        )
    if not values["PERSONAL_OS_PROXY_TOKEN"]:
        raise ProductionLaunchError("release runtime proxy token cannot be empty")
    if not values["PERSONAL_OS_TRUSTED_HOSTS"].strip():
        raise ProductionLaunchError("release runtime trusted hosts cannot be empty")
    if not values["SECRET_KEY"]:
        raise ProductionLaunchError("release runtime SECRET_KEY cannot be empty")
    return values


def _validate_mode(path: Path, *, label: str, forbidden_bits: int) -> os.stat_result:
    try:
        details = path.stat()
    except OSError as exc:
        raise ProductionLaunchError(f"cannot inspect {label} permissions") from exc
    if stat.S_IMODE(details.st_mode) & forbidden_bits:
        raise ProductionLaunchError(f"{label} permissions are too broad")
    return details


def _validate_posix_permissions(
    *,
    active_pointer: Path,
    descriptor: Path,
    code_root: Path,
    entrypoint: Path,
    gunicorn_config: Path,
    config_path: Path,
    database_path: Path,
    manifest_path: Path,
    database_root: Path | None = None,
    require_separated_database_artifacts: bool = False,
    venv_root: Path | None = None,
    venv_path: Path | None = None,
    python_executable: Path | None = None,
) -> None:
    if os.name == "nt":
        return
    effective_uid = os.geteuid()
    root_owned = {
        "active release pointer": active_pointer,
        "release descriptor": descriptor,
        "release entrypoint": entrypoint,
        "Gunicorn config": gunicorn_config,
        "runtime config": config_path,
        "database manifest": manifest_path,
        "database manifest checksum": Path(str(manifest_path) + ".sha256"),
    }
    # Every directory in the immutable code tree must also be protected. A
    # root-owned leaf file is not sufficient when the service user can replace
    # it through a writable parent directory between verification and import.
    root_owned_directories = {
        "release code root": code_root,
        "active pointer directory": active_pointer.parent,
        "release descriptor directory": descriptor.parent,
        "runtime config directory": config_path.parent,
    }
    if require_separated_database_artifacts:
        if database_root is None:
            raise ProductionLaunchError(
                "database root is required for separated artifact validation"
            )
        root_owned_directories.update(
            {
                "database root": database_root,
                "database manifest directory": manifest_path.parent,
            }
        )
        if venv_root is not None:
            root_owned_directories["venv root"] = venv_root
        if venv_path is not None:
            root_owned_directories["expected venv directory"] = venv_path
        if python_executable is not None:
            root_owned["venv python executable"] = python_executable
    for label, path in root_owned_directories.items():
        details = _validate_mode(
            path,
            label=label,
            forbidden_bits=stat.S_IWGRP | stat.S_IWOTH,
        )
        if details.st_uid != 0:
            raise ProductionLaunchError(f"{label} must be owned by root")
    for candidate in code_root.rglob("*"):
        if candidate.is_dir():
            details = _validate_mode(
                candidate,
                label="release code directory",
                forbidden_bits=stat.S_IWGRP | stat.S_IWOTH,
            )
            if details.st_uid != 0:
                raise ProductionLaunchError(
                    "every release code directory must be owned by root"
                )
    for label, path in root_owned.items():
        details = _validate_mode(
            path,
            label=label,
            forbidden_bits=stat.S_IWGRP | stat.S_IWOTH,
        )
        if details.st_uid != 0:
            raise ProductionLaunchError(f"{label} must be owned by root")
    _validate_mode(
        config_path,
        label="runtime config",
        forbidden_bits=stat.S_IRWXO | stat.S_IWGRP,
    )
    database_details = _validate_mode(
        database_path,
        label="runtime database",
        forbidden_bits=stat.S_IRWXG | stat.S_IRWXO,
    )
    if effective_uid == 0 or database_details.st_uid != effective_uid:
        raise ProductionLaunchError(
            "runtime database must be owned by the non-root service user"
        )
    if require_separated_database_artifacts:
        database_directory_details = _validate_mode(
            database_path.parent,
            label="runtime database directory",
            forbidden_bits=stat.S_IRWXG | stat.S_IRWXO,
        )
        if (
            effective_uid == 0
            or database_directory_details.st_uid != effective_uid
        ):
            raise ProductionLaunchError(
                "runtime database directory must be owned by the non-root "
                "service user"
            )


def _validate_separated_database_artifacts(
    *, database_root: Path, database_path: Path, manifest_path: Path
) -> None:
    """Require mutable database and immutable evidence to use distinct parents."""
    if database_path.parent == database_root:
        raise ProductionLaunchError(
            "separated runtime database must use a dedicated writable directory"
        )
    if database_path.parent == manifest_path.parent:
        raise ProductionLaunchError(
            "runtime database and immutable manifest must use separate directories"
        )


def _build_runtime_environment(
    values: dict[str, str],
    *,
    active_pointer: Path,
    release: dict,
    code_root: Path,
    database_path: Path,
    bind_port: int,
) -> dict[str, str]:
    present_forbidden = sorted(_FORBIDDEN_PARENT_ENV_KEYS & os.environ.keys())
    if present_forbidden:
        raise ProductionLaunchError(
            "launcher parent environment contains forbidden keys: "
            + ", ".join(present_forbidden)
        )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in _SAFE_PARENT_ENV_KEYS
    }
    environment.update(values)
    environment.update(
        {
            "YD_OS_DB_PATH": str(database_path),
            "PSY_ACTIVE_RELEASE_POINTER": str(active_pointer),
            "PSY_EXPECTED_APP_VERSION": release["application"]["version"],
            "PSY_EXPECTED_GIT_COMMIT": release["application"]["git_commit"],
            "PSY_RELEASE_DESCRIPTOR_SHA256": release["descriptor_sha256"],
            "PSY_RELEASE_ID": release["release_id"],
            "PSY_RELEASE_CODE_ROOT": str(code_root),
            "PSY_RELEASE_ENTRYPOINT_SHA256": release["application"][
                "entrypoint_sha256"
            ],
            "PSY_RELEASE_CONFIG_PATH": release["application"]["config_path"],
            "PSY_RELEASE_CONFIG_SHA256": release["application"]["config_sha256"],
            "PSY_RELEASE_DATABASE_PATH": str(database_path),
            GUNICORN_BIND_PORT_ENV: str(bind_port),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def prepare_launch(
    *,
    active_pointer,
    descriptor_root,
    release_root,
    config_root,
    database_root,
    expected_application_version: str,
    expected_git_commit: str,
    bind_port=DEFAULT_BIND_PORT,
    expected_database_path=None,
    require_separated_database_artifacts: bool = False,
    shadow_instance=None,
    expected_release_id=None,
    venv_root=None,
    expected_venv_path=None,
) -> LaunchPlan:
    """Resolve and validate the complete selected production launch plan."""
    bind_port = validate_bind_port(bind_port)
    approved_shadow_instance = None
    approved_release_id = None
    python_executable = Path(sys.executable)
    approved_venv_path = None
    approved_venv_root = None

    if require_separated_database_artifacts:
        if expected_database_path is None:
            raise ProductionLaunchError(
                "separated database artifacts require an explicitly approved "
                "database path"
            )
        if venv_root is None or expected_venv_path is None:
            raise ProductionLaunchError(
                "separated shadow launch requires both --venv-root and --expected-venv-path"
            )
        try:
            approved_shadow_instance = validate_shadow_identity(
                shadow_instance, label="shadow instance id"
            )
            approved_release_id = validate_shadow_identity(
                expected_release_id, label="shadow release id"
            )
        except ShadowDeploymentError as exc:
            raise ProductionLaunchError(str(exc)) from exc
    else:
        if venv_root is not None or expected_venv_path is not None:
            raise ProductionLaunchError(
                "non-separated production launch must not specify venv arguments"
            )

    if not str(expected_application_version or "").startswith("v2.2"):
        raise ProductionLaunchError("launcher only accepts an approved v2.2 release")
    if not _COMMIT_RE.fullmatch(str(expected_git_commit or "")):
        raise ProductionLaunchError("expected Git commit must be 40 lowercase hex chars")

    pointer = _canonical_existing(
        active_pointer, label="active release pointer", directory=False
    )
    descriptor_root = _canonical_existing(
        descriptor_root, label="descriptor root", directory=True
    )
    release_root = _canonical_existing(
        release_root, label="release root", directory=True
    )
    config_root = _canonical_existing(
        config_root, label="config root", directory=True
    )
    database_root = _canonical_existing(
        database_root, label="database root", directory=True
    )
    if require_separated_database_artifacts:
        approved_venv_root = _canonical_existing(
            venv_root, label="venv root", directory=True
        )
        approved_venv_path = _canonical_existing(
            expected_venv_path, label="expected venv path", directory=True
        )
        _require_within(
            approved_venv_path,
            approved_venv_root,
            label="expected venv path",
        )
        if approved_venv_path.name != f"{approved_shadow_instance}-{expected_git_commit}":
            raise ProductionLaunchError(
                "expected venv path does not match the approved instance and git commit"
            )
        if os.name == "nt":
            candidate_bin = approved_venv_path / "Scripts" / "python.exe"
            if not candidate_bin.exists():
                candidate_bin = approved_venv_path / "bin" / "python"
        else:
            candidate_bin = approved_venv_path / "bin" / "python"

        if not candidate_bin.is_file() or candidate_bin.stat().st_size <= 0:
            raise ProductionLaunchError(
                "venv python executable must exist and be a non-empty regular file"
            )
        python_executable = candidate_bin

    approved_database_path = None
    if expected_database_path is not None:
        approved_database_path = _canonical_existing(
            expected_database_path,
            label="approved runtime database",
            directory=False,
        )
        _require_within(
            approved_database_path,
            database_root,
            label="approved runtime database",
        )
    _require_within(pointer, descriptor_root, label="active release pointer")

    try:
        release = resolve_active_release(
            pointer,
            expected_git_commit=expected_git_commit,
            expected_application_version=expected_application_version,
            # Runtime databases are mutable after activation.  Startup still
            # verifies the signed-by-permissions manifest, exact schema/profile,
            # integrity, row invariants, and code/config hashes.
            verify_immutable_database=False,
        )
    except ReleaseSwitchError as exc:
        raise ProductionLaunchError(str(exc)) from exc

    if require_separated_database_artifacts:
        try:
            selected_release_id = validate_shadow_identity(
                release["release_id"], label="selected shadow release id"
            )
        except (KeyError, ShadowDeploymentError) as exc:
            raise ProductionLaunchError("selected shadow release id is invalid") from exc
        if selected_release_id != approved_release_id:
            raise ProductionLaunchError(
                "selected shadow release id does not match the approved release id"
            )

    descriptor = Path(release["descriptor"])
    code_root = Path(release["application"]["code_root"])
    entrypoint = Path(release["application"]["entrypoint"])
    config_path = Path(release["application"]["config_path"])
    database_path = Path(release["database"]["path"])
    manifest_path = Path(release["database"]["manifest_path"])
    if (
        approved_database_path is not None
        and database_path != approved_database_path
    ):
        raise ProductionLaunchError(
            "descriptor database does not match the explicitly approved path"
        )
    for path, root, label in (
        (descriptor, descriptor_root, "release descriptor"),
        (code_root, release_root, "release code root"),
        (config_path, config_root, "runtime config"),
        (database_path, database_root, "runtime database"),
        (manifest_path, database_root, "database manifest"),
    ):
        _require_within(path, root, label=label)
    if require_separated_database_artifacts:
        _validate_separated_database_artifacts(
            database_root=database_root,
            database_path=database_path,
            manifest_path=manifest_path,
        )
    try:
        config_path.relative_to(code_root)
    except ValueError:
        pass
    else:
        raise ProductionLaunchError("runtime config must be outside the code root")
    if (code_root / ".env").exists():
        raise ProductionLaunchError("release code root must not contain a .env file")
    if entrypoint != code_root / "production.py":
        raise ProductionLaunchError("release entrypoint must be code_root/production.py")
    gunicorn_config = _canonical_existing(
        code_root / "gunicorn.conf.py", label="Gunicorn config", directory=False
    )

    runtime_values = parse_runtime_config(config_path)
    _validate_posix_permissions(
        active_pointer=pointer,
        descriptor=descriptor,
        code_root=code_root,
        entrypoint=entrypoint,
        gunicorn_config=gunicorn_config,
        config_path=config_path,
        database_path=database_path,
        manifest_path=manifest_path,
        database_root=database_root,
        require_separated_database_artifacts=require_separated_database_artifacts,
        venv_root=approved_venv_root,
        venv_path=approved_venv_path,
        python_executable=python_executable if require_separated_database_artifacts else None,
    )
    environment = _build_runtime_environment(
        runtime_values,
        active_pointer=pointer,
        release=release,
        code_root=code_root,
        database_path=database_path,
        bind_port=bind_port,
    )
    command = (
        str(python_executable),
        "-m",
        "gunicorn",
        "--config",
        str(gunicorn_config),
        "production:create_production_app()",
    )
    if os.name == "nt":
        # Windows is limited to resolver/preflight and local reverse-proxy
        # acceptance. Gunicorn execution remains a Linux-only production path.
        command = ()
    return LaunchPlan(
        active_pointer=pointer,
        descriptor=descriptor,
        descriptor_sha256=release["descriptor_sha256"],
        release_id=release["release_id"],
        application_version=release["application"]["version"],
        git_commit=release["application"]["git_commit"],
        code_root=code_root,
        entrypoint=entrypoint,
        gunicorn_config=gunicorn_config,
        config_path=config_path,
        database_path=database_path,
        database_manifest_path=manifest_path,
        separated_database_artifacts=require_separated_database_artifacts,
        shadow_instance=approved_shadow_instance,
        bind_port=bind_port,
        runtime_environment=environment,
        command=command,
        python_executable=python_executable,
        venv_path=approved_venv_path,
    )


def run_selected_preflight(plan: LaunchPlan) -> None:
    executable = str(plan.python_executable) if plan.python_executable else sys.executable
    try:
        result = subprocess.run(
            [executable, str(plan.entrypoint), "--check"],
            cwd=plan.code_root,
            env=plan.runtime_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProductionLaunchError("selected release preflight could not run") from exc
    if result.returncode != 0:
        raise ProductionLaunchError("selected release production preflight failed")


def launch(plan: LaunchPlan) -> None:
    """Preflight, then replace this process with the fixed Gunicorn command."""
    if os.name == "nt" or not plan.command:
        raise ProductionLaunchError("Gunicorn production launch requires Linux")
    run_selected_preflight(plan)
    executable = str(plan.python_executable) if plan.python_executable else sys.executable
    try:
        os.chdir(plan.code_root)
        os.execve(executable, list(plan.command), plan.runtime_environment)
    except OSError as exc:
        raise ProductionLaunchError("Gunicorn exec failed") from exc


def _report(plan: LaunchPlan) -> dict:
    return {
        "ok": True,
        "release_id": plan.release_id,
        "application_version": plan.application_version,
        "git_commit": plan.git_commit,
        "descriptor_sha256": plan.descriptor_sha256,
        "code_root": str(plan.code_root),
        "entrypoint": str(plan.entrypoint),
        "config_path": str(plan.config_path),
        "database_path": str(plan.database_path),
        "database_manifest_path": str(plan.database_manifest_path),
        "separated_database_artifacts": plan.separated_database_artifacts,
        "shadow_instance": plan.shadow_instance,
        "venv_path": str(plan.venv_path) if plan.venv_path else None,
        "python_executable": str(plan.python_executable) if plan.python_executable else sys.executable,
        "gunicorn": {
            "bind": f"127.0.0.1:{plan.bind_port}",
            "workers": 1,
            "worker_class": "gthread",
            "threads": 4,
            "preload": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed PSY active-release production launcher"
    )
    parser.add_argument("--active-pointer", type=Path, required=True)
    parser.add_argument("--descriptor-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--database-root", type=Path, required=True)
    parser.add_argument("--expected-app-version", required=True)
    parser.add_argument("--expected-git-commit", required=True)
    parser.add_argument(
        "--bind-port",
        default=str(DEFAULT_BIND_PORT),
        help=(
            "loopback Gunicorn port; defaults to 5000 and must be an "
            "unprivileged decimal TCP port"
        ),
    )
    parser.add_argument(
        "--require-separated-database-artifacts",
        action="store_true",
        help=(
            "require the writable database and immutable manifest to live in "
            "different directories"
        ),
    )
    parser.add_argument(
        "--expected-database-path",
        type=Path,
        help=(
            "exact runtime database approval; required for separated shadow artifacts"
        ),
    )
    parser.add_argument(
        "--shadow-instance",
        help="strict Phase 5A shadow instance id",
    )
    parser.add_argument(
        "--expected-release-id",
        help="strict, explicitly approved Phase 5A shadow release id",
    )
    parser.add_argument(
        "--venv-root",
        type=Path,
        help="strict venv root directory; required for separated shadow mode",
    )
    parser.add_argument(
        "--expected-venv-path",
        type=Path,
        help="strict expected venv path; required for separated shadow mode",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="resolve the active release and run its preflight without listening",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = prepare_launch(
            active_pointer=args.active_pointer,
            descriptor_root=args.descriptor_root,
            release_root=args.release_root,
            config_root=args.config_root,
            database_root=args.database_root,
            expected_application_version=args.expected_app_version,
            expected_git_commit=args.expected_git_commit,
            bind_port=args.bind_port,
            expected_database_path=args.expected_database_path,
            require_separated_database_artifacts=(
                args.require_separated_database_artifacts
            ),
            shadow_instance=args.shadow_instance,
            expected_release_id=args.expected_release_id,
            venv_root=args.venv_root,
            expected_venv_path=args.expected_venv_path,
        )
        if args.check:
            run_selected_preflight(plan)
            print(json.dumps(_report(plan), ensure_ascii=False, sort_keys=True))
            return 0
        launch(plan)
    except (ProductionLaunchError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
