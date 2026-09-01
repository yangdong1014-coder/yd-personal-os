import os
import re
import runpy
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import changelog
import production_launcher
import shadow_deployment
from production_launcher import ProductionLaunchError
from shadow_deployment import ShadowDeploymentError


APP_ROOT = Path(__file__).parents[1].resolve()
REPO_ROOT = APP_ROOT.parent.resolve()
APP_VERSION = "v2.2.0-shadow"
GIT_COMMIT = "ad6280ab04024e07da0fbd1db8b64f20dabe633e"
STRONG_SECRET = "K9vQ2mL7xR4cT8pN5wD3jH6sF1zB0yG8uC4aE7rM2kP9nV5q"
STRONG_PROXY_TOKEN = "R7wK4nT9pL2xV6cH1mQ8sD5fJ3zB0yG9uN4aE7rM2kP6vC8q"


def _clear_forbidden_parent_environment(monkeypatch):
    for key in production_launcher._FORBIDDEN_PARENT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _fake_release_layout(tmp_path, monkeypatch):
    descriptor_root = (tmp_path / "selectors").resolve()
    release_root = (tmp_path / "releases").resolve()
    code_root = (release_root / "code").resolve()
    config_root = (tmp_path / "config").resolve()
    database_root = (tmp_path / "shadow-databases").resolve()
    runtime_parent = (database_root / "staged").resolve()
    manifest_parent = (database_root / "manifests").resolve()
    venv_root = (tmp_path / "venvs").resolve()
    expected_venv_path = (venv_root / f"phase5a-test-{GIT_COMMIT}").resolve()
    venv_bin = expected_venv_path / ("Scripts" if os.name == "nt" else "bin")
    for directory in (
        descriptor_root,
        code_root,
        config_root,
        runtime_parent,
        manifest_parent,
        venv_root,
        expected_venv_path,
        venv_bin,
    ):
        directory.mkdir(parents=True, exist_ok=False)

    venv_python = venv_bin / ("python.exe" if os.name == "nt" else "python")
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")

    pointer = (descriptor_root / "active-release.json").resolve()
    descriptor = (descriptor_root / "shadow.json").resolve()
    entrypoint = (code_root / "production.py").resolve()
    gunicorn_config = (code_root / "gunicorn.conf.py").resolve()
    runtime_config = (config_root / "runtime.env").resolve()
    database_path = (runtime_parent / "yd_os-v22-shadow.db").resolve()
    manifest_path = (
        manifest_parent / "yd_os-v22-shadow.db.manifest.json"
    ).resolve()

    pointer.write_text("{}", encoding="utf-8")
    descriptor.write_text("{}", encoding="utf-8")
    entrypoint.write_text("# test entrypoint\n", encoding="utf-8")
    gunicorn_config.write_text("bind = '127.0.0.1:5000'\n", encoding="utf-8")
    runtime_config.write_text(
        "\n".join(
            (
                "PERSONAL_OS_ENV=production",
                "PERSONAL_OS_REMOTE=1",
                "PERSONAL_OS_BIND_HOST=127.0.0.1",
                "PERSONAL_OS_TRUSTED_HOSTS=shadow.example.test",
                "PERSONAL_OS_TRUSTED_PROXY=127.0.0.1",
                f"PERSONAL_OS_PROXY_TOKEN={STRONG_PROXY_TOKEN}",
                f"SECRET_KEY={STRONG_SECRET}",
                "",
            )
        ),
        encoding="utf-8",
    )
    database_path.write_bytes(b"temporary shadow database placeholder")
    manifest_path.write_text("{}", encoding="utf-8")
    Path(str(manifest_path) + ".sha256").write_text("0" * 64, encoding="ascii")

    resolved_release = {
        "descriptor": str(descriptor),
        "descriptor_sha256": "1" * 64,
        "release_id": "phase5a-test",
        "application": {
            "version": APP_VERSION,
            "git_commit": GIT_COMMIT,
            "code_root": str(code_root),
            "entrypoint": str(entrypoint),
            "entrypoint_sha256": "2" * 64,
            "config_path": str(runtime_config),
            "config_sha256": "3" * 64,
        },
        "database": {
            "path": str(database_path),
            "manifest_path": str(manifest_path),
        },
    }
    monkeypatch.setattr(
        production_launcher,
        "resolve_active_release",
        lambda *_args, **_kwargs: resolved_release,
    )
    monkeypatch.setattr(
        production_launcher,
        "_validate_posix_permissions",
        lambda **_kwargs: None,
    )
    _clear_forbidden_parent_environment(monkeypatch)
    return SimpleNamespace(
        pointer=pointer,
        descriptor_root=descriptor_root,
        release_root=release_root,
        config_root=config_root,
        database_root=database_root,
        database_path=database_path,
        manifest_path=manifest_path,
        venv_root=venv_root,
        expected_venv_path=expected_venv_path,
        venv_python=venv_python,
        release=resolved_release,
    )


def _prepare(layout, **overrides):
    require_separated = overrides.get(
        "require_separated_database_artifacts", True
    )
    values = {
        "active_pointer": layout.pointer,
        "descriptor_root": layout.descriptor_root,
        "release_root": layout.release_root,
        "config_root": layout.config_root,
        "database_root": layout.database_root,
        "expected_application_version": APP_VERSION,
        "expected_git_commit": GIT_COMMIT,
        "expected_database_path": layout.database_path,
        "require_separated_database_artifacts": True,
        "shadow_instance": "phase5a-test",
        "expected_release_id": layout.release["release_id"],
    }
    if require_separated:
        values["venv_root"] = layout.venv_root
        values["expected_venv_path"] = layout.expected_venv_path
    values.update(overrides)
    return production_launcher.prepare_launch(**values)


def test_launcher_default_remains_loopback_5000(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    plan = _prepare(layout)

    assert plan.bind_port == 5000
    assert plan.runtime_environment["PSY_GUNICORN_BIND_PORT"] == "5000"
    assert production_launcher._report(plan)["gunicorn"]["bind"] == (
        "127.0.0.1:5000"
    )
    assert "--bind" not in plan.command


def test_launcher_approved_shadow_port_has_one_runtime_truth(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    plan = _prepare(layout, bind_port="5100")

    assert plan.bind_port == 5100
    assert plan.runtime_environment["PSY_GUNICORN_BIND_PORT"] == "5100"
    assert production_launcher._report(plan)["gunicorn"]["bind"] == (
        "127.0.0.1:5100"
    )


@pytest.mark.parametrize(
    "value",
    (None, "", " 5100", "5100 ", "+5100", "5100.0", "abc", "9" * 5000, -1, 0, 80, 1023, 65536, False),
)
def test_launcher_rejects_invalid_or_privileged_ports(value):
    with pytest.raises(ProductionLaunchError, match="bind port"):
        production_launcher.validate_bind_port(value)


def test_hostile_parent_cannot_override_launcher_approved_bind(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)
    monkeypatch.setenv("PSY_GUNICORN_BIND_PORT", "6200")

    with pytest.raises(ProductionLaunchError, match="PSY_GUNICORN_BIND_PORT"):
        _prepare(layout, bind_port=5100)


def test_runtime_config_rejects_external_host_override(tmp_path):
    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join(
            (
                "PERSONAL_OS_ENV=production",
                "PERSONAL_OS_REMOTE=1",
                "PERSONAL_OS_BIND_HOST=0.0.0.0",
                "PERSONAL_OS_TRUSTED_HOSTS=shadow.example.test",
                "PERSONAL_OS_TRUSTED_PROXY=127.0.0.1",
                f"PERSONAL_OS_PROXY_TOKEN={STRONG_PROXY_TOKEN}",
                f"SECRET_KEY={STRONG_SECRET}",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProductionLaunchError, match="127.0.0.1"):
        production_launcher.parse_runtime_config(config_path)


def test_runtime_config_cannot_supply_launcher_internal_port(tmp_path):
    config_path = tmp_path / "runtime.env"
    config_path.write_text(
        "\n".join(
            (
                "PERSONAL_OS_ENV=production",
                "PERSONAL_OS_REMOTE=1",
                "PERSONAL_OS_BIND_HOST=127.0.0.1",
                "PERSONAL_OS_TRUSTED_HOSTS=shadow.example.test",
                "PERSONAL_OS_TRUSTED_PROXY=127.0.0.1",
                f"PERSONAL_OS_PROXY_TOKEN={STRONG_PROXY_TOKEN}",
                f"SECRET_KEY={STRONG_SECRET}",
                "PSY_GUNICORN_BIND_PORT=5100",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProductionLaunchError, match="not allowed"):
        production_launcher.parse_runtime_config(config_path)


def _load_gunicorn_config(monkeypatch, port=None):
    monkeypatch.setenv("PERSONAL_OS_TRUSTED_PROXY", "127.0.0.1")
    if port is None:
        monkeypatch.delenv("PSY_GUNICORN_BIND_PORT", raising=False)
    else:
        monkeypatch.setenv("PSY_GUNICORN_BIND_PORT", str(port))
    return runpy.run_path(str(APP_ROOT / "gunicorn.conf.py"))


def test_gunicorn_consumes_launcher_port_and_preserves_forwarding_guards(monkeypatch):
    default_config = _load_gunicorn_config(monkeypatch)
    shadow_config = _load_gunicorn_config(monkeypatch, 5100)

    assert default_config["bind"] == "127.0.0.1:5000"
    assert shadow_config["bind"] == "127.0.0.1:5100"
    assert shadow_config["forwarded_allow_ips"] == "127.0.0.1"
    assert shadow_config["secure_scheme_headers"] == {
        "X-FORWARDED-PROTO": "https"
    }
    assert shadow_config["forwarder_headers"] == ""
    assert shadow_config["workers"] == 1

    safe_cfg = SimpleNamespace(
        bind=["127.0.0.1:5100"],
        workers=1,
        worker_class_str="gthread",
        threads=4,
        preload_app=True,
        reload=False,
        forwarded_allow_ips=["127.0.0.1"],
        forwarder_headers="",
        control_socket_disable=True,
    )
    shadow_config["on_starting"](SimpleNamespace(cfg=safe_cfg))
    safe_cfg.bind = ["0.0.0.0:5100"]
    with pytest.raises(RuntimeError, match="127.0.0.1:5100"):
        shadow_config["on_starting"](SimpleNamespace(cfg=safe_cfg))


@pytest.mark.parametrize(
    "forwarded_allow_ips",
    (
        ["127.0.0.1", "::1"],
        ["*"],
        ["10.0.0.1"],
        [],
    ),
)
def test_shadow_gunicorn_rejects_non_exact_forwarded_allow_ips(
    monkeypatch, forwarded_allow_ips
):
    shadow_config = _load_gunicorn_config(monkeypatch, 5100)
    cfg = SimpleNamespace(
        bind=["127.0.0.1:5100"],
        workers=1,
        worker_class_str="gthread",
        threads=4,
        preload_app=True,
        reload=False,
        forwarded_allow_ips=forwarded_allow_ips,
        forwarder_headers="",
        control_socket_disable=True,
    )
    with pytest.raises(RuntimeError, match="forwarded_allow_ips must match the trusted proxy"):
        shadow_config["on_starting"](SimpleNamespace(cfg=cfg))


@pytest.mark.parametrize("port", ("80", "65536", "not-a-port"))
def test_gunicorn_rejects_invalid_launcher_port(monkeypatch, port):
    with pytest.raises(ProductionLaunchError, match="bind port"):
        _load_gunicorn_config(monkeypatch, port)


@pytest.mark.parametrize("value", ("a", "a" * 64, "phase5a-01"))
def test_shadow_identity_allowlist_accepts_canonical_values(value):
    assert shadow_deployment.validate_shadow_identity(
        value, label="shadow identity"
    ) == value


@pytest.mark.parametrize(
    "value",
    (
        "bad/id",
        "bad id",
        "bad\nid",
        "bad;id",
        "bad*id",
        "..",
        "-leading",
        "bad$id",
        "bad{id}",
        "A-uppercase",
        "a" * 65,
    ),
)
def test_shadow_identity_allowlist_rejects_unsafe_values(value):
    with pytest.raises(ShadowDeploymentError):
        shadow_deployment.validate_shadow_identity(value, label="shadow identity")


def test_separated_shadow_requires_instance_and_release_identity(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    with pytest.raises(ProductionLaunchError, match="shadow instance id"):
        _prepare(layout, shadow_instance=None)
    with pytest.raises(ProductionLaunchError, match="shadow release id"):
        _prepare(layout, expected_release_id=None)


def test_separated_shadow_rejects_release_id_mismatch(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    with pytest.raises(ProductionLaunchError, match="approved release id"):
        _prepare(layout, expected_release_id="different-release")


def test_separated_shadow_rejects_unsafe_descriptor_release_id(
    tmp_path, monkeypatch
):
    layout = _fake_release_layout(tmp_path, monkeypatch)
    layout.release["release_id"] = "../unsafe"

    with pytest.raises(ProductionLaunchError, match="selected shadow release id"):
        _prepare(layout, expected_release_id="phase5a-test")


def test_nonseparated_launcher_keeps_existing_optional_approval_behavior(
    tmp_path, monkeypatch
):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    plan = _prepare(
        layout,
        expected_database_path=None,
        require_separated_database_artifacts=False,
        shadow_instance=None,
        expected_release_id=None,
    )

    assert plan.database_path == layout.database_path
    assert plan.separated_database_artifacts is False


def test_separated_shadow_requires_explicit_database_approval(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    with pytest.raises(
        ProductionLaunchError, match="explicitly approved database path"
    ):
        _prepare(layout, expected_database_path=None)


def test_separated_shadow_accepts_matching_exact_database(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    plan = _prepare(layout, expected_database_path=layout.database_path)

    assert plan.database_path == layout.database_path
    assert plan.runtime_environment["YD_OS_DB_PATH"] == str(layout.database_path)


def test_separated_shadow_rejects_database_mismatch(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)
    other_database = (layout.database_root / "staged" / "other.db").resolve()
    other_database.write_bytes(b"different temporary file")

    with pytest.raises(ProductionLaunchError, match="explicitly approved path"):
        _prepare(layout, expected_database_path=other_database)


def test_separated_shadow_rejects_database_outside_root(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)
    fake_formal = (tmp_path / "opt" / "psy1" / "formal.db").resolve()
    fake_formal.parent.mkdir(parents=True)
    fake_formal.write_bytes(b"not real production data")

    with pytest.raises(ProductionLaunchError, match="escapes its approved root"):
        _prepare(layout, expected_database_path=fake_formal)


def test_separated_shadow_rejects_missing_database(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    with pytest.raises(ProductionLaunchError, match="does not exist"):
        _prepare(layout, expected_database_path=layout.database_root / "missing.db")


def test_shadow_database_and_manifest_must_have_separate_parents(tmp_path):
    root = (tmp_path / "shadow-db").resolve()
    runtime_parent = root / "staged"
    manifest_parent = root / "manifests"

    production_launcher._validate_separated_database_artifacts(
        database_root=root,
        database_path=runtime_parent / "shadow.db",
        manifest_path=manifest_parent / "shadow.db.manifest.json",
    )
    with pytest.raises(ProductionLaunchError, match="dedicated writable directory"):
        production_launcher._validate_separated_database_artifacts(
            database_root=root,
            database_path=root / "shadow.db",
            manifest_path=manifest_parent / "shadow.db.manifest.json",
        )
    with pytest.raises(ProductionLaunchError, match="separate directories"):
        production_launcher._validate_separated_database_artifacts(
            database_root=root,
            database_path=runtime_parent / "shadow.db",
            manifest_path=runtime_parent / "shadow.db.manifest.json",
        )


def test_shadow_posix_permissions_separate_mutable_and_immutable_parents(
    tmp_path, monkeypatch
):
    code_root = tmp_path / "code"
    code_root.mkdir()
    inspected = []

    def fake_validate_mode(_path, *, label, forbidden_bits):
        inspected.append((label, forbidden_bits))
        service_owned = {"runtime database", "runtime database directory"}
        return SimpleNamespace(st_uid=1000 if label in service_owned else 0)

    monkeypatch.setattr(
        production_launcher,
        "os",
        SimpleNamespace(name="posix", geteuid=lambda: 1000),
    )
    monkeypatch.setattr(production_launcher, "_validate_mode", fake_validate_mode)

    production_launcher._validate_posix_permissions(
        active_pointer=tmp_path / "selectors" / "active.json",
        descriptor=tmp_path / "selectors" / "release.json",
        code_root=code_root,
        entrypoint=code_root / "production.py",
        gunicorn_config=code_root / "gunicorn.conf.py",
        config_path=tmp_path / "config" / "runtime.env",
        database_path=tmp_path / "database" / "staged" / "shadow.db",
        manifest_path=tmp_path / "database" / "manifests" / "shadow.manifest.json",
        database_root=tmp_path / "database",
        require_separated_database_artifacts=True,
    )

    labels = {label for label, _bits in inspected}
    assert "database root" in labels
    assert "database manifest directory" in labels
    assert "runtime database directory" in labels
    runtime_bits = dict(inspected)["runtime database directory"]
    assert runtime_bits == stat.S_IRWXG | stat.S_IRWXO


def test_shadow_systemd_template_isolated_and_has_runtime_access_proof():
    unit = (APP_ROOT / "deploy" / "psy-v22-shadow@.service").read_text(
        encoding="utf-8"
    )

    assert "User=psy" in unit and "Group=psy" in unit
    assert "WorkingDirectory=/etc/psy/releases/%i" in unit
    assert "EnvironmentFile=/etc/psy/releases/%i/launcher.env" in unit
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in unit
    assert (
        "ExecStartPre=/usr/bin/python3 "
        "/usr/local/libexec/psy-shadow-deployment.py validate-identity "
        '--instance "%I" --release-id "${PSY_APPROVED_RELEASE_ID}"'
    ) in unit
    assert "/usr/bin/python3" in unit
    assert (
        "/opt/psy/releases/rel-v220-shadow-${PSY_APPROVED_GIT_COMMIT}/repo/personal-system-v2/production_launcher.py"
        in unit
    )
    assert (
        "--release-root /opt/psy/releases/rel-v220-shadow-${PSY_APPROVED_GIT_COMMIT}/repo"
        in unit
    )
    assert "--venv-root /opt/psy/venvs" in unit
    assert "--expected-venv-path /opt/psy/venvs/%i-${PSY_APPROVED_GIT_COMMIT}" in unit
    assert "/var/lib/psy/releases/%i/active-release.json" in unit
    assert "/var/lib/psy/databases/%i/staged" in unit
    assert '--expected-database-path "${PSY_APPROVED_DATABASE_PATH}"' in unit
    assert '--bind-port "${PSY_APPROVED_BIND_PORT}"' in unit
    assert '--shadow-instance "%I"' in unit
    assert '--expected-release-id "${PSY_APPROVED_RELEASE_ID}"' in unit
    assert "--require-separated-database-artifacts" in unit
    assert "ConditionPathExists=/opt/psy1" in unit
    assert "InaccessiblePaths=/opt/psy1 /var/lib/psy/databases/%i/source /var/lib/psy/databases/%i/migration" in unit
    assert "ExecStartPre=/usr/bin/test ! -e /opt/psy1" in unit
    assert "ExecStartPre=/usr/bin/test ! -e /var/lib/psy/databases/%i/source" in unit
    assert "ExecStartPre=/usr/bin/test ! -e /var/lib/psy/databases/%i/migration" in unit
    assert "ExecStartPre=/usr/bin/test -f /var/lib/psy/releases/%i/active-release.json" in unit
    assert "ReadOnlyPaths=/opt/psy/releases /opt/psy/venvs /etc/psy/releases/%i /var/lib/psy/releases/%i /var/lib/psy/databases/%i/manifests" in unit
    assert "ReadWritePaths=/var/lib/psy/databases/%i/staged" in unit
    assert "Restart=on-failure" in unit
    assert "127.0.0.1:5000" not in unit and "5100" not in unit
    assert "/opt/psy1/" not in unit
    assert "/opt/psy/venv/bin" not in unit
    assert "/usr/local/libexec/psy-production-launcher.py" not in unit
    assert "/etc/psy/launcher.env" not in unit
    assert "/var/lib/psy/releases/active-release.json" not in unit
    assert "/opt/psy/releases/shadow-%i" not in unit
    assert "/opt/psy/venvs/shadow-%i" not in unit
    assert "/etc/psy/releases/shadow-%i" not in unit
    assert "/var/lib/psy/releases/shadow/%i" not in unit
    assert "/var/lib/psy/databases/shadow/%i" not in unit
    assert "shadow/%i" not in unit

    runbook = (REPO_ROOT / "docs" / "phase-5a-shadow-deployment-runbook.md").read_text(
        encoding="utf-8"
    )
    assert "nsenter --target" in runbook
    assert "setpriv --reuid=psy" in runbook
    assert "/usr/bin/test ! -e /opt/psy1" in runbook


def _valid_shadow_nginx_inputs():
    return {
        "server_name": "shadow.example.test",
        "bind_address": "172.25.103.111",
        "port": "5100",
        "certificate_path": "/etc/letsencrypt/live/shadow.example.test/fullchain.pem",
        "certificate_key_path": "/etc/letsencrypt/live/shadow.example.test/privkey.pem",
        "acme_root": "/var/lib/psy/acme/shadow",
        "proxy_auth_snippet": "/etc/nginx/snippets/psy-shadow-proxy-auth.conf",
    }


def test_shadow_nginx_renderer_validates_and_resolves_every_placeholder():
    template = (APP_ROOT / "deploy" / "nginx-psy-v22-shadow.conf.template").read_text(
        encoding="utf-8"
    )

    rendered = shadow_deployment.render_shadow_nginx(
        template, **_valid_shadow_nginx_inputs()
    )

    assert "__PSY_SHADOW_" not in rendered
    assert "server 127.0.0.1:5100;" in rendered
    assert "listen 172.25.103.111:443 ssl http2;" in rendered
    assert "server_name shadow.example.test;" in rendered
    assert (
        "include /etc/nginx/snippets/psy-shadow-proxy-auth.conf;" in rendered
    )


def test_shadow_nginx_cli_check_validates_without_writing(capsys):
    template = (APP_ROOT / "deploy" / "nginx-psy-v22-shadow.conf.template").resolve()
    values = _valid_shadow_nginx_inputs()

    result = shadow_deployment.main(
        [
            "render-nginx",
            "--instance",
            "phase5a-test",
            "--release-id",
            "phase5a-release",
            "--template",
            str(template),
            "--check",
            "--server-name",
            values["server_name"],
            "--bind-address",
            values["bind_address"],
            "--port",
            values["port"],
            "--certificate",
            values["certificate_path"],
            "--certificate-key",
            values["certificate_key_path"],
            "--acme-root",
            values["acme_root"],
            "--proxy-auth-snippet",
            values["proxy_auth_snippet"],
        ]
    )

    assert result == 0
    assert '"placeholders_remaining": false' in capsys.readouterr().out


@pytest.mark.parametrize(
    "server_name",
    (
        "localhost",
        "Shadow.example.test",
        "shadow..example.test",
        "-shadow.example.test",
        "shadow.example.test;include",
        "shadow.example.test\nserver_name evil.test",
        "shadow.example.test{}",
    ),
)
def test_shadow_nginx_renderer_rejects_invalid_fqdn(server_name):
    values = _valid_shadow_nginx_inputs()
    values["server_name"] = server_name

    with pytest.raises(ShadowDeploymentError):
        shadow_deployment.render_shadow_nginx("__PSY_SHADOW_SERVER_NAME__", **values)


@pytest.mark.parametrize(
    "bind_address", ("0.0.0.0", "172.25.103.999", "127.0.0.1;include", "::1")
)
def test_shadow_nginx_renderer_rejects_invalid_bind_address(bind_address):
    values = _valid_shadow_nginx_inputs()
    values["bind_address"] = bind_address

    with pytest.raises(ShadowDeploymentError):
        shadow_deployment.validate_shadow_nginx_inputs(**values)


@pytest.mark.parametrize("port", ("80", "65536", "5100;include", " 5100"))
def test_shadow_nginx_renderer_rejects_invalid_port(port):
    values = _valid_shadow_nginx_inputs()
    values["port"] = port

    with pytest.raises(ShadowDeploymentError):
        shadow_deployment.validate_shadow_nginx_inputs(**values)


@pytest.mark.parametrize(
    "unsafe_path",
    (
        "relative/path",
        "/etc/nginx/../shadow.conf",
        "/etc/nginx/./shadow.conf",
        "/etc/nginx/shadow config.conf",
        "/etc/nginx/shadow.conf;include",
        "/etc/nginx/shadow.conf\ninclude",
        "/etc/nginx/{shadow}.conf",
    ),
)
@pytest.mark.parametrize(
    "path_field",
    (
        "certificate_path",
        "certificate_key_path",
        "acme_root",
        "proxy_auth_snippet",
    ),
)
def test_shadow_nginx_renderer_rejects_unsafe_deployment_paths(
    unsafe_path, path_field
):
    values = _valid_shadow_nginx_inputs()
    values[path_field] = unsafe_path

    with pytest.raises(ShadowDeploymentError):
        shadow_deployment.validate_shadow_nginx_inputs(**values)


def test_shadow_nginx_renderer_rejects_placeholder_contract_drift():
    values = _valid_shadow_nginx_inputs()
    template = (
        "__PSY_SHADOW_SERVER_NAME__\n"
        "__PSY_SHADOW_UNKNOWN__\n"
    )

    with pytest.raises(ShadowDeploymentError, match="placeholder contract"):
        shadow_deployment.render_shadow_nginx(template, **values)


def test_shadow_nginx_template_has_no_wildcard_or_production_binding():
    nginx = (APP_ROOT / "deploy" / "nginx-psy-v22-shadow.conf.template").read_text(
        encoding="utf-8"
    )

    assert "upstream psy_v22_shadow" in nginx
    assert "server 127.0.0.1:__PSY_SHADOW_PORT__;" in nginx
    assert nginx.count("listen __PSY_SHADOW_BIND_ADDRESS__:") == 2
    assert nginx.count("server_name __PSY_SHADOW_SERVER_NAME__;") == 2
    assert "default_server" not in nginx
    assert "listen 80" not in nginx and "listen 443" not in nginx
    assert "listen [::]" not in nginx and "0.0.0.0" not in nginx
    assert "172.25.103.111" not in nginx and "8.137.186.60" not in nginx
    assert "proxy_pass http://psy_v22_shadow;" in nginx
    assert "proxy_set_header Host __PSY_SHADOW_SERVER_NAME__;" in nginx
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "proxy_set_header X-Forwarded-Proto https;" in nginx
    assert "proxy_set_header X-Forwarded-Host __PSY_SHADOW_SERVER_NAME__;" in nginx
    assert "$proxy_add_x_forwarded_for" not in nginx
    assert "ssl_certificate __PSY_SHADOW_CERTIFICATE_PATH__;" in nginx
    assert "ssl_certificate_key __PSY_SHADOW_CERTIFICATE_KEY_PATH__;" in nginx
    assert "return 308 https://__PSY_SHADOW_SERVER_NAME__$request_uri;" in nginx
    assert "include __PSY_SHADOW_PROXY_AUTH_SNIPPET__;" in nginx


def test_shadow_examples_are_distinct_and_have_no_committed_secret():
    deploy = APP_ROOT / "deploy"
    launcher = (deploy / "shadow-launcher.env.example").read_text(encoding="utf-8")
    runtime = (deploy / "shadow-runtime.env.example").read_text(encoding="utf-8")
    proxy = (deploy / "nginx-psy-v22-shadow-proxy-auth.conf.example").read_text(
        encoding="utf-8"
    )

    assert "PSY_APPROVED_APP_VERSION=v2.2.0-shadow" in launcher
    assert "PSY_APPROVED_RELEASE_ID=replace_with_" in launcher
    assert "PSY_APPROVED_BIND_PORT=5100" in launcher
    assert (
        "PSY_APPROVED_DATABASE_PATH=/var/lib/psy/databases/replace_instance/staged/yd_os-v22-shadow.db"
        in launcher
    )
    assert "/var/lib/psy/databases/shadow/" not in launcher
    assert "YD_OS_DB_PATH" not in launcher
    assert "PERSONAL_OS_BIND_HOST=127.0.0.1" in runtime
    assert "YD_OS_DB_PATH" not in runtime
    assert "replace_with" in runtime and STRONG_SECRET not in runtime
    assert "X-PSY-Proxy-Token" in proxy and STRONG_PROXY_TOKEN not in proxy


def test_build_identity_combines_version_and_release_id(
    unauthenticated_client, monkeypatch
):
    monkeypatch.setenv("PSY_RELEASE_ID", "phase5a-local-browser")

    assert changelog.get_current_version() == "v2.2.1"
    assert changelog.get_build_identity() == (
        "v2.2.1 · phase5a-local-browser"
    )
    assert changelog.get_build_identity(
        {
            "PSY_EXPECTED_APP_VERSION": "v2.2.0-shadow",
            "PSY_RELEASE_ID": "phase5a-approved-release",
        }
    ) == "v2.2.0-shadow · phase5a-approved-release"
    response = unauthenticated_client.get("/login")
    assert response.status_code == 200
    login_markup = response.get_data(as_text=True)
    assert 'class="auth-build-identity"' not in login_markup
    assert "phase5a-local-browser" not in login_markup


def test_service_worker_never_caches_documents_api_or_login_state():
    worker = (APP_ROOT / "static" / "service-worker.js").read_text(encoding="utf-8")
    assert 'request.mode === "navigate"' in worker
    assert 'request.destination === "document"' in worker
    assert 'url.pathname.startsWith("/api/")' in worker
    assert '"/login"' not in worker
    assert '"/logout"' not in worker


def test_runbook_has_all_21_shadow_steps_and_stops_before_phase_5b():
    runbook = (REPO_ROOT / "docs" / "phase-5a-shadow-deployment-runbook.md").read_text(
        encoding="utf-8"
    )

    for step in range(1, 22):
        assert f"### {step}." in runbook
    assert "本文不授权从正式数据库复制" in runbook
    assert "source copy (immutable)" in runbook
    assert "Phase 5B 不在本文范围内" in runbook
    assert "systemctl enable" not in runbook
    assert "personal-system-v2/data/yd_os.db" in runbook
    assert "^[a-z0-9][a-z0-9-]{0,63}$" in runbook
    assert "validate-identity" in runbook
    assert '--instance "${INSTANCE}"' in runbook
    assert "render-nginx" in runbook
    assert "nginx -t" in runbook
    assert "$INSTANCE" not in runbook
    assert "$RELEASE_ID" not in runbook


def test_requirements_lock_file_integrity_and_security():
    lock_file = APP_ROOT / "requirements.lock"
    assert lock_file.is_file(), "requirements.lock must exist"

    raw = lock_file.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "requirements.lock must not contain UTF-8 BOM"
    assert b"\r" not in raw, "requirements.lock must use pure LF line endings"
    assert raw.endswith(b"\n"), "requirements.lock must end with a newline"

    content = raw.decode("utf-8")
    lines = content.splitlines()

    # 1. Check prohibited patterns
    forbidden_patterns = [
        "/tmp/", "psy-lock-scratch", "file:", "git+", "--editable", "http://", "@",
        "C:", "D:", "E:", "F:"
    ]
    for pattern in forbidden_patterns:
        for idx, line in enumerate(lines, 1):
            assert pattern not in line, f"Found forbidden pattern '{pattern}' at line {idx}: {line}"

    # 2. Check packages, exact == pinning, and hashes
    import re
    packages = {}
    current_pkg = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pkg_match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:==|===|@|<=|>=|<|>|~=)(.*)$", stripped)
        if pkg_match and not stripped.startswith("--"):
            current_pkg = pkg_match.group(1).lower()
            req_str = stripped.rstrip(" \\")
            packages[current_pkg] = {"req": req_str, "hashes": []}
            assert "==" in req_str, f"Package {current_pkg} is not pinned with exact ==: {req_str}"
            assert not any(op in req_str for op in (">", "<", "~=")), f"Package {current_pkg} contains loose operator: {req_str}"
        elif stripped.startswith("--hash=") and current_pkg:
            packages[current_pkg]["hashes"].append(stripped)

    assert len(packages) >= 30, f"Expected full transitive dependencies locked, found {len(packages)}"
    for pkg_name, pkg_data in packages.items():
        assert len(pkg_data["hashes"]) > 0, f"Package {pkg_name} must contain at least one --hash"

    # 3. Check Linux gunicorn
    assert "gunicorn" in packages, "requirements.lock must contain gunicorn"
    gunicorn_req = packages["gunicorn"]["req"]
    assert "gunicorn==" in gunicorn_req
    assert 'sys_platform != "win32"' in gunicorn_req or "win32" in gunicorn_req


def test_runbook_step_4_specifies_lockfile_with_hashes_and_no_nodeps():
    runbook = (REPO_ROOT / "docs" / "phase-5a-shadow-deployment-runbook.md").read_text(
        encoding="utf-8"
    )
    # Extract Step 4 section
    assert "### 4. 创建独立 venv" in runbook
    step_4_start = runbook.find("### 4. 创建独立 venv")
    step_5_start = runbook.find("### 5. 安装 shadow runtime.env")
    assert step_4_start != -1 and step_5_start != -1
    step_4_text = runbook[step_4_start:step_5_start]

    assert "requirements.lock" in step_4_text
    assert "--require-hashes" in step_4_text
    assert "--no-deps" not in step_4_text or "不得使用 `--no-deps`" in step_4_text
    assert "-m pip check" in step_4_text
    assert "-m gunicorn --version" in step_4_text
    assert "group/world writable" in step_4_text
    assert "Ubuntu 22.04" in step_4_text
    assert "pip-tools 7.6.1" in step_4_text


def test_gitattributes_enforces_lf_and_release_bundle_exclusions():
    # 1. Verify text content of .gitattributes (checked in ALL environments)
    gitattributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in gitattributes
    assert "personal-system-v2/requirements.txt text eol=lf" in gitattributes
    assert "personal-system-v2/requirements.lock text eol=lf" in gitattributes
    assert "personal-system-v2/data export-ignore" in gitattributes
    assert "personal-system-v2/data/** export-ignore" in gitattributes

    # 2. If in a Git repository, verify export-ignore attribute semantics are set using git check-attr
    is_git_repo = (REPO_ROOT / ".git").exists()
    if is_git_repo:
        import subprocess
        cmd = ["git", "check-attr", "export-ignore", "personal-system-v2/data", "personal-system-v2/data/.gitkeep"]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=True)
        lines = proc.stdout.strip().splitlines()
        assert len(lines) == 2, f"Expected 2 lines from git check-attr, got {lines}"
        assert "personal-system-v2/data: export-ignore: set" in lines[0]
        assert "personal-system-v2/data/.gitkeep: export-ignore: set" in lines[1]


def is_forbidden_env_file(path_or_name: str) -> bool:
    """
    Detect whether a filename or path represents a forbidden environment file in release bundles.
    Forbidden:
      - .env, .env.production, .env.local, .env.*
      - runtime.env, launcher.env, production.env, *.env
      - config/runtime.env.backup, *.env.*
    Allowed:
      - Explicit example templates ending in .example (.env.example, runtime.env.example, etc.)
      - Normal code/doc files like environment.py, envelope.json
    """
    basename = Path(path_or_name).name
    if basename.endswith(".example"):
        return False
    if basename == ".env":
        return True
    if basename.startswith(".env."):
        return True
    if basename.endswith(".env"):
        return True
    if ".env." in basename:
        return True
    return False


def test_forbidden_env_file_detection_synthetic_cases():
    """Verify is_forbidden_env_file correctly classifies forbidden vs allowed env files."""
    must_be_forbidden = [
        ".env",
        ".env.production",
        "runtime.env",
        "launcher.env",
        "production.env",
        "config/runtime.env.backup",
        "deploy/runtime.env",
        ".env.local",
        "sub/dir/secret.env",
        "custom.env.old",
        "personal-system-v2/deploy/launcher.env",
        "personal-system-v2/deploy/runtime.env",
    ]
    for path in must_be_forbidden:
        assert is_forbidden_env_file(path) is True, f"Expected {path} to be classified as forbidden env file"

    must_be_allowed = [
        ".env.example",
        "runtime.env.example",
        "launcher.env.example",
        "deploy/runtime.env.example",
        "deploy/shadow-runtime.env.example",
        "deploy/launcher.env.example",
        "deploy/shadow-launcher.env.example",
        "personal-system-v2/deploy/shadow-launcher.env.example",
        "environment.py",
        "envelope.json",
        "main.css",
        "test_auth.py",
    ]
    for path in must_be_allowed:
        assert is_forbidden_env_file(path) is False, f"Expected {path} to be classified as allowed file"


def test_git_archive_release_bundle_strictly_excludes_forbidden_items():
    """
    Dual-mode validation of release bundle exclusion safety:
    Mode 1 (Git Repository Workspace, .git exists):
      - Uses git archive --worktree-attributes --format=tar HEAD to stream in-memory archive
      - Hard asserts exclusion of data, cache, venv, .git, real .env, special types.
    Mode 2 (Non-Git Release Tree, .git does NOT exist):
      - Verifies PYTHONDONTWRITEBYTECODE is set to prevent test pollution
      - Directly traverses physical release directory tree (followlinks=False)
      - Hard asserts exclusion of data, cache, venv, .git, real .env, special types.
    """
    is_git_repo = (REPO_ROOT / ".git").exists()
    forbidden_cache_segments = {"cache", "__pycache__", ".pytest_cache", ".mypy_cache"}
    forbidden_venv_segments = {"venv", ".venv"}

    if is_git_repo:
        import io
        import subprocess
        import tarfile

        cmd = ["git", "archive", "--worktree-attributes", "--format=tar", "HEAD"]
        proc = subprocess.run(cmd, capture_output=True, cwd=REPO_ROOT, check=True)

        with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tar:
            members = tar.getmembers()
            assert len(members) > 0, "Archive must contain members"

            # 1. Hard assertion: personal-system-v2/data directory and any members under data
            data_members = [
                m.name for m in members
                if m.name == "personal-system-v2/data"
                or m.name.startswith("personal-system-v2/data/")
                or any(seg == "data" for seg in m.name.split("/"))
            ]
            assert len(data_members) == 0, f"Archive contains forbidden data members: {data_members}"

            # 2. Hard assertion: cache path segments by full segment
            cache_members = [
                m.name for m in members
                if any(seg in forbidden_cache_segments for seg in m.name.split("/"))
            ]
            assert len(cache_members) == 0, f"Archive contains forbidden cache members: {cache_members}"

            # 3. Hard assertion: venv path segments by full segment
            venv_members = [
                m.name for m in members
                if any(seg in forbidden_venv_segments for seg in m.name.split("/"))
            ]
            assert len(venv_members) == 0, f"Archive contains forbidden venv members: {venv_members}"

            # 4. Hard assertion: .git repository directory
            git_members = [
                m.name for m in members
                if m.name == ".git" or m.name.startswith(".git/") or any(seg == ".git" for seg in m.name.split("/"))
            ]
            assert len(git_members) == 0, f"Archive contains forbidden .git members: {git_members}"

            # 5. Hard assertion: Real .env files (using unified is_forbidden_env_file helper)
            env_files = [
                m.name for m in members
                if is_forbidden_env_file(m.name)
            ]
            assert len(env_files) == 0, f"Archive contains forbidden .env files: {env_files}"

            # 6. Hard assertion: All members must be regular files (REGTYPE) or directories (DIRTYPE)
            invalid_type_members = [
                f"type={m.type}:{m.name}" for m in members
                if m.type not in (tarfile.REGTYPE, tarfile.DIRTYPE)
            ]
            assert len(invalid_type_members) == 0, f"Archive contains non-regular/non-dir members: {invalid_type_members}"
    else:
        # Non-Git Release Tree Mode
        # Guard: Check PYTHONDONTWRITEBYTECODE / dont_write_bytecode
        assert sys.dont_write_bytecode or os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", (
            "In non-git release tree, PYTHONDONTWRITEBYTECODE=1 must be set to prevent bytecode pollution"
        )

        # 1. Hard assertion: personal-system-v2/data directory must not exist
        data_dir = REPO_ROOT / "personal-system-v2" / "data"
        assert not data_dir.exists(), f"Forbidden data directory exists in release tree: {data_dir}"

        # 2. Direct physical traversal without following symlinks
        found_data_items = []
        found_cache_items = []
        found_venv_items = []
        found_git_items = []
        found_env_items = []
        found_special_items = []

        for root, dirs, files in os.walk(REPO_ROOT, followlinks=False):
            root_path = Path(root)
            rel_root = root_path.relative_to(REPO_ROOT).as_posix()
            parts = rel_root.split("/") if rel_root != "." else []

            # Check root directory segments
            if any(p in forbidden_cache_segments for p in parts):
                found_cache_items.append(rel_root)
            if any(p in forbidden_venv_segments for p in parts):
                found_venv_items.append(rel_root)
            if any(p == ".git" for p in parts):
                found_git_items.append(rel_root)
            if "personal-system-v2" in parts and "data" in parts:
                found_data_items.append(rel_root)

            # Check directory items in dirs (symlinks, junctions, abnormal dir types)
            for d in list(dirs):
                d_path = root_path / d
                d_rel = (root_path.relative_to(REPO_ROOT) / d).as_posix()
                d_parts = parts + [d]

                if "personal-system-v2" in d_parts and "data" in d_parts:
                    found_data_items.append(d_rel)
                if any(p in forbidden_cache_segments for p in d_parts):
                    found_cache_items.append(d_rel)
                if any(p in forbidden_venv_segments for p in d_parts):
                    found_venv_items.append(d_rel)
                if any(p == ".git" for p in d_parts):
                    found_git_items.append(d_rel)

                is_dir_symlink = d_path.is_symlink()
                is_dir_junction = getattr(d_path, "is_junction", lambda: False)() or (
                    hasattr(os.path, "isjunction") and os.path.isjunction(d_path)
                )
                if is_dir_symlink or is_dir_junction or not d_path.is_dir():
                    found_special_items.append(d_rel)

            # Check file items in files (symlinks, non-regular files, forbidden env)
            for f in files:
                f_path = root_path / f
                f_rel = (root_path.relative_to(REPO_ROOT) / f).as_posix()
                f_parts = parts + [f]

                if "personal-system-v2" in f_parts and "data" in f_parts:
                    found_data_items.append(f_rel)
                if any(p in forbidden_cache_segments for p in f_parts):
                    found_cache_items.append(f_rel)
                if any(p in forbidden_venv_segments for p in f_parts):
                    found_venv_items.append(f_rel)
                if any(p == ".git" for p in f_parts):
                    found_git_items.append(f_rel)
                if is_forbidden_env_file(f):
                    found_env_items.append(f_rel)

                is_file_symlink = f_path.is_symlink()
                is_file_junction = getattr(f_path, "is_junction", lambda: False)() or (
                    hasattr(os.path, "isjunction") and os.path.isjunction(f_path)
                )
                if is_file_symlink or is_file_junction or not f_path.is_file():
                    found_special_items.append(f_rel)

        assert len(found_data_items) == 0, f"Found forbidden data items in release tree: {found_data_items}"
        assert len(found_cache_items) == 0, f"Found forbidden cache items in release tree: {found_cache_items}"
        assert len(found_venv_items) == 0, f"Found forbidden venv items in release tree: {found_venv_items}"
        assert len(found_git_items) == 0, f"Found forbidden .git items in release tree: {found_git_items}"
        assert len(found_env_items) == 0, f"Found forbidden env files in release tree: {found_env_items}"
        assert len(found_special_items) == 0, f"Found forbidden special items in release tree: {found_special_items}"


def test_shadow_launcher_requires_venv_root_and_expected_venv_path(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)

    with pytest.raises(ProductionLaunchError, match="--venv-root and --expected-venv-path"):
        _prepare(layout, venv_root=None)
    with pytest.raises(ProductionLaunchError, match="--venv-root and --expected-venv-path"):
        _prepare(layout, expected_venv_path=None)


def test_shadow_launcher_rejects_venv_outside_root(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)
    escaped_venv = (tmp_path / "other-venvs" / f"phase5a-test-{GIT_COMMIT}").resolve()
    escaped_venv.parent.mkdir(parents=True)
    escaped_venv.mkdir()
    bin_dir = escaped_venv / ("Scripts" if os.name == "nt" else "bin")
    bin_dir.mkdir()
    (bin_dir / ("python.exe" if os.name == "nt" else "python")).write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(ProductionLaunchError, match="escapes its approved root"):
        _prepare(layout, expected_venv_path=escaped_venv)


def test_shadow_launcher_rejects_venv_commit_or_instance_mismatch(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)
    mismatched_venv = (layout.venv_root / f"phase5a-test-{'0'*40}").resolve()
    mismatched_venv.mkdir()
    bin_dir = mismatched_venv / ("Scripts" if os.name == "nt" else "bin")
    bin_dir.mkdir()
    (bin_dir / ("python.exe" if os.name == "nt" else "python")).write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(ProductionLaunchError, match="instance and git commit"):
        _prepare(layout, expected_venv_path=mismatched_venv)


def test_shadow_launcher_rejects_missing_or_non_regular_venv_python(tmp_path, monkeypatch):
    layout = _fake_release_layout(tmp_path, monkeypatch)
    layout.venv_python.unlink()

    with pytest.raises(ProductionLaunchError, match="venv python executable must exist"):
        _prepare(layout)


def test_shadow_launcher_posix_permissions_validate_venv_tree(tmp_path, monkeypatch):
    code_root = tmp_path / "code"
    code_root.mkdir()
    inspected = []

    def fake_validate_mode(_path, *, label, forbidden_bits):
        inspected.append((label, forbidden_bits))
        service_owned = {"runtime database", "runtime database directory"}
        return SimpleNamespace(st_uid=1000 if label in service_owned else 0)

    monkeypatch.setattr(
        production_launcher,
        "os",
        SimpleNamespace(name="posix", geteuid=lambda: 1000),
    )
    monkeypatch.setattr(production_launcher, "_validate_mode", fake_validate_mode)

    venv_dir = tmp_path / "venvs" / f"shadow-01-{GIT_COMMIT}"
    venv_dir.mkdir(parents=True)
    venv_bin = venv_dir / "bin"
    venv_bin.mkdir()
    venv_py = venv_bin / "python"
    venv_py.write_text("#!/bin/sh\n")

    production_launcher._validate_posix_permissions(
        active_pointer=tmp_path / "selectors" / "active.json",
        descriptor=tmp_path / "selectors" / "release.json",
        code_root=code_root,
        entrypoint=code_root / "production.py",
        gunicorn_config=code_root / "gunicorn.conf.py",
        config_path=tmp_path / "config" / "runtime.env",
        database_path=tmp_path / "database" / "staged" / "shadow.db",
        manifest_path=tmp_path / "database" / "manifests" / "shadow.manifest.json",
        database_root=tmp_path / "database",
        require_separated_database_artifacts=True,
        venv_root=tmp_path / "venvs",
        venv_path=venv_dir,
        python_executable=venv_py,
    )

    labels = {label for label, _bits in inspected}
    assert "venv root" in labels
    assert "expected venv directory" in labels
    assert "venv python executable" in labels


def test_contract_regression_static_guards():
    service_text = (APP_ROOT / "deploy" / "psy-v22-shadow@.service").read_text(encoding="utf-8")
    runbook_text = (REPO_ROOT / "docs" / "phase-5a-shadow-deployment-runbook.md").read_text(encoding="utf-8")
    cutover_runbook_text = (REPO_ROOT / "docs" / "phase-5-database-cutover-runbook.md").read_text(encoding="utf-8")
    launcher_env_example = (APP_ROOT / "deploy" / "shadow-launcher.env.example").read_text(encoding="utf-8")
    release_text = (REPO_ROOT / "docs" / "standards" / "RELEASE.md").read_text(encoding="utf-8")

    # Prohibited legacy patterns
    for text, doc_name in (
        (service_text, "psy-v22-shadow@.service"),
        (runbook_text, "phase-5a-shadow-deployment-runbook.md"),
        (cutover_runbook_text, "phase-5-database-cutover-runbook.md"),
        (launcher_env_example, "shadow-launcher.env.example"),
        (release_text, "RELEASE.md"),
    ):
        assert "/usr/local/libexec/psy-production-launcher.py" not in text, f"Found legacy launcher path in {doc_name}"
        assert "shadow-shadow-" not in text, f"Found shadow-shadow- in {doc_name}"
        assert "/var/lib/psy/databases/shadow/" not in text, f"Found legacy database shadow root in {doc_name}"
        assert "SHORT_COMMIT" not in text, f"Found SHORT_COMMIT in {doc_name}"
        assert "{incoming,verified}" not in text, f"Found ambiguous brace expansion in {doc_name}"

    # Prohibited unflagged mv in promotion contexts
    assert 'mv -n "${SRC}" "${DEST}"' not in runbook_text
    assert 'mv -n "${STAGING_ROOT}" "${TARGET_ROOT}"' not in runbook_text

    # Mandatory canonical patterns
    assert "mv -T -n" in runbook_text
    assert "/usr/bin/python3" in service_text
    assert "rel-v220-shadow-${PSY_APPROVED_GIT_COMMIT}" in service_text
    assert "--venv-root" in service_text
    assert "--expected-venv-path" in service_text
    assert "rel-v220-shadow-${GIT_COMMIT}" in runbook_text


def test_artifact_namespace_contract_hierarchy_and_permissions():
    """Regression test ensuring authoritative artifact namespace hierarchy and permissions.

    Verifies exact path + owner + group + mode structure without relying solely on keyword presence.
    """
    runbook_path = REPO_ROOT / "docs" / "phase-5a-shadow-deployment-runbook.md"
    release_path = REPO_ROOT / "docs" / "standards" / "RELEASE.md"

    runbook_text = runbook_path.read_text(encoding="utf-8")
    release_text = release_path.read_text(encoding="utf-8")

    expected_hierarchy = [
        {
            "role": "shared namespace root",
            "path": "/var/lib/psy/artifacts",
            "owner": "root",
            "group": "root",
            "mode": "0755",
        },
        {
            "role": "instance boundary",
            "path": "/var/lib/psy/artifacts/${INSTANCE}",
            "owner": "root",
            "group": "root",
            "mode": "0750",
        },
        {
            "role": "leaf operational directory (incoming)",
            "path": "/var/lib/psy/artifacts/${INSTANCE}/incoming",
            "owner": "root",
            "group": "root",
            "mode": "0750",
        },
        {
            "role": "leaf operational directory (verified)",
            "path": "/var/lib/psy/artifacts/${INSTANCE}/verified",
            "owner": "root",
            "group": "root",
            "mode": "0750",
        },
    ]

    # 1. Parse markdown table rows in phase-5a-shadow-deployment-runbook.md
    # Canonical Path Mapping table format: | 资源 | Shadow 路径/名称 | 权限真源 |
    table_rows = {}
    for line in runbook_text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("|") and trimmed.endswith("|"):
            cells = [c.strip() for c in trimmed.split("|")[1:-1]]
            if len(cells) >= 3:
                resource_name, path_cell, perm_cell = cells[0], cells[1], cells[2]
                raw_path = path_cell.strip("`")
                perm_match = re.search(r"([a-z0-9_]+):([a-z0-9_]+)\s+([0-7]{4})", perm_cell)
                if perm_match:
                    owner, group, mode = perm_match.groups()
                    table_rows[raw_path] = {
                        "resource": resource_name,
                        "owner": owner,
                        "group": group,
                        "mode": mode,
                    }

    # Verify each expected hierarchy item in runbook table
    for item in expected_hierarchy:
        path = item["path"]
        assert path in table_rows, f"Path {path} not found in runbook canonical path mapping table"
        actual = table_rows[path]
        assert actual["owner"] == item["owner"], f"{path} owner expected {item['owner']}, got {actual['owner']}"
        assert actual["group"] == item["group"], f"{path} group expected {item['group']}, got {actual['group']}"
        assert actual["mode"] == item["mode"], f"{path} mode expected {item['mode']}, got {actual['mode']}"

    # Verify ambiguous shorthand is completely absent
    assert "{incoming,verified}" not in runbook_text
    assert "{incoming,verified}" not in release_text

    # 2. Verify explicit hierarchy distinction and permission contract in RELEASE.md
    assert "shared namespace root" in release_text
    assert "instance boundary" in release_text
    assert "leaf operational directories" in release_text

    for item in expected_hierarchy:
        path = item["path"]
        owner = item["owner"]
        group = item["group"]
        mode = item["mode"]
        # Match pattern: path ... 必须为 `owner:group` + `mode`
        pattern = rf"{re.escape(path)}[^\n]*?必须为\s*`{owner}:{group}`\s*\+\s*`{mode}`"
        match = re.search(pattern, release_text)
        assert match is not None, f"Contract for {path} ({owner}:{group} {mode}) not found in RELEASE.md"
