import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import auth_service
import database
import production
import production_launcher
from database_artifacts import create_database_manifest
from production_launcher import ProductionLaunchError
from release_switch import (
    ReleaseSwitchError,
    activate_release_pointer,
    create_release_descriptor,
    resolve_active_release,
)
from v22_migration import migrate_legacy_database


APP_ROOT = Path(__file__).parents[1].resolve()
FIXTURE_SQL = Path(__file__).parent / "fixtures" / "legacy_v214.sql"
HEAD_COMMIT = "fa7f01486cb36e765544b8f55c60c145a83df0ae"
APP_VERSION = "v2.2.0"
STRONG_SECRET = "K9vQ2mL7xR4cT8pN5wD3jH6sF1zB0yG8uC4aE7rM2kP9nV5q"
STRONG_PROXY_TOKEN = "R7wK4nT9pL2xV6cH1mQ8sD5fJ3zB0yG9uN4aE7rM2kP6vC8q"


def _copy_release(tmp_path):
    release_root = tmp_path / "releases"
    code_root = release_root / "v22"
    shutil.copytree(
        APP_ROOT,
        code_root,
        ignore=shutil.ignore_patterns(
            ".git", ".pytest_cache", "__pycache__", "backups", "data", ".env"
        ),
    )
    return release_root.resolve(), code_root.resolve()


def _build_active_release(tmp_path, *, config_text=None):
    descriptor_root = (tmp_path / "selectors").resolve()
    config_root = (tmp_path / "config").resolve()
    database_root = (tmp_path / "databases").resolve()
    for directory in (descriptor_root, config_root, database_root):
        directory.mkdir()
    release_root, code_root = _copy_release(tmp_path)
    source = database_root / "legacy.db"
    connection = sqlite3.connect(source)
    connection.executescript(FIXTURE_SQL.read_text(encoding="utf-8"))
    connection.close()
    staged = database_root / "staged-v22.db"
    migrate_legacy_database(
        source,
        staged,
        admin_username="phase43-admin",
        admin_email="phase43-admin@example.test",
        admin_password="correct horse battery",
    )
    manifest = database_root / "staged-v22.db.manifest.json"
    create_database_manifest(
        staged.resolve(),
        manifest.resolve(),
        expected_profile="v22",
        artifact_kind="migration-staged",
        source_path=source.resolve(),
        source_profile="legacy_v214",
        git_commit=HEAD_COMMIT,
        application_version=APP_VERSION,
    )
    config_path = config_root / "runtime.env"
    config_path.write_text(
        config_text
        or "\n".join(
            (
                "PERSONAL_OS_ENV=production",
                "PERSONAL_OS_REMOTE=1",
                "PERSONAL_OS_BIND_HOST=127.0.0.1",
                "PERSONAL_OS_TRUSTED_HOSTS=psy.localhost",
                "PERSONAL_OS_TRUSTED_PROXY=127.0.0.1",
                f"PERSONAL_OS_PROXY_TOKEN={STRONG_PROXY_TOKEN}",
                f"SECRET_KEY={STRONG_SECRET}",
                "",
            )
        ),
        encoding="utf-8",
    )
    descriptor = descriptor_root / "v22.json"
    create_release_descriptor(
        descriptor.resolve(),
        release_id="phase43-v22",
        application_version=APP_VERSION,
        git_commit=HEAD_COMMIT,
        code_root=code_root,
        code_entrypoint=code_root / "production.py",
        config_path=config_path.resolve(),
        database_path=staged.resolve(),
        database_manifest_path=manifest.resolve(),
        expected_profile="v22",
    )
    pointer = descriptor_root / "active-release.json"
    activate_release_pointer(
        descriptor.resolve(),
        pointer.resolve(),
        service_is_stopped=True,
        expected_git_commit=HEAD_COMMIT,
        expected_application_version=APP_VERSION,
    )
    return SimpleNamespace(
        pointer=pointer.resolve(),
        descriptor=descriptor.resolve(),
        descriptor_root=descriptor_root,
        release_root=release_root,
        code_root=code_root,
        config_root=config_root,
        config_path=config_path.resolve(),
        database_root=database_root,
        database=staged.resolve(),
        manifest=manifest.resolve(),
    )


def _prepare(release):
    return production_launcher.prepare_launch(
        active_pointer=release.pointer,
        descriptor_root=release.descriptor_root,
        release_root=release.release_root,
        config_root=release.config_root,
        database_root=release.database_root,
        expected_application_version=APP_VERSION,
        expected_git_commit=HEAD_COMMIT,
    )


def _port_is_open(port=5000):
    with socket.socket() as probe:
        probe.settimeout(0.15)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def test_launcher_resolves_descriptor_as_the_only_code_config_and_db_selector(
    tmp_path, monkeypatch
):
    release = _build_active_release(tmp_path)
    monkeypatch.setenv("YD_OS_DB_PATH", str((tmp_path / "wrong.db").resolve()))
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)

    plan = _prepare(release)

    assert plan.code_root == release.code_root
    assert plan.entrypoint == release.code_root / "production.py"
    assert plan.gunicorn_config == release.code_root / "gunicorn.conf.py"
    assert plan.config_path == release.config_path
    assert plan.database_path == release.database
    assert plan.runtime_environment["YD_OS_DB_PATH"] == str(release.database)
    assert "GUNICORN_CMD_ARGS" not in plan.runtime_environment
    expected_command = (
        sys.executable,
        "-m",
        "gunicorn",
        "--config",
        str(release.code_root / "gunicorn.conf.py"),
        "production:create_production_app()",
    )
    assert plan.command == (() if os.name == "nt" else expected_command)
    assert "--workers" not in plan.command
    assert "--bind" not in plan.command


@pytest.mark.parametrize(
    "bad_line",
    (
        "YD_OS_DB_PATH=/tmp/attacker.db",
        "GUNICORN_CMD_ARGS=--workers 9",
        "FLASK_DEBUG=1",
        "export PERSONAL_OS_ENV=production",
        "PERSONAL_OS_ENV=$(touch /tmp/psy-shell-injection)",
    ),
)
def test_runtime_config_rejects_unknown_keys_and_shell_syntax(tmp_path, bad_line):
    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join(
            (
                bad_line,
                "PERSONAL_OS_ENV=production",
                "PERSONAL_OS_REMOTE=1",
                "PERSONAL_OS_BIND_HOST=127.0.0.1",
                "PERSONAL_OS_TRUSTED_HOSTS=psy.localhost",
                "PERSONAL_OS_TRUSTED_PROXY=127.0.0.1",
                f"PERSONAL_OS_PROXY_TOKEN={STRONG_PROXY_TOKEN}",
                f"SECRET_KEY={STRONG_SECRET}",
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProductionLaunchError):
        production_launcher.parse_runtime_config(config_path)


def test_launcher_rejects_dangerous_parent_environment(tmp_path, monkeypatch):
    release = _build_active_release(tmp_path)
    monkeypatch.setenv("GUNICORN_CMD_ARGS", "--workers 9 --bind 0.0.0.0:5000")

    with pytest.raises(ProductionLaunchError, match="GUNICORN_CMD_ARGS"):
        _prepare(release)


@pytest.mark.parametrize("mutation", ("pointer", "descriptor", "code", "config"))
def test_launcher_rejects_pointer_descriptor_code_or_config_tampering(
    tmp_path, monkeypatch, mutation
):
    release = _build_active_release(tmp_path)
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)
    if mutation == "pointer":
        payload = json.loads(release.pointer.read_text(encoding="utf-8"))
        payload["descriptor_sha256"] = "0" * 64
        release.pointer.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "descriptor":
        with release.descriptor.open("ab") as stream:
            stream.write(b"\n")
    elif mutation == "code":
        with (release.code_root / "production.py").open("a", encoding="utf-8") as stream:
            stream.write("\n# tampered\n")
    else:
        with release.config_path.open("a", encoding="utf-8") as stream:
            stream.write("# tampered\n")

    with pytest.raises(ProductionLaunchError):
        _prepare(release)


def test_runtime_database_may_change_rows_but_not_schema_or_integrity(
    tmp_path, monkeypatch
):
    release = _build_active_release(tmp_path)
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)
    connection = sqlite3.connect(release.database)
    connection.execute("UPDATE goals SET name = 'runtime write' WHERE id = 10")
    connection.commit()
    connection.close()

    assert _prepare(release).database_path == release.database

    connection = sqlite3.connect(release.database)
    connection.execute("PRAGMA user_version = 999")
    connection.commit()
    connection.close()
    with pytest.raises(ProductionLaunchError, match="schema|invariant"):
        _prepare(release)


def test_selected_preflight_fails_closed_before_any_listener(tmp_path, monkeypatch):
    release = _build_active_release(tmp_path)
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)
    plan = _prepare(release)
    listener_state_before = _port_is_open()

    release.config_path.write_text(
        release.config_path.read_text(encoding="utf-8").replace(
            f"SECRET_KEY={STRONG_SECRET}", "SECRET_KEY=weak"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProductionLaunchError, match="preflight"):
        production_launcher.run_selected_preflight(plan)
    # This assertion must remain valid while a disposable acceptance harness
    # legitimately owns port 5000 in another process: preflight itself may not
    # change the listener state in either direction.
    assert _port_is_open() is listener_state_before


def test_production_preflight_requires_and_revalidates_launcher_context(
    tmp_path, monkeypatch
):
    release = _build_active_release(tmp_path)
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)
    plan = _prepare(release)
    monkeypatch.setattr(database, "DB_PATH", str(release.database))
    monkeypatch.setattr(production, "__file__", str(release.code_root / "production.py"))
    for key, value in plan.runtime_environment.items():
        monkeypatch.setenv(key, value)
    import config

    config._PRODUCTION_PREFLIGHT_PATH = None
    report = production.run_preflight()
    assert report["release"] == {
        "release_id": "phase43-v22",
        "application_version": APP_VERSION,
        "git_commit": HEAD_COMMIT,
        "descriptor_sha256": plan.descriptor_sha256,
    }

    monkeypatch.setenv("PSY_RELEASE_DESCRIPTOR_SHA256", "0" * 64)
    config._PRODUCTION_PREFLIGHT_PATH = None
    with pytest.raises(production.ProductionPreflightError, match="不一致"):
        production.run_preflight()


def test_direct_production_entry_without_launcher_is_rejected(tmp_path, monkeypatch):
    release = _build_active_release(tmp_path)
    monkeypatch.setattr(database, "DB_PATH", str(release.database))
    for key in tuple(os.environ):
        if key.startswith("PSY_RELEASE_") or key.startswith("PSY_EXPECTED_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("PSY_ACTIVE_RELEASE_POINTER", raising=False)
    with pytest.raises(production.ProductionPreflightError, match="launcher"):
        production.run_preflight()


def test_public_gunicorn_factory_cannot_disable_release_context(monkeypatch):
    calls = []

    def fake_create_app(*, require_release_context=True):
        calls.append(require_release_context)
        return object()

    monkeypatch.setattr(production, "create_app", fake_create_app)
    production.create_production_app()
    assert calls == [True]


def test_release_pointer_requires_a_canonical_descriptor_path(tmp_path):
    release = _build_active_release(tmp_path)
    alias = release.descriptor_root / "alias.json"
    try:
        alias.symlink_to(release.descriptor)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    payload = json.loads(release.pointer.read_text(encoding="utf-8"))
    payload["descriptor_path"] = str(alias)
    release.pointer.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReleaseSwitchError, match="canonical"):
        resolve_active_release(
            release.pointer,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version=APP_VERSION,
            verify_immutable_database=False,
        )


def test_malformed_or_non_regular_active_pointer_fails_closed(tmp_path):
    malformed = (tmp_path / "malformed-active.json").resolve()
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ReleaseSwitchError, match="not valid UTF-8 JSON"):
        resolve_active_release(
            malformed,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version=APP_VERSION,
            verify_immutable_database=False,
        )

    non_regular = (tmp_path / "active-release-directory").resolve()
    non_regular.mkdir()
    with pytest.raises(ReleaseSwitchError, match="non-empty regular file"):
        resolve_active_release(
            non_regular,
            expected_git_commit=HEAD_COMMIT,
            expected_application_version=APP_VERSION,
            verify_immutable_database=False,
        )


def test_launcher_rejects_symlink_active_pointer(tmp_path):
    pointer = (tmp_path / "active-release.json").resolve()
    pointer.write_text("{}", encoding="utf-8")
    alias = tmp_path / "active-release-alias.json"
    try:
        alias.symlink_to(pointer)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ProductionLaunchError, match="canonical and not a symlink"):
        production_launcher.prepare_launch(
            active_pointer=alias.absolute(),
            descriptor_root=tmp_path.resolve(),
            release_root=tmp_path.resolve(),
            config_root=tmp_path.resolve(),
            database_root=tmp_path.resolve(),
            expected_application_version=APP_VERSION,
            expected_git_commit=HEAD_COMMIT,
        )


@pytest.mark.parametrize(
    "untrusted_label", ("active release pointer", "release descriptor")
)
def test_launcher_posix_permissions_require_root_owned_release_metadata(
    tmp_path, monkeypatch, untrusted_label
):
    code_root = tmp_path / "code"
    code_root.mkdir()

    def fake_validate_mode(_path, *, label, forbidden_bits):
        del forbidden_bits
        return SimpleNamespace(st_uid=1000 if label == untrusted_label else 0)

    monkeypatch.setattr(
        production_launcher,
        "os",
        SimpleNamespace(name="posix", geteuid=lambda: 1000),
    )
    monkeypatch.setattr(production_launcher, "_validate_mode", fake_validate_mode)

    with pytest.raises(
        ProductionLaunchError, match=f"{untrusted_label} must be owned by root"
    ):
        production_launcher._validate_posix_permissions(
            active_pointer=tmp_path / "active-release.json",
            descriptor=tmp_path / "release.json",
            code_root=code_root,
            entrypoint=code_root / "production.py",
            gunicorn_config=code_root / "gunicorn.conf.py",
            config_path=tmp_path / "runtime.env",
            database_path=tmp_path / "runtime.db",
            manifest_path=tmp_path / "runtime.db.manifest.json",
        )


def test_gunicorn_guard_rejects_cli_worker_and_bind_overrides_via_real_check(
    tmp_path, monkeypatch
):
    if os.name == "nt" or subprocess.run(
        [sys.executable, "-c", "import gunicorn"], capture_output=True
    ).returncode:
        pytest.skip("real Gunicorn check requires Linux with Gunicorn installed")
    release = _build_active_release(tmp_path)
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)
    plan = _prepare(release)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gunicorn",
            "--check-config",
            "--workers",
            "2",
            "--bind",
            "0.0.0.0:5000",
            "--config",
            str(plan.gunicorn_config),
            "production:create_production_app()",
        ],
        cwd=plan.code_root,
        env=plan.runtime_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_systemd_template_has_no_shell_and_delegates_to_active_release_launcher():
    unit = (APP_ROOT / "deploy" / "psy-v22.service").read_text(encoding="utf-8")
    assert "User=psy" in unit
    assert "Group=psy" in unit
    assert "WorkingDirectory=/opt/psy/launcher" in unit
    assert "EnvironmentFile=/etc/psy/launcher.env" in unit
    assert "production_launcher.py" in unit
    assert "--active-pointer /var/lib/psy/releases/active-release.json" in unit
    assert "--database-root /var/lib/psy/databases" in unit
    assert "YD_OS_DB_PATH" not in unit
    assert "sh -c" not in unit and "/bin/bash" not in unit
    assert "Restart=on-failure" in unit
    assert "TimeoutStartSec=90s" in unit and "TimeoutStopSec=45s" in unit
    assert "ReadOnlyPaths=" in unit and "ReadWritePaths=/var/lib/psy/databases" in unit
    assert "--workers" not in unit and "--bind" not in unit


def test_nginx_template_owns_proxy_boundary_without_security_header_conflicts():
    nginx = (APP_ROOT / "deploy" / "nginx-psy-v22.conf").read_text(
        encoding="utf-8"
    )
    assert "listen 80;" in nginx
    assert "return 308 https://psy.example.com$request_uri;" in nginx
    assert "listen 80 default_server;" in nginx
    assert "listen 443 ssl http2 default_server;" in nginx
    assert nginx.count("return 444;") == 2
    assert "listen 443 ssl http2;" in nginx
    assert "proxy_pass http://127.0.0.1:5000;" in nginx
    assert "client_max_body_size 16m;" in nginx
    assert "proxy_set_header Host psy.example.com;" in nginx
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "proxy_set_header X-Forwarded-Proto https;" in nginx
    assert "proxy_set_header X-Forwarded-Host psy.example.com;" in nginx
    assert "proxy_set_header Host $host;" not in nginx
    assert "https://$host" not in nginx
    assert "include /etc/nginx/snippets/psy-proxy-auth.conf;" in nginx
    assert "$proxy_add_x_forwarded_for" not in nginx
    assert "proxy_pass http://0.0.0.0" not in nginx
    assert not re.search(r"^\s*add_header\s+", nginx, flags=re.MULTILINE)
    assert "location = /api/health" in nginx
    assert "limit_req zone=psy_login_source" in nginx


def test_template_examples_do_not_contain_real_secrets_or_database_paths():
    deploy = APP_ROOT / "deploy"
    runtime = (deploy / "runtime.env.example").read_text(encoding="utf-8")
    launcher = (deploy / "launcher.env.example").read_text(encoding="utf-8")
    assert "YD_OS_DB_PATH" not in runtime
    assert "yd_os.db" not in runtime.casefold()
    assert "root:psy" in runtime and "0640" in runtime
    assert "never install this secret-bearing file as mode 0644" in runtime
    assert "replace_with" in runtime and STRONG_SECRET not in runtime
    assert "replace_with" in launcher and HEAD_COMMIT not in launcher


def test_nginx_proxy_token_snippet_is_header_only_and_has_no_committed_secret():
    snippet = (APP_ROOT / "deploy" / "nginx-psy-proxy-auth.conf.example").read_text(
        encoding="utf-8"
    )
    assert "proxy_set_header X-PSY-Proxy-Token" in snippet
    assert "replace_with" in snippet
    assert STRONG_PROXY_TOKEN not in snippet
    assert "SECRET_KEY" not in snippet
    assert "YD_OS_DB_PATH" not in snippet


def test_phase43_browser_fixture_can_seed_three_users_without_real_data(
    tmp_path, monkeypatch
):
    db_path = (tmp_path / "browser.db").resolve()
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()
    admin = auth_service.bootstrap_admin(
        "phase43admin", "phase43admin@example.test", "Admin phase43 password"
    )
    user_a, _ = auth_service.create_standard_user(
        "phase43usera", "phase43usera@example.test"
    )
    user_b, _ = auth_service.create_standard_user(
        "phase43userb", "phase43userb@example.test"
    )
    assert {admin["role"], user_a["role"], user_b["role"]} == {"admin", "user"}
    assert str(db_path).casefold().endswith("browser.db")
    assert "data" not in db_path.parts[-2:]


def test_production_launcher_compatibility_rejects_venv_arguments_in_standard_mode(
    tmp_path, monkeypatch
):
    release = _build_active_release(tmp_path)
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)

    # 1. Both defaulted/omitted -> PASS / existing behavior
    plan = _prepare(release)
    assert plan.code_root == release.code_root
    assert plan.venv_path is None
    assert plan.python_executable == Path(sys.executable)

    # 2. Only venv-root passed -> FAIL
    with pytest.raises(
        ProductionLaunchError, match="must not specify venv arguments"
    ):
        production_launcher.prepare_launch(
            active_pointer=release.pointer,
            descriptor_root=release.descriptor_root,
            release_root=release.release_root,
            config_root=release.config_root,
            database_root=release.database_root,
            expected_application_version=APP_VERSION,
            expected_git_commit=HEAD_COMMIT,
            venv_root=tmp_path / "venvs",
        )

    # 3. Only expected-venv-path passed -> FAIL
    with pytest.raises(
        ProductionLaunchError, match="must not specify venv arguments"
    ):
        production_launcher.prepare_launch(
            active_pointer=release.pointer,
            descriptor_root=release.descriptor_root,
            release_root=release.release_root,
            config_root=release.config_root,
            database_root=release.database_root,
            expected_application_version=APP_VERSION,
            expected_git_commit=HEAD_COMMIT,
            expected_venv_path=tmp_path / "venvs" / "fake-venv",
        )

    # 4. Both passed -> FAIL
    with pytest.raises(
        ProductionLaunchError, match="must not specify venv arguments"
    ):
        production_launcher.prepare_launch(
            active_pointer=release.pointer,
            descriptor_root=release.descriptor_root,
            release_root=release.release_root,
            config_root=release.config_root,
            database_root=release.database_root,
            expected_application_version=APP_VERSION,
            expected_git_commit=HEAD_COMMIT,
            venv_root=tmp_path / "venvs",
            expected_venv_path=tmp_path / "venvs" / "fake-venv",
        )
