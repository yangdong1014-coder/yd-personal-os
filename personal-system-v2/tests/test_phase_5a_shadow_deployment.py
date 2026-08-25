import os
import runpy
import stat
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
    for directory in (
        descriptor_root,
        code_root,
        config_root,
        runtime_parent,
        manifest_parent,
    ):
        directory.mkdir(parents=True, exist_ok=False)

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
        release=resolved_release,
    )


def _prepare(layout, **overrides):
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
        forwarded_allow_ips="127.0.0.1",
        forwarder_headers="",
        control_socket_disable=True,
    )
    shadow_config["on_starting"](SimpleNamespace(cfg=safe_cfg))
    safe_cfg.bind = ["0.0.0.0:5100"]
    with pytest.raises(RuntimeError, match="127.0.0.1:5100"):
        shadow_config["on_starting"](SimpleNamespace(cfg=safe_cfg))


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
    assert "WorkingDirectory=/opt/psy/releases/shadow-%i/repo" in unit
    assert "EnvironmentFile=/etc/psy/releases/shadow-%i/launcher.env" in unit
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in unit
    assert (
        "ExecStartPre=/usr/bin/python3 "
        "/usr/local/libexec/psy-shadow-deployment.py validate-identity "
        '--instance "%I" --release-id "${PSY_APPROVED_RELEASE_ID}"'
    ) in unit
    assert "/opt/psy/venvs/shadow-%i/" in unit
    assert "/opt/psy/releases/shadow-%i/repo/personal-system-v2/production_launcher.py" in unit
    assert "--release-root /opt/psy/releases/shadow-%i/repo" in unit
    assert "/var/lib/psy/releases/shadow/%i/active-release.json" in unit
    assert "/var/lib/psy/databases/shadow/%i/staged" in unit
    assert '--expected-database-path "${PSY_APPROVED_DATABASE_PATH}"' in unit
    assert '--bind-port "${PSY_APPROVED_BIND_PORT}"' in unit
    assert '--shadow-instance "%I"' in unit
    assert '--expected-release-id "${PSY_APPROVED_RELEASE_ID}"' in unit
    assert "--require-separated-database-artifacts" in unit
    assert "ConditionPathExists=/opt/psy1" in unit
    assert "InaccessiblePaths=/opt/psy1" in unit
    assert "ExecStartPre=/usr/bin/test ! -e /opt/psy1" in unit
    assert "ReadWritePaths=/var/lib/psy/databases/shadow/%i/staged" in unit
    assert "Restart=on-failure" in unit
    assert "127.0.0.1:5000" not in unit and "5100" not in unit
    assert "/opt/psy1/" not in unit
    assert "/opt/psy/venv/bin" not in unit
    assert "/etc/psy/launcher.env" not in unit
    assert "/var/lib/psy/releases/active-release.json" not in unit

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
    assert "PSY_APPROVED_DATABASE_PATH=/var/lib/psy/databases/shadow/" in launcher
    assert "YD_OS_DB_PATH" not in launcher
    assert "PERSONAL_OS_BIND_HOST=127.0.0.1" in runtime
    assert "YD_OS_DB_PATH" not in runtime
    assert "replace_with" in runtime and STRONG_SECRET not in runtime
    assert "X-PSY-Proxy-Token" in proxy and STRONG_PROXY_TOKEN not in proxy


def test_candidate_build_identity_combines_version_and_release_id(
    unauthenticated_client, monkeypatch
):
    monkeypatch.setenv("PSY_RELEASE_ID", "phase5a-local-browser")

    assert changelog.get_current_version() == "v2.2.0-shadow"
    assert changelog.get_build_identity() == (
        "v2.2.0-shadow · phase5a-local-browser"
    )
    assert changelog.get_build_identity(
        {
            "PSY_EXPECTED_APP_VERSION": "v2.2.0-shadow",
            "PSY_RELEASE_ID": "phase5a-approved-release",
        }
    ) == "v2.2.0-shadow · phase5a-approved-release"
    response = unauthenticated_client.get("/login")
    assert response.status_code == 200
    assert "v2.2.0-shadow · phase5a-local-browser" in response.get_data(
        as_text=True
    )


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


def test_gitattributes_enforces_lf_for_requirements():
    gitattributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "personal-system-v2/requirements.txt text eol=lf" in gitattributes
    assert "personal-system-v2/requirements.lock text eol=lf" in gitattributes
