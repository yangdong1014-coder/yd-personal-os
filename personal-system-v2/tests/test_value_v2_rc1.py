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


def test_value_chain_links_across_opportunity_experiment_feedback_asset(client):
    opportunity = client.post(
        "/api/opportunities",
        json={"name": "链路机会", "status": "值得测试"},
    ).get_json()["data"]
    experiment = client.post(
        "/api/experiments",
        json={
            "opportunity_id": opportunity["id"],
            "name": "链路实验",
            "status": "进行中",
        },
    ).get_json()["data"]
    feedback = client.post(
        "/api/feedback",
        json={
            "title": "链路反馈",
            "related_type": "experiment",
            "related_id": experiment["id"],
            "source": "客户反馈",
            "level": "L4 产生可量化结果",
            "content": "客户愿意继续试用",
            "evidence": "给出明确改进建议",
        },
    ).get_json()["data"]
    asset = client.post(f"/api/feedback/{feedback['id']}/asset").get_json()["data"]

    opportunity_links = client.get(
        f"/api/opportunities/{opportunity['id']}/links"
    ).get_json()["data"]
    assert opportunity_links["opportunity"]["id"] == opportunity["id"]
    assert [item["id"] for item in opportunity_links["experiments"]] == [experiment["id"]]
    assert [item["id"] for item in opportunity_links["feedback"]] == [feedback["id"]]
    assert [item["id"] for item in opportunity_links["assets"]] == [asset["id"]]
    assert opportunity_links["counts"] == {"experiments": 1, "feedback": 1, "assets": 1}

    experiment_links = client.get(
        f"/api/experiments/{experiment['id']}/links"
    ).get_json()["data"]
    assert experiment_links["experiment"]["id"] == experiment["id"]
    assert experiment_links["opportunity"]["id"] == opportunity["id"]
    assert [item["id"] for item in experiment_links["feedback"]] == [feedback["id"]]
    assert [item["id"] for item in experiment_links["assets"]] == [asset["id"]]

    feedback_links = client.get(
        f"/api/feedback/{feedback['id']}/links"
    ).get_json()["data"]
    assert feedback_links["feedback"]["id"] == feedback["id"]
    assert feedback_links["related_type"] == "experiment"
    assert feedback_links["related"]["id"] == experiment["id"]
    assert feedback_links["upstream"]["opportunity"]["id"] == opportunity["id"]
    assert [item["id"] for item in feedback_links["assets"]] == [asset["id"]]

    asset_links = client.get(f"/api/assets/{asset['id']}/links").get_json()["data"]
    assert asset_links["asset"]["id"] == asset["id"]
    assert asset_links["source_type"] == "feedback"
    assert asset_links["source"]["id"] == feedback["id"]
    assert asset_links["upstream"]["feedback"]["id"] == feedback["id"]
    assert asset_links["upstream"]["experiment"]["id"] == experiment["id"]
    assert asset_links["upstream"]["opportunity"]["id"] == opportunity["id"]


def test_value_links_return_empty_arrays_without_related_data(client):
    opportunity = client.post(
        "/api/opportunities",
        json={"name": "孤立机会"},
    ).get_json()["data"]
    experiment = client.post(
        "/api/experiments",
        json={"name": "孤立实验"},
    ).get_json()["data"]
    feedback = client.post(
        "/api/feedback",
        json={"title": "孤立反馈"},
    ).get_json()["data"]

    opportunity_links = client.get(
        f"/api/opportunities/{opportunity['id']}/links"
    ).get_json()["data"]
    assert opportunity_links["experiments"] == []
    assert opportunity_links["feedback"] == []
    assert opportunity_links["assets"] == []

    experiment_links = client.get(
        f"/api/experiments/{experiment['id']}/links"
    ).get_json()["data"]
    assert experiment_links["opportunity"] is None
    assert experiment_links["feedback"] == []
    assert experiment_links["assets"] == []

    feedback_links = client.get(
        f"/api/feedback/{feedback['id']}/links"
    ).get_json()["data"]
    assert feedback_links["related"] is None
    assert feedback_links["assets"] == []


def test_value_links_return_404_for_missing_records(client):
    assert client.get("/api/opportunities/999999/links").status_code == 404
    assert client.get("/api/experiments/999999/links").status_code == 404
    assert client.get("/api/feedback/999999/links").status_code == 404
    assert client.get("/api/assets/999999/links").status_code == 404


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
    assert health["version"] == "v2.0.0-rc.3"

    home = client.get("/")
    assert home.status_code == 200
    html = home.get_data(as_text=True)
    assert "PSY-2.0 价值实验" in html
    assert "审计机会" in html


def test_value_discipline_pages_render(client):
    for path in ("/", "/opportunities", "/experiments", "/feedback", "/assets", "/goals", "/inbox"):
        response = client.get(path)
        assert response.status_code == 200


def test_value_dashboard_rc3_signals(client):
    opportunity = client.post(
        "/api/opportunities",
        json={
            "name": "待验证机会",
            "status": "值得测试",
            "importance_score": 5,
            "feedback_speed_score": 5,
            "revenue_score": 5,
        },
    ).get_json()["data"]
    experiment = client.post(
        "/api/experiments",
        json={
            "name": "待沉淀实验",
            "status": "已验证",
            "success_criteria": "完成验证",
        },
    ).get_json()["data"]
    feedback = client.post(
        "/api/feedback",
        json={
            "title": "待沉淀强反馈",
            "source": "客户反馈",
            "level": "L5 带来收入、降本、加薪、资源、外部机会",
        },
    ).get_json()["data"]
    paused = client.post(
        "/api/experiments",
        json={
            "name": "待停止观察实验",
            "status": "进行中",
            "failure_criteria": "三天无反馈",
        },
    ).get_json()["data"]

    data = client.get("/api/value-dashboard").get_json()["data"]
    assert any(item["id"] == opportunity["id"] for item in data["pending_validation"])
    assert any(item["id"] == feedback["id"] for item in data["pending_deposit"])
    assert any(
        item["id"] == experiment["id"]
        for item in data["completed_experiments_without_assets"]
    )
    assert any(item["id"] == paused["id"] for item in data["pending_stop_review"])


def test_project_value_discipline_fields_do_not_break_project_api(client):
    goal = client.post("/api/goals", json={"name": "纪律目标", "type": "年度"}).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "纪律项目"},
    ).get_json()["data"]

    updated = client.patch(
        f"/api/projects/{project['id']}",
        json={
            "stop_condition": "连续两周无真实反馈则停止",
            "disconfirming_signal": "用户不愿意试用",
            "value_capture": "形成可对外展示案例",
        },
    )
    assert updated.status_code == 200
    data = updated.get_json()["data"]
    assert data["stop_condition"] == "连续两周无真实反馈则停止"
    assert data["disconfirming_signal"] == "用户不愿意试用"
    assert data["value_capture"] == "形成可对外展示案例"


def test_value_discipline_statuses_do_not_break_value_apis(client):
    for status in ("值得测试", "暂停", "删除", "已转项目"):
        response = client.post(
            "/api/opportunities",
            json={"name": f"{status}机会", "status": status},
        )
        assert response.status_code == 200
        assert response.get_json()["data"]["status"] == status

    for status in ("进行中", "已验证", "未验证", "已暂停"):
        response = client.post(
            "/api/experiments",
            json={
                "name": f"{status}实验",
                "status": status,
                "success_criteria": "有明确结果",
                "failure_criteria": "无真实反馈",
            },
        )
        assert response.status_code == 200
        assert response.get_json()["data"]["status"] == status


def test_asset_delete_api_still_works_for_case_asset(client):
    asset = client.post(
        "/api/assets",
        json={
            "title": "待删除案例资产",
            "asset_type": "案例复盘",
            "asset_level": "案例",
            "fields": {"资产说明": "可删除案例"},
        },
    ).get_json()["data"]

    response = client.delete(f"/api/assets/{asset['id']}")
    assert response.status_code == 200
    assert response.get_json()["data"]["deleted"] is True


def test_links_api_handles_missing_relations_without_500(client):
    feedback = client.post(
        "/api/feedback",
        json={
            "title": "断链反馈",
            "related_type": "experiment",
            "related_id": 999999,
        },
    ).get_json()["data"]
    asset = client.post(
        "/api/assets",
        json={
            "title": "断链资产",
            "asset_type": "案例复盘",
            "asset_level": "案例",
            "fields": {"资产说明": "断链来源"},
        },
    ).get_json()["data"]

    conn = database.get_connection()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "UPDATE assets SET source_type = ?, source_id = ? WHERE id = ?",
        ("feedback", 999999, asset["id"]),
    )
    conn.execute(
        """
        INSERT INTO experiments (
            id, opportunity_id, name, hypothesis, experiment_type,
            minimum_action, test_target, feedback_source, validation_period,
            success_criteria, failure_criteria, progress, real_feedback,
            data_result, next_decision, review_conclusion, status, created_at, updated_at
        ) VALUES (?, ?, ?, '', '结果型MVP', '', '', '', '', '', '', '', '', '', '', '', '设计中', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
        """,
        (999998, 999997, "断链实验"),
    )
    conn.commit()
    conn.close()

    feedback_links = client.get(f"/api/feedback/{feedback['id']}/links")
    assert feedback_links.status_code == 200
    assert feedback_links.get_json()["data"]["related"] is None

    asset_links = client.get(f"/api/assets/{asset['id']}/links")
    assert asset_links.status_code == 200
    assert asset_links.get_json()["data"]["source"] is None

    experiment_links = client.get("/api/experiments/999998/links")
    assert experiment_links.status_code == 200
    assert experiment_links.get_json()["data"]["opportunity"] is None
