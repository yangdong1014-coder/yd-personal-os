import os
import shutil
from pathlib import Path

import config


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["status"] == "up"
    assert "version" in payload["data"]


def test_local_access_without_token_when_remote_off(client, monkeypatch):
    monkeypatch.delenv("PERSONAL_OS_REMOTE", raising=False)
    monkeypatch.setattr(config, "is_remote_mode", lambda: False)
    response = client.get("/")
    assert response.status_code == 200


def test_remote_mode_forbidden_without_token(client, monkeypatch):
    monkeypatch.setattr(config, "is_remote_mode", lambda: True)
    monkeypatch.setattr(config, "get_access_token", lambda: "test-secret-token")
    response = client.get(
        "/api/goals",
        environ_overrides={"REMOTE_ADDR": "100.64.0.1"},
    )
    assert response.status_code == 403
    assert "令牌" in response.get_json()["error"]


def test_remote_mode_page_with_valid_token(client, monkeypatch):
    monkeypatch.setattr(config, "is_remote_mode", lambda: True)
    monkeypatch.setattr(config, "get_access_token", lambda: "test-secret-token")
    response = client.get(
        "/?token=test-secret-token",
        environ_overrides={"REMOTE_ADDR": "100.64.0.1"},
    )
    assert response.status_code == 200


def test_remote_mode_api_with_header_token(client, monkeypatch):
    monkeypatch.setattr(config, "is_remote_mode", lambda: True)
    monkeypatch.setattr(config, "get_access_token", lambda: "test-secret-token")
    response = client.get(
        "/api/goals",
        headers={"X-Personal-OS-Token": "test-secret-token"},
        environ_overrides={"REMOTE_ADDR": "100.64.0.1"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_local_remote_mode_no_token_required(client, monkeypatch):
    monkeypatch.setattr(config, "is_remote_mode", lambda: True)
    monkeypatch.setattr(config, "get_access_token", lambda: "test-secret-token")
    response = client.get(
        "/api/goals",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert response.status_code == 200


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