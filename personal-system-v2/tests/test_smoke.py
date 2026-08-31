import json
import struct
from pathlib import Path

import database
import site_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _png_dimensions(path):
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", header[16:24])


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


def test_base_template_has_brand_favicons_and_dynamic_version(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/static/icons/brand/favicon.ico"' in html
    assert 'href="/static/icons/brand/favicon-32x32.png"' in html
    assert 'href="/static/icons/brand/favicon-16x16.png"' in html
    assert 'href="/static/icons/brand/apple-touch-icon.png"' in html
    assert '<span class="nav-brand-version">v2.2.0</span>' in html

    template = (PROJECT_ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "{{ current_version }}" in template
    assert "v2.2.0" not in template


def test_brand_icon_assets_are_available(client):
    brand_dir = PROJECT_ROOT / "static" / "icons" / "brand"
    assert not (PROJECT_ROOT / "psy-app-icon-source.png.png").exists()
    assert _png_dimensions(brand_dir / "psy-app-icon.png") == (1254, 1254)
    assert _png_dimensions(brand_dir / "favicon-16x16.png") == (16, 16)
    assert _png_dimensions(brand_dir / "favicon-32x32.png") == (32, 32)
    assert _png_dimensions(brand_dir / "apple-touch-icon.png") == (180, 180)

    ico_header = (brand_dir / "favicon.ico").read_bytes()[:6]
    assert ico_header[:4] == b"\x00\x00\x01\x00"
    assert int.from_bytes(ico_header[4:6], "little") >= 2

    for path in (
        "/static/icons/brand/favicon.ico",
        "/static/icons/brand/favicon-16x16.png",
        "/static/icons/brand/favicon-32x32.png",
        "/static/icons/brand/apple-touch-icon.png",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content_type.startswith("image/")


def test_login_page_uses_shared_brand_favicons(unauthenticated_client):
    response = unauthenticated_client.get("/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/static/icons/brand/favicon.ico"' in html
    assert 'href="/static/icons/brand/apple-touch-icon.png"' in html


def test_icp_filing_is_hidden_when_unconfigured(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'class="sidebar-icp"' not in response.get_data(as_text=True)


def test_icp_filing_is_rendered_only_when_configured(client, monkeypatch):
    filing_number = "测试ICP备00000000号-1"
    monkeypatch.setattr(site_config, "get_icp_filing_number", lambda: filing_number)

    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert filing_number in html
    assert 'class="sidebar-icp"' in html
    assert 'href="https://beian.miit.gov.cn/"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


def test_site_config_reads_icp_filing_number(tmp_path, monkeypatch):
    config_path = tmp_path / "site_config.json"
    config_path.write_text(
        json.dumps({"icp_filing_number": "  测试ICP备00000000号-1  "}),
        encoding="utf-8",
    )
    monkeypatch.setattr(site_config, "SITE_CONFIG_PATH", str(config_path))
    assert site_config.get_icp_filing_number() == "测试ICP备00000000号-1"


def test_production_persistent_site_config_overrides_release_default(
    tmp_path, monkeypatch
):
    release_config = tmp_path / "release-site-config.json"
    persistent_config = tmp_path / "persistent-site-config.json"
    release_config.write_text(
        json.dumps({"icp_filing_number": "发布内默认备案号"}),
        encoding="utf-8",
    )
    persistent_config.write_text(
        json.dumps({"icp_filing_number": "持久配置备案号"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.setattr(site_config, "SITE_CONFIG_PATH", str(release_config))
    monkeypatch.setattr(
        site_config, "PERSISTENT_SITE_CONFIG_PATH", str(persistent_config)
    )

    assert site_config.get_icp_filing_number() == "持久配置备案号"

    release_config.write_text(
        json.dumps({"icp_filing_number": "新发布内默认备案号"}),
        encoding="utf-8",
    )
    assert site_config.get_icp_filing_number() == "持久配置备案号"


def test_optional_production_site_config_missing_or_malformed_is_safe(
    tmp_path, monkeypatch
):
    release_config = tmp_path / "release-site-config.json"
    persistent_config = tmp_path / "persistent-site-config.json"
    release_config.write_text(
        json.dumps({"icp_filing_number": ""}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.setattr(site_config, "SITE_CONFIG_PATH", str(release_config))
    monkeypatch.setattr(
        site_config, "PERSISTENT_SITE_CONFIG_PATH", str(persistent_config)
    )

    assert site_config.get_icp_filing_number() == ""

    persistent_config.write_text("{malformed", encoding="utf-8")
    assert site_config.get_icp_filing_number() == ""


def test_development_does_not_require_production_site_config(tmp_path, monkeypatch):
    release_config = tmp_path / "release-site-config.json"
    persistent_config = tmp_path / "persistent-site-config.json"
    release_config.write_text(
        json.dumps({"icp_filing_number": ""}),
        encoding="utf-8",
    )
    persistent_config.write_text(
        json.dumps({"icp_filing_number": "仅生产使用的备案号"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PERSONAL_OS_ENV", "development")
    monkeypatch.setattr(site_config, "SITE_CONFIG_PATH", str(release_config))
    monkeypatch.setattr(
        site_config, "PERSISTENT_SITE_CONFIG_PATH", str(persistent_config)
    )

    assert site_config.get_icp_filing_number() == ""


def test_physical_release_switch_keeps_persistent_icp(tmp_path, monkeypatch):
    release_a_config = tmp_path / "release-a" / "site_config.json"
    release_b_config = tmp_path / "release-b" / "site_config.json"
    persistent_config = tmp_path / "production" / "site_config.json"
    for release_config in (release_a_config, release_b_config):
        release_config.parent.mkdir(parents=True)
        release_config.write_text(
            json.dumps({"icp_filing_number": ""}),
            encoding="utf-8",
        )
    persistent_config.parent.mkdir()
    persistent_config.write_text(
        json.dumps({"icp_filing_number": "跨发布持久备案号"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PERSONAL_OS_ENV", "production")
    monkeypatch.setattr(
        site_config, "PERSISTENT_SITE_CONFIG_PATH", str(persistent_config)
    )

    monkeypatch.setattr(site_config, "SITE_CONFIG_PATH", str(release_a_config))
    assert site_config.get_icp_filing_number() == "跨发布持久备案号"

    monkeypatch.setattr(site_config, "SITE_CONFIG_PATH", str(release_b_config))
    assert site_config.get_icp_filing_number() == "跨发布持久备案号"


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
    assert "psy-2-pwa-auth-shell-v2" in script
    assert 'const APP_SHELL_URLS = [\n  "/static/' in script
    assert 'request.mode === "navigate"' in script
    assert 'cache.match("/")' not in script
    assert "X-Personal-OS-Token" not in script


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
    assert payload["data"]["current"] == "v2.2.0"
    assert payload["data"]["build_identity"].startswith("v2.2.0")
    versions = [entry["version"] for entry in payload["data"]["entries"]]
    assert versions[:3] == ["v2.2.0", "v2.2.0-shadow", "v2.1.4"]
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
