import json
import sqlite3

import database


def test_value_tables_are_initialized(client):
    conn = database.get_connection()
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    project_columns = database._table_columns(conn, "projects")
    asset_columns = database._table_columns(conn, "assets")
    conn.close()

    assert {"opportunities", "experiments", "feedback_items"} <= tables
    assert "core_hypothesis" in project_columns
    assert "asset_level" in asset_columns


def test_legacy_database_migrates_value_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy-value.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待处理',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_date TEXT NOT NULL,
            type TEXT NOT NULL,
            what_done TEXT NOT NULL DEFAULT '',
            stuck TEXT NOT NULL DEFAULT '',
            next_adjust TEXT NOT NULL DEFAULT '',
            depositable TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            trigger_context TEXT NOT NULL DEFAULT '',
            core_content TEXT NOT NULL DEFAULT '',
            asset_type TEXT NOT NULL,
            capability_tags TEXT NOT NULL DEFAULT '[]',
            source_review_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_review_id) REFERENCES reviews(id) ON DELETE SET NULL
        );
        CREATE TABLE capability_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            content TEXT NOT NULL,
            source_project TEXT,
            level_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO goals (id, name, type, created_at) VALUES (1, '旧目标', '年度', '2026-01-01 00:00:00');
        INSERT INTO projects (id, goal_id, name, created_at) VALUES (1, 1, '旧项目', '2026-01-01 00:00:00');
        INSERT INTO assets (id, title, core_content, asset_type, capability_tags, created_at)
        VALUES (1, '旧资产', '旧内容', '知识卡片', '[]', '2026-01-01 00:00:00');
        """
    )
    conn.commit()
    conn.close()

    database.init_db()

    conn = database.get_connection()
    assert "opportunities" in {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert conn.execute("SELECT core_hypothesis FROM projects WHERE id = 1").fetchone()[0] == ""
    assert conn.execute("SELECT asset_level FROM assets WHERE id = 1").fetchone()[0] == "资料"
    conn.close()


def test_opportunities_api_crud(client):
    create = client.post(
        "/api/opportunities",
        json={
            "name": "高价值机会",
            "status": "值得测试",
            "importance_score": 5,
            "feedback_speed_score": 4,
            "revenue_score": 4,
            "asset_score": 4,
            "leverage_score": 3,
        },
    )
    assert create.status_code == 200
    opportunity = create.get_json()["data"]
    assert opportunity["total_score"] == 20

    update = client.patch(
        f"/api/opportunities/{opportunity['id']}",
        json={"next_action": "启动7天MVP", "leverage_score": 5},
    )
    assert update.status_code == 200
    assert update.get_json()["data"]["total_score"] == 22

    assert len(client.get("/api/opportunities").get_json()["data"]) == 1
    delete = client.delete(f"/api/opportunities/{opportunity['id']}")
    assert delete.status_code == 200


def test_experiments_api_crud(client):
    opportunity = client.post("/api/opportunities", json={"name": "待实验机会"}).get_json()["data"]
    create = client.post(
        "/api/experiments",
        json={
            "opportunity_id": opportunity["id"],
            "name": "7天验证",
            "experiment_type": "交易型MVP",
            "minimum_action": "找一个真实使用者",
        },
    )
    assert create.status_code == 200
    experiment = create.get_json()["data"]
    assert experiment["opportunity_id"] == opportunity["id"]
    assert experiment["opportunity_name"] == "待实验机会"

    dashboard = client.get("/api/value-dashboard").get_json()["data"]
    running = dashboard["running_experiments"]
    assert any(
        item["id"] == experiment["id"]
        and item["opportunity_id"] == opportunity["id"]
        and item["opportunity_name"] == "待实验机会"
        for item in running
    )

    update = client.patch(
        f"/api/experiments/{experiment['id']}",
        json={"status": "进行中", "real_feedback": "有人愿意试用"},
    )
    assert update.status_code == 200
    assert update.get_json()["data"]["status"] == "进行中"
    assert client.delete(f"/api/experiments/{experiment['id']}").status_code == 200


def test_experiment_requires_opportunity_when_created_from_opportunity(client):
    response = client.post(
        "/api/experiments",
        json={"name": "缺少关联的机会实验", "require_opportunity": True},
    )
    assert response.status_code == 400
    assert "opportunity_id" in response.get_json()["error"]


def test_feedback_api_crud(client):
    create = client.post(
        "/api/feedback",
        json={
            "title": "真实使用反馈",
            "source": "使用者反馈",
            "level": "L4 产生可量化结果",
            "content": "流程被实际使用",
        },
    )
    assert create.status_code == 200
    feedback = create.get_json()["data"]

    update = client.patch(
        f"/api/feedback/{feedback['id']}",
        json={"evidence": "节省 30 分钟"},
    )
    assert update.status_code == 200
    assert update.get_json()["data"]["evidence"] == "节省 30 分钟"
    assert client.delete(f"/api/feedback/{feedback['id']}").status_code == 200


def test_feedback_can_link_to_experiment(client):
    experiment = client.post(
        "/api/experiments",
        json={"name": "反馈关联实验"},
    ).get_json()["data"]
    feedback = client.post(
        "/api/feedback",
        json={
            "title": "实验触发反馈",
            "related_type": "experiment",
            "related_id": experiment["id"],
            "source": "使用者反馈",
            "level": "L2 同事/使用者觉得有价值",
        },
    ).get_json()["data"]

    assert feedback["related_type"] == "experiment"
    assert feedback["related_id"] == experiment["id"]


def test_feedback_can_generate_case_asset(client):
    feedback = client.post(
        "/api/feedback",
        json={
            "title": "周岁礼 AI 版面销售初测反馈",
            "source": "客户反馈",
            "level": "L3 业务流程开始使用",
            "content": "客户愿意基于样图继续沟通",
            "evidence": "客户追问价格和交付周期",
            "next_action": "补充报价页和交付案例",
        },
    ).get_json()["data"]

    response = client.post(f"/api/feedback/{feedback['id']}/asset")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    asset = payload["data"]

    assert asset["title"] == "周岁礼 AI 版面销售初测反馈案例资产"
    assert asset["asset_type"] == "案例复盘"
    assert asset["asset_level"] == "案例"
    assert asset["summary"] == "客户愿意基于样图继续沟通"
    assert asset["core_content"] == "客户愿意基于样图继续沟通"
    assert asset["evidence"] == "客户追问价格和交付周期"
    assert asset["productization_next_step"] == "补充报价页和交付案例"
    assert asset["source_type"] == "feedback"
    assert asset["source_id"] == feedback["id"]

    assets = client.get("/api/assets").get_json()["data"]
    assert any(item["id"] == asset["id"] for item in assets)


def test_feedback_generate_case_asset_not_found(client):
    response = client.post("/api/feedback/999999/asset")
    assert response.status_code == 404
    assert response.get_json()["ok"] is False


def test_strong_feedback_can_generate_case_asset_with_default_next_step(client):
    feedback = client.post(
        "/api/feedback",
        json={
            "title": "强反馈验证",
            "source": "数据反馈",
            "level": "L4 产生可量化结果",
            "content": "",
            "evidence": "转化率提升 12%",
        },
    ).get_json()["data"]

    response = client.post(f"/api/feedback/{feedback['id']}/asset")
    assert response.status_code == 200
    asset = response.get_json()["data"]
    assert asset["asset_level"] == "案例"
    assert asset["asset_type"] == "案例复盘"
    assert asset["evidence"] == "转化率提升 12%"
    assert asset["productization_next_step"] == "继续补充结果数据、适用场景和可复用方法。"
    assert "强反馈验证" in asset["external_expression"]
    assert asset["source_type"] == "feedback"
    assert asset["source_id"] == feedback["id"]


def test_project_audit_fields_preserve_old_project(client):
    goal = client.post("/api/goals", json={"name": "目标", "type": "年度"}).get_json()["data"]
    project = client.post("/api/projects", json={"goal_id": goal["id"], "name": "项目"}).get_json()["data"]
    assert project["core_hypothesis"] == ""
    assert project["total_score"] == 0

    updated = client.patch(
        f"/api/projects/{project['id']}",
        json={"core_hypothesis": "用户会为结果付费", "importance_score": 5},
    ).get_json()["data"]
    assert updated["name"] == "项目"
    assert updated["core_hypothesis"] == "用户会为结果付费"
    assert updated["total_score"] == 5


def test_asset_value_fields_preserve_old_asset(client):
    asset = client.post(
        "/api/assets",
        json={
            "title": "案例资产",
            "asset_type": "案例复盘",
            "fields": {"资产说明": "可展示案例"},
            "asset_level": "案例",
            "evidence": "有真实反馈",
            "capability_tags": [],
        },
    ).get_json()["data"]
    assert asset["asset_level"] == "案例"
    assert asset["evidence"] == "有真实反馈"

    updated = client.patch(
        f"/api/assets/{asset['id']}",
        json={"asset_level": "筹码", "external_expression": "对外版本"},
    ).get_json()["data"]
    assert updated["asset_level"] == "筹码"
    assert updated["external_expression"] == "对外版本"


def test_export_import_v2_and_legacy_v1_compatibility(client):
    client.post("/api/opportunities", json={"name": "导出机会", "importance_score": 5})
    backup = json.loads(client.get("/api/export").data)
    assert backup["meta"]["version"] == "2.0"
    assert "opportunities" in backup

    imported = client.post("/api/import", json=backup)
    assert imported.status_code == 200
    assert imported.get_json()["data"]["failed"] == 0

    legacy = {
        "meta": {"version": "1.0"},
        "goals": [],
        "projects": [],
        "tasks": [],
        "reviews": [],
        "assets": [],
        "capability_entries": [],
    }
    assert client.post("/api/import/preview", json=legacy).status_code == 200


def test_health_and_homepage_for_value_rc1(client):
    health = client.get("/api/health").get_json()["data"]
    assert health["version"] == "v2.0.0-rc.1"

    home = client.get("/")
    assert home.status_code == 200
    html = home.get_data(as_text=True)
    assert "PSY-2.0 价值实验" in html
    assert "审计机会" in html
