import database


def test_create_sop_asset_with_fields(client):
    response = client.post(
        "/api/assets",
        json={
            "title": "发布检查 SOP",
            "asset_type": "SOP",
            "maturity": "可用",
            "fields": {
                "适用场景": "版本发布前",
                "执行步骤": "1. pytest\n2. 更新 changelog",
            },
            "capability_tags": ["落地力"],
        },
    )
    assert response.status_code == 200
    asset = response.get_json()["data"]
    assert asset["asset_type"] == "SOP"
    assert asset["fields"]["适用场景"] == "版本发布前"
    assert asset["maturity"] == "可用"
    assert asset["summary"]


def test_list_assets_filter_by_type(client):
    client.post(
        "/api/assets",
        json={
            "title": "洞察 A",
            "asset_type": "本质洞察",
            "fields": {"底层本质": "测试洞察"},
        },
    )
    client.post(
        "/api/assets",
        json={
            "title": "SOP B",
            "asset_type": "SOP",
            "fields": {"执行步骤": "步骤"},
        },
    )
    sop_only = client.get("/api/assets?asset_type=SOP").get_json()["data"]
    assert len(sop_only) == 1
    assert sop_only[0]["title"] == "SOP B"


def test_legacy_asset_migration(client):
    conn = database.get_connection()
    cur = conn.execute(
        """
        INSERT INTO assets (
            title, trigger_context, core_content, asset_type,
            capability_tags, source_review_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "旧知识卡片",
            "某场景",
            "某本质内容",
            "知识卡片",
            "[]",
            None,
            "2026-01-01 00:00:00",
        ),
    )
    asset_id = cur.lastrowid
    conn.commit()
    conn.close()

    database.init_db()
    asset = database.get_asset(asset_id)
    assert asset["asset_type"] in ("本质洞察", "方法论", "通用资产")
    assert asset["fields"]
    assert asset["summary"]


def test_increment_reuse_count(client):
    created = client.post(
        "/api/assets",
        json={
            "title": "复用测试",
            "asset_type": "模板",
            "fields": {"核心内容": "内容"},
        },
    ).get_json()["data"]
    updated = client.post(f"/api/assets/{created['id']}/reuse").get_json()["data"]
    assert updated["reuse_count"] == 1


def test_update_asset_editable_fields_preserves_system_fields(client, monkeypatch):
    now_values = iter(
        [
            "2026-06-23 01:00:00",
            "2026-06-23 01:30:00",
            "2026-06-23 02:00:00",
        ]
    )
    monkeypatch.setattr(database, "_now", lambda: next(now_values))

    created = client.post(
        "/api/assets",
        json={
            "title": "待编辑资产",
            "asset_type": "本质洞察",
            "maturity": "草稿",
            "fields": {"底层本质": "旧本质"},
            "reusable_scenario": "旧场景",
            "capability_tags": ["本质力"],
        },
    ).get_json()["data"]
    reused = client.post(f"/api/assets/{created['id']}/reuse").get_json()["data"]
    assert reused["reuse_count"] == 1

    response = client.patch(
        f"/api/assets/{created['id']}",
        json={
            "id": 99999,
            "created_at": "1999-01-01 00:00:00",
            "reuse_count": 999,
            "title": "已编辑资产",
            "asset_type": "方法论",
            "maturity": "稳定",
            "summary": "",
            "fields": {
                "解决的问题": "重复思考",
                "核心原则": "先抽象再执行",
                "操作流程": "收集事实\n提炼原则",
            },
            "reusable_scenario": "方案复盘",
            "capability_tags": ["产品力", "不存在的能力"],
        },
    )

    assert response.status_code == 200
    asset = response.get_json()["data"]
    assert asset["id"] == created["id"]
    assert asset["created_at"] == created["created_at"]
    assert asset["reuse_count"] == 1
    assert asset["updated_at"] == "2026-06-23 02:00:00"
    assert asset["updated_at"] != created["updated_at"]
    assert asset["title"] == "已编辑资产"
    assert asset["asset_type"] == "方法论"
    assert asset["maturity"] == "稳定"
    assert asset["fields"]["核心原则"] == "先抽象再执行"
    assert asset["reusable_scenario"] == "方案复盘"
    assert asset["capability_tags"] == ["产品力"]
    assert asset["summary"] == "先抽象再执行"

    assets = client.get("/api/assets").get_json()["data"]
    listed = next(item for item in assets if item["id"] == created["id"])
    assert listed["title"] == "已编辑资产"
    assert listed["fields"]["核心原则"] == "先抽象再执行"
