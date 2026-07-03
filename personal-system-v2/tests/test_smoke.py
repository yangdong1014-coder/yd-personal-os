import json
from pathlib import Path

import database


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _empty_backup():
    return {
        "meta": {
            "exported_at": "2026-01-01 00:00:00",
            "version": "1.0",
            "tables": list(database.IMPORT_TABLES),
        },
        "goals": [],
        "projects": [],
        "tasks": [],
        "reviews": [],
        "assets": [],
        "capability_entries": [],
    }


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_base_template_has_pwa_metadata(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert "/static/manifest.json" in html
    assert 'name="theme-color"' in html
    assert 'name="apple-mobile-web-app-capable"' in html
    assert 'name="apple-mobile-web-app-title"' in html


def test_base_template_has_compact_theme_toggle(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="theme-toggle-btn"' in html
    assert 'class="nav-export-btn theme-toggle"' in html
    assert 'class="nav-export-icon theme-toggle-icon theme-toggle__icon"' in html
    assert 'class="nav-export-label theme-toggle__label"' in html
    assert 'aria-label="当前外观：深色暖色，点击切换"' in html
    assert 'title="当前外观：深色暖色，点击切换"' in html
    assert "外观：深色暖色</span>" not in html


def test_base_template_hides_low_frequency_data_buttons(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="export-data-btn"' not in html
    assert 'id="export-obsidian-btn"' not in html
    assert 'id="import-data-btn"' not in html
    assert 'id="import-data-input"' not in html
    assert 'id="theme-toggle-btn"' in html


def test_theme_toggle_css_keeps_button_chrome_minimal():
    css = (PROJECT_ROOT / "static" / "css" / "main.css").read_text(encoding="utf-8")
    assert ".theme-toggle {" in css
    assert "background: transparent;" in css
    assert "box-shadow: none;" in css
    assert ".theme-toggle__label {\n  display: none;" in css
    assert "width: 22px;" in css
    assert "height: 22px;" in css


def test_main_js_updates_theme_toggle_accessible_label():
    script = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    assert 'short: "暖色", full: "深色暖色"' in script
    assert 'short: "冷色", full: "深色冷色"' in script
    assert 'label.textContent = theme.short;' in script
    assert 'button.setAttribute("aria-label", fullLabel);' in script
    assert 'button.setAttribute("title", fullLabel);' in script
    assert 'label: "外观：深色暖色"' not in script


def test_manifest_is_available(client):
    response = client.get("/static/manifest.json")
    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["name"] == "PSY-1 Personal OS"
    assert payload["short_name"] == "PSY-1"
    assert payload["start_url"] == "/"
    assert payload["display"] == "standalone"
    assert len(payload["icons"]) >= 2
    assert {icon["sizes"] for icon in payload["icons"]} >= {"192x192", "512x512"}


def test_service_worker_is_available(client):
    response = client.get("/service-worker.js")
    assert response.status_code == 200
    assert response.content_type.startswith("application/javascript")
    assert response.headers["Cache-Control"] == "no-cache"
    script = response.get_data(as_text=True)
    assert '"/api/"' in script
    assert "caches.open" in script
    assert "psy-2-pwa-v2.1.0" in script


def test_positioning_page(client):
    response = client.get("/positioning")
    assert response.status_code == 200


def test_tasks_page(client):
    response = client.get("/tasks")
    assert response.status_code == 200


def test_changelog_api(client):
    response = client.get("/api/changelog")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["current"] == "v2.1.0"
    assert isinstance(payload["data"]["entries"], list)


def test_list_goals_api(client):
    response = client.get("/api/goals")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)


def test_delete_goal_success(client):
    create = client.post(
        "/api/goals",
        json={"name": "测试目标", "type": "年度"},
    )
    goal_id = create.get_json()["data"]["id"]

    response = client.delete(f"/api/goals/{goal_id}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["deleted"] is True

    goals = client.get("/api/goals").get_json()["data"]
    assert all(goal["id"] != goal_id for goal in goals)


def test_delete_goal_not_found(client):
    response = client.delete("/api/goals/99999")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert "不存在" in payload["error"]


def test_import_empty_backup(client):
    response = client.post(
        "/api/import",
        json=_empty_backup(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["imported"] == 0
    assert payload["data"]["skipped"] == 0
    assert payload["data"]["failed"] == 0


def test_import_roundtrip(client):
    goal = client.post(
        "/api/goals",
        json={"name": "导入测试", "type": "季度"},
    ).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "导入项目"},
    ).get_json()["data"]
    client.post(
        "/api/tasks",
        json={"project_id": project["id"], "name": "导入任务"},
    )

    export_response = client.get("/api/export")
    backup = json.loads(export_response.data)

    client.delete(f"/api/goals/{goal['id']}")
    assert client.get("/api/goals").get_json()["data"] == []

    import_response = client.post("/api/import", json=backup)
    assert import_response.status_code == 200
    stats = import_response.get_json()["data"]
    assert stats["imported"] >= 3
    assert stats["failed"] == 0

    goals = client.get("/api/goals").get_json()["data"]
    assert len(goals) == 1
    assert goals[0]["name"] == "导入测试"


def test_import_invalid_json_body(client):
    response = client.post(
        "/api/import",
        data="not-json",
        content_type="application/json",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False


def test_import_invalid_backup_structure(client):
    response = client.post(
        "/api/import",
        json={"meta": {"version": "9.9"}},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]
