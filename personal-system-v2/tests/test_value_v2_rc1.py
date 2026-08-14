import json
import sqlite3
from pathlib import Path

import pytest

import ai_service
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


def test_init_db_refuses_partial_legacy_value_migration(tmp_path, monkeypatch):
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

    with pytest.raises(database.LegacyMigrationRequired):
        database.init_db()

    conn = sqlite3.connect(db_path)
    assert "opportunities" not in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "core_hypothesis" not in {
        row[1] for row in conn.execute("PRAGMA table_info(projects)")
    }
    assert "asset_level" not in {
        row[1] for row in conn.execute("PRAGMA table_info(assets)")
    }
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
    assert health == {"status": "up"}

    home = client.get("/")
    assert home.status_code == 200
    html = home.get_data(as_text=True)
    assert "价值链路总览" in html
    assert "按机会聚合当前未归档链路" in html
    assert "<h2>资产复利</h2>" not in html
    assert "asset-compound" not in html
    assert "审计机会" in html


def test_value_chain_homepage_semantic_actions_are_present():
    index_js = Path("static/js/index.js").read_text(encoding="utf-8")

    for text in (
        "启动实验",
        "更新实验",
        "记录反馈",
        "沉淀案例",
        "复盘判断",
        "确认归档",
        "回查链路",
        "修改当前链路",
        "已沉淀资产",
        "查看资产",
        "复用资产",
        "当前缺口",
        "还没有沉淀案例资产",
        "当前状态",
        "机会待验证",
        "实验进行中",
        "等待真实反馈",
        "结果待资产化",
        "需要停止/调整判断",
        "value-chain-compact",
        "value-chain-details",
        "value-chain-supplement-list",
        "value-chain-supplement-empty",
        "暂无更多补充信息，建议先启动实验。",
        "btn-chain-expand",
        "展开",
        "去机会页查看完整链路",
    ):
        assert text in index_js
    assert "value-chain-flow" not in index_js
    assert '<div class="value-chain-details" hidden>' in index_js
    assert "renderChainSupplement(chain)" in index_js
    assert index_js.index("btn-chain-expand") < index_js.index("btn-chain-links")

    main_css = Path("static/css/main.css").read_text(encoding="utf-8")
    assert ".value-chain-supplement-list" in main_css
    assert ".value-chain-detail-grid" not in main_css
    assert "grid-template-columns: 1fr;" in main_css


def test_opportunity_center_cards_are_compact_and_links_are_stateful():
    opportunities_js = Path("static/js/opportunities.js").read_text(encoding="utf-8")
    main_css = Path("static/css/main.css").read_text(encoding="utf-8")

    for text in (
        "expandedOpportunityLinks",
        "linksCache",
        "listEl.addEventListener",
        "收起链路",
        "查看链路",
        "opportunity-card-title-row",
        "opportunity-card-source-meta",
        "opportunity-card-tools",
        "opportunity-card-badges",
        "opportunity-status-badge",
        "opportunity-link-latest-grid",
        "暂无下游链路，建议先创建实验验证该机会。",
        "去实验页",
        "去反馈页",
        "去资产页",
    ):
        assert text in opportunities_js
    assert "renderMvpLayerTag(item)" not in opportunities_js
    assert "renderDiscipline(item.status)" not in opportunities_js
    assert '<p class="entity-meta">${escapeHtml(item.source || "未记录来源")}</p>' not in opportunities_js
    assert 'class="btn btn-sm btn-ghost btn-links"' in opportunities_js
    assert "btn-links-action" not in opportunities_js
    assert 'closest(".btn-links")' in opportunities_js
    assert "expandedOpportunityLinks.delete(item.id)" in opportunities_js
    assert opportunities_js.count("${renderAiTools()}") == 1
    assert "value-link-panel[hidden]" in main_css
    assert ".opportunity-card-title-row" in main_css
    assert ".opportunity-card-source-meta" in main_css
    assert ".opportunity-card-tools" in main_css
    assert ".value-link-summary" in main_css
    assert ".value-link-strip .btn-links" in main_css


def test_experiment_cards_use_single_meta_tag_row():
    experiments_js = Path("static/js/experiments.js").read_text(encoding="utf-8")
    main_css = Path("static/css/main.css").read_text(encoding="utf-8")

    assert "experiment-meta-tags" in experiments_js
    assert "renderExperimentMetaTags(item)" in experiments_js
    assert "experiment-title-meta" in experiments_js
    assert "renderExperimentTitleMeta(item)" in experiments_js
    assert "experiment-card-tools" in experiments_js
    assert experiments_js.count("${renderAiTools()}") == 1
    assert "来源机会：" in experiments_js
    assert "有假设" in experiments_js
    assert "有最小行动" in experiments_js
    assert "有失败标准" in experiments_js
    assert "有成功标准" in experiments_js
    assert "暂无下游反馈或案例资产，建议先生成反馈验证实验结果。" in experiments_js
    assert "experiment-link-summary" in experiments_js
    assert "renderMvpLayerTag(item)" not in experiments_js
    assert '<div class="value-card-meta">' not in experiments_js
    assert '<div class="kernel-tag-row">${renderKernelTags(item)}</div>' not in experiments_js
    assert "linkList(" not in experiments_js
    assert ".experiment-meta-tags" in main_css
    assert ".experiment-title-meta" in main_css
    assert ".experiment-card-tools" in main_css
    assert ".experiment-link-summary" in main_css
    assert "flex-wrap: wrap;" in main_css


def test_feedback_cards_use_single_meta_tag_row():
    feedback_js = Path("static/js/feedback.js").read_text(encoding="utf-8")
    main_css = Path("static/css/main.css").read_text(encoding="utf-8")

    assert "feedback-card-header" in feedback_js
    assert "feedback-card-meta" in feedback_js
    assert "feedback-card-tools" in feedback_js
    assert "feedback-card-head-tools" in feedback_js
    assert feedback_js.count("${renderAiTools()}") == 1
    assert '<p class="entity-meta">${escapeHtml(item.source)} · ${escapeHtml(item.level)}</p>' not in feedback_js
    assert "feedback-meta-tags" in feedback_js
    assert "renderFeedbackMetaTags(item, strongFeedback)" in feedback_js
    assert "关联对象：" in feedback_js
    assert "有证据" in feedback_js
    assert "强反馈" in feedback_js
    assert "有上游链路" in feedback_js
    assert "MVP 信号" in feedback_js
    assert "renderMvpLayerTag(item)" not in feedback_js
    assert '<div class="value-card-meta">' not in feedback_js
    assert '<div class="kernel-tag-row">${renderKernelTags(item, strongFeedback)}</div>' not in feedback_js
    assert ".feedback-card-header" in main_css
    assert ".feedback-card-meta" in main_css
    assert ".feedback-card-tools" in main_css
    assert ".feedback-card-head-tools" in main_css
    assert ".feedback-meta-tags" in main_css
    assert "flex-wrap: wrap;" in main_css


def test_asset_cards_follow_value_card_information_layers():
    assets_js = Path("static/js/assets.js").read_text(encoding="utf-8")
    main_css = Path("static/css/main.css").read_text(encoding="utf-8")

    assert "asset-title-meta" in assets_js
    assert "asset-meta-tags" in assets_js
    assert "renderAssetMetaTags(asset)" in assets_js
    assert "asset-link-strip" in assets_js
    assert "查看来源" in assets_js
    assert "收起来源" in assets_js
    assert "来源标题：待查看" not in assets_js
    assert "renderMvpLayerTag(asset)" not in assets_js
    assert "assetMvpSignalLabel(asset)" in assets_js
    assert "renderAssetDetailPanel(asset)" in assets_js
    assert "asset-detail-grid" in assets_js
    assert "asset-ai-toolbar" in assets_js
    assert "renderAssetDetailActions()" in assets_js
    assert 'renderAssetDetailField("摘要", asset.summary)' not in assets_js
    assert "module-ai-entry--inline" not in assets_js
    assert "module-ai-action-groups" not in assets_js
    assert ".asset-title-meta" in main_css
    assert ".asset-meta-tags" in main_css
    assert ".asset-link-strip" in main_css
    assert ".asset-detail-grid" in main_css
    assert ".asset-ai-toolbar" in main_css
    assert ".asset-detail-actions" in main_css
    assert ".asset-card-expanded .asset-archive-preview-line" in main_css
    assert "color: var(--text-primary);" in main_css
    assert "color: var(--text-secondary);" in main_css


def test_reviews_page_uses_collapsible_create_form():
    reviews_html = Path("templates/reviews.html").read_text(encoding="utf-8")
    reviews_js = Path("static/js/reviews.js").read_text(encoding="utf-8")
    main_css = Path("static/css/main.css").read_text(encoding="utf-8")

    assert 'id="toggle-review-form-btn"' in reviews_html
    assert 'id="review-form-panel" class="section-card review-form-panel" hidden' in reviews_html
    assert "reviews-workspace" in reviews_html
    assert "page-split page-split-wide page-split-scroll" not in reviews_html
    assert "review-form-topline" in reviews_html
    assert "review-form-grid" in reviews_html
    assert "isReviewFormOpen" in reviews_js
    assert "setReviewFormOpen(false)" in reviews_js
    assert "resetReviewForm()" in reviews_js
    assert ".reviews-workspace" in main_css
    assert ".review-form-grid" in main_css
    assert ".review-form-panel[hidden]" in main_css


def test_ai_entries_keep_real_actions_and_enable_value_chain_tools():
    index_js = Path("static/js/index.js").read_text(encoding="utf-8")
    assets_js = Path("static/js/assets.js").read_text(encoding="utf-8")
    opportunities_js = Path("static/js/opportunities.js").read_text(encoding="utf-8")
    experiments_js = Path("static/js/experiments.js").read_text(encoding="utf-8")
    feedback_js = Path("static/js/feedback.js").read_text(encoding="utf-8")
    reviews_js = Path("static/js/reviews.js").read_text(encoding="utf-8")
    inbox_js = Path("static/js/inbox.js").read_text(encoding="utf-8")
    main_css = Path("static/css/main.css").read_text(encoding="utf-8")

    for api in (
        "/api/ai/dashboard-briefing",
        "/api/ai/dispatch-actions",
    ):
        assert api in index_js
    for api in (
        "/api/ai/optimize-asset",
        "/api/ai/classify-asset",
        "/api/ai/template-asset",
    ):
        assert api in assets_js
    for api in (
        "/api/ai/complete-review",
        "/api/ai/aggregate-weekly-reviews",
        "/api/ai/refine-review",
    ):
        assert api in reviews_js
    assert "/api/inbox/analyze" in inbox_js
    assert "asset-ai-disabled-note" in assets_js
    assert "asset-ai-disabled\" disabled" not in assets_js
    for js, prefix in (
        (opportunities_js, "opportunity"),
        (experiments_js, "experiment"),
        (feedback_js, "feedback"),
    ):
        assert f"/api/ai/{prefix}-advance" in js
        assert f"/api/ai/{prefix}-red-team" in js
        assert f"/api/ai/{prefix}-audit" in js
        assert "btn-ai-value" in js
        assert "AI处理中" in js
        assert "btn-copy-ai-result" in js
    assert ".module-ai-entry:has(#opportunity-ai-title) .module-ai-actions" in main_css
    assert ".module-ai-entry:has(#experiment-ai-title) .module-ai-actions" in main_css
    assert ".module-ai-entry:has(#feedback-ai-title) .module-ai-actions" in main_css
    assert ".module-ai-entry:has(#asset-ai-title) .module-ai-actions" in main_css
    assert "display: none;" in main_css
    assert ".asset-ai-disabled-note" in main_css
    assert ".value-ai-tool-row" in main_css
    assert ".ai-result-panel" in main_css


def test_value_chain_ai_routes_call_helper_and_return_sections(client, monkeypatch):
    calls = []

    def fake_chat_json(system_prompt, user_prompt):
      calls.append((system_prompt, user_prompt))
      assert "机会 -> 实验 -> 反馈 -> 案例资产" in system_prompt
      assert "上下文 JSON" in user_prompt
      return {
          "title": "AI 审计结果",
          "summary": "当前对象可以继续推进，但证据不足。",
          "sections": [{"title": "缺失项", "items": ["补充真实对象", "补充验证动作"]}],
          "recommendation": "先做最小验证。",
          "next_action": "今天设计 7 天 MVP。",
      }

    monkeypatch.setattr(ai_service, "_chat_json", fake_chat_json)

    opportunity = client.post("/api/opportunities", json={"name": "AI 机会"}).get_json()["data"]
    experiment = client.post("/api/experiments", json={"name": "AI 实验"}).get_json()["data"]
    feedback = client.post("/api/feedback", json={"title": "AI 反馈"}).get_json()["data"]
    routes = (
        ("/api/ai/opportunity-advance", opportunity["id"]),
        ("/api/ai/opportunity-red-team", opportunity["id"]),
        ("/api/ai/opportunity-audit", opportunity["id"]),
        ("/api/ai/experiment-advance", experiment["id"]),
        ("/api/ai/experiment-red-team", experiment["id"]),
        ("/api/ai/experiment-audit", experiment["id"]),
        ("/api/ai/feedback-advance", feedback["id"]),
        ("/api/ai/feedback-red-team", feedback["id"]),
        ("/api/ai/feedback-audit", feedback["id"]),
    )

    for route, entity_id in routes:
        response = client.post(route, json={"id": entity_id})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        data = payload["data"]
        assert data["sections"][0]["title"] == "缺失项"
        assert data["recommendation"] == "先做最小验证。"
        assert data["next_action"] == "今天设计 7 天 MVP。"

    assert len(calls) == len(routes)


def test_value_chain_ai_routes_reject_missing_records(client, monkeypatch):
    monkeypatch.setattr(ai_service, "_chat_json", lambda *_args: {})
    for route in (
        "/api/ai/opportunity-advance",
        "/api/ai/experiment-red-team",
        "/api/ai/feedback-audit",
    ):
        response = client.post(route, json={"id": 999999})
        assert response.get_json()["ok"] is False


def test_value_discipline_pages_render(client):
    for path in ("/", "/opportunities", "/experiments", "/feedback", "/assets", "/reviews", "/goals", "/inbox"):
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


def _chain_for(data, opportunity_id):
    return next(
        item for item in data["chains"]
        if item["opportunity"]["id"] == opportunity_id
    )


def test_value_dashboard_chains_keep_legacy_fields(client):
    data = client.get("/api/value-dashboard").get_json()["data"]

    assert "chains" in data
    for key in (
        "high_score_opportunities",
        "running_experiments",
        "strong_feedback",
        "case_assets",
        "pending_validation",
        "pending_deposit",
        "completed_experiments_without_assets",
        "pending_stop_review",
    ):
        assert key in data


def test_value_dashboard_chains_group_latest_items_by_opportunity(client):
    first = client.post(
        "/api/opportunities",
        json={"name": "第一条链路", "status": "值得测试"},
    ).get_json()["data"]
    second = client.post(
        "/api/opportunities",
        json={"name": "第二条链路", "status": "值得测试"},
    ).get_json()["data"]
    client.post(
        "/api/experiments",
        json={"opportunity_id": first["id"], "name": "第一旧实验"},
    ).get_json()["data"]
    latest_exp = client.post(
        "/api/experiments",
        json={"opportunity_id": first["id"], "name": "第一新实验", "status": "进行中"},
    ).get_json()["data"]
    second_exp = client.post(
        "/api/experiments",
        json={"opportunity_id": second["id"], "name": "第二实验", "status": "设计中"},
    ).get_json()["data"]
    client.post(
        "/api/feedback",
        json={
            "related_type": "experiment",
            "related_id": latest_exp["id"],
            "title": "第一反馈",
            "level": "L4 产生可量化结果",
        },
    ).get_json()["data"]
    second_feedback = client.post(
        "/api/feedback",
        json={
            "related_type": "experiment",
            "related_id": second_exp["id"],
            "title": "第二反馈",
            "level": "L2 同事/使用者觉得有价值",
        },
    ).get_json()["data"]
    asset = client.post(f"/api/feedback/{second_feedback['id']}/asset").get_json()["data"]

    data = client.get("/api/value-dashboard").get_json()["data"]
    first_chain = _chain_for(data, first["id"])
    second_chain = _chain_for(data, second["id"])

    assert first_chain["latest_experiment"]["id"] == latest_exp["id"]
    assert first_chain["latest_feedback"]["title"] == "第一反馈"
    assert first_chain["latest_asset"] is None
    assert first_chain["counts"] == {"experiments": 2, "feedback": 1, "assets": 0}
    assert first_chain["stage"] == "待沉淀"

    assert second_chain["latest_experiment"]["id"] == second_exp["id"]
    assert second_chain["latest_feedback"]["id"] == second_feedback["id"]
    assert second_chain["latest_asset"]["id"] == asset["id"]
    assert second_chain["stage"] == "已完成"


def test_archived_opportunity_is_hidden_from_chains_but_listed(client):
    archived = client.post(
        "/api/opportunities",
        json={"name": "归档链路", "status": "值得测试"},
    ).get_json()["data"]
    active = client.post(
        "/api/opportunities",
        json={"name": "活跃链路", "status": "值得测试"},
    ).get_json()["data"]

    response = client.patch(
        f"/api/opportunities/{archived['id']}",
        json={"status": "已归档"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "已归档"

    dashboard = client.get("/api/value-dashboard").get_json()["data"]
    chain_ids = {item["opportunity"]["id"] for item in dashboard["chains"]}
    assert archived["id"] not in chain_ids
    assert active["id"] in chain_ids

    opportunities = client.get("/api/opportunities").get_json()["data"]
    assert any(
        item["id"] == archived["id"] and item["status"] == "已归档"
        for item in opportunities
    )


def test_value_dashboard_chain_stage_variants(client):
    no_experiment = client.post(
        "/api/opportunities",
        json={"name": "无实验机会", "status": "值得测试"},
    ).get_json()["data"]
    running_opportunity = client.post(
        "/api/opportunities",
        json={"name": "进行中机会", "status": "值得测试"},
    ).get_json()["data"]
    running_experiment = client.post(
        "/api/experiments",
        json={
            "opportunity_id": running_opportunity["id"],
            "name": "进行中实验",
            "status": "进行中",
        },
    ).get_json()["data"]
    deposit_opportunity = client.post(
        "/api/opportunities",
        json={"name": "待沉淀机会", "status": "值得测试"},
    ).get_json()["data"]
    deposit_experiment = client.post(
        "/api/experiments",
        json={
            "opportunity_id": deposit_opportunity["id"],
            "name": "待沉淀实验",
            "status": "进行中",
        },
    ).get_json()["data"]
    client.post(
        "/api/feedback",
        json={
            "related_type": "experiment",
            "related_id": deposit_experiment["id"],
            "title": "强反馈",
            "level": "L5 带来收入、降本、加薪、资源、外部机会",
        },
    ).get_json()["data"]
    complete_opportunity = client.post(
        "/api/opportunities",
        json={"name": "完成机会", "status": "值得测试"},
    ).get_json()["data"]
    complete_experiment = client.post(
        "/api/experiments",
        json={
            "opportunity_id": complete_opportunity["id"],
            "name": "完成实验",
            "status": "进行中",
        },
    ).get_json()["data"]
    complete_feedback = client.post(
        "/api/feedback",
        json={
            "related_type": "experiment",
            "related_id": complete_experiment["id"],
            "title": "完成反馈",
            "level": "L4 产生可量化结果",
            "content": "可以沉淀",
        },
    ).get_json()["data"]
    client.post(f"/api/feedback/{complete_feedback['id']}/asset")

    data = client.get("/api/value-dashboard").get_json()["data"]

    assert _chain_for(data, no_experiment["id"])["stage"] == "待验证"
    assert _chain_for(data, running_opportunity["id"])["latest_experiment"]["id"] == running_experiment["id"]
    assert _chain_for(data, running_opportunity["id"])["stage"] == "进行中"
    assert _chain_for(data, deposit_opportunity["id"])["stage"] == "待沉淀"
    assert _chain_for(data, complete_opportunity["id"])["stage"] == "已完成"


def test_value_dashboard_chain_change_adds_no_database_fields(client):
    conn = database.get_connection()
    columns = {
        table: {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for table in ("opportunities", "experiments", "feedback_items", "assets")
    }
    conn.close()

    assert not ({"archived", "is_archived", "deleted", "stopped"} & columns["opportunities"])
    assert not ({"archived", "is_archived", "deleted", "stopped"} & columns["experiments"])
    assert not ({"archived", "is_archived", "deleted", "stopped"} & columns["feedback_items"])
    assert not ({"archived", "is_archived", "deleted", "stopped"} & columns["assets"])


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
    for status in ("值得测试", "暂停", "删除", "已转项目", "已归档"):
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
    invalid_feedback = client.post(
        "/api/feedback",
        json={
            "title": "断链反馈",
            "related_type": "experiment",
            "related_id": 999999,
        },
    )
    assert invalid_feedback.status_code == 400
    feedback = client.post(
        "/api/feedback", json={"title": "无关联反馈"}
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
    owner_id = conn.execute(
        "SELECT user_id FROM assets WHERE id = ?", (asset["id"],)
    ).fetchone()["user_id"]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "UPDATE assets SET source_type = ?, source_id = ? WHERE id = ?",
        ("feedback", 999999, asset["id"]),
    )
    conn.execute(
        "DROP TRIGGER trg_experiments_opportunity_id_owner_insert"
    )
    conn.execute(
        """
        INSERT INTO experiments (
            id, user_id, opportunity_id, name, hypothesis, experiment_type,
            minimum_action, test_target, feedback_source, validation_period,
            success_criteria, failure_criteria, progress, real_feedback,
            data_result, next_decision, review_conclusion, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, '', '结果型MVP', '', '', '', '', '', '', '', '', '', '', '', '设计中', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
        """,
        (999998, owner_id, 999997, "断链实验"),
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
