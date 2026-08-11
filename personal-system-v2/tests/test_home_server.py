from pathlib import Path

import pytest

import auth_service
import config
from conftest import extract_csrf_token


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["status"] == "up"
    assert "version" in payload["data"]


def test_authenticated_local_access_when_remote_off(client, monkeypatch):
    monkeypatch.delenv("PERSONAL_OS_REMOTE", raising=False)
    response = client.get("/")
    assert response.status_code == 200


def test_remote_request_without_session_returns_401(unauthenticated_client):
    response = unauthenticated_client.get(
        "/api/goals",
        environ_overrides={"REMOTE_ADDR": "100.64.0.1"},
    )
    assert response.status_code == 401
    assert response.get_json()["code"] == "authentication_required"


def test_remote_request_with_authenticated_session_is_allowed(test_app):
    password = "remote admin password"
    auth_service.bootstrap_admin("remoteadmin", "remote@example.com", password)
    remote_client = test_app.test_client()
    remote_address = {"REMOTE_ADDR": "100.64.0.1"}
    login_page = remote_client.get("/login", environ_overrides=remote_address)
    csrf_token = extract_csrf_token(login_page)
    login_response = remote_client.post(
        "/login",
        data={
            "identifier": "remoteadmin",
            "password": password,
            "csrf_token": csrf_token,
        },
        environ_overrides=remote_address,
    )
    assert login_response.status_code == 302

    response = remote_client.get(
        "/api/goals",
        environ_overrides=remote_address,
    )
    assert response.status_code == 200


def test_legacy_query_token_cannot_bypass_login(unauthenticated_client):
    response = unauthenticated_client.get("/api/goals?token=legacy-shared-token")
    assert response.status_code == 401


def test_service_worker_is_public(unauthenticated_client):
    response = unauthenticated_client.get(
        "/service-worker.js",
        environ_overrides={"REMOTE_ADDR": "100.64.0.1"},
    )
    assert response.status_code == 200
    assert response.content_type.startswith("application/javascript")


def test_local_request_without_session_also_requires_login(unauthenticated_client):
    response = unauthenticated_client.get(
        "/api/goals",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert response.status_code == 401


def test_remote_mode_requires_persistent_secret_key(monkeypatch):
    monkeypatch.setenv("PERSONAL_OS_REMOTE", "1")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(SystemExit, match="SECRET_KEY"):
        config.validate_server_config()

    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    config.validate_server_config()


def test_backup_db_does_not_modify_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_dir = tmp_path / "personal-system-v2"
    data_dir = app_dir / "data"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "yd_os.db"
    db_path.write_bytes(b"sqlite-test-content-v1")

    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "backup-db.py"
    spec = importlib.util.spec_from_file_location("backup_db", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "APP_DIR", app_dir)
    monkeypatch.setattr(module, "DB_PATH", db_path)
    monkeypatch.setattr(module, "BACKUP_DIR", app_dir / "backups")

    before = db_path.read_bytes()
    dest = module.backup_database(keep=5)
    after = db_path.read_bytes()

    assert before == after
    assert dest.is_file()
    assert dest.read_bytes() == before


def test_backups_gitignored():
    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    assert "backups/" in content
