import ai_service
from urllib.parse import quote


def _module_url(module):
    return quote(module)


def _create_asset(client, title, asset_type, fields, capability_tags=None, maturity="草稿"):
    return client.post(
        "/api/assets",
        json={
            "title": title,
            "asset_type": asset_type,
            "fields": fields,
            "capability_tags": capability_tags or [],
            "maturity": maturity,
        },
    ).get_json()["data"]


def _create_entry(client, module, content):
    return client.post(
        "/api/capability-entries",
        json={
            "module": module,
            "entry_date": "2026-06-24",
            "content": content,
            "source_project": "",
            "level_type": "能力层",
        },
    ).get_json()["data"]


def _seed_capability_dashboard(client):
    _create_asset(
        client,
        "本质草稿",
        "本质洞察",
        {"底层本质": "抓主要矛盾"},
        ["本质力"],
    )
    _create_asset(
        client,
        "建模草稿",
        "模型",
        {"核心变量": "输入、过程、输出"},
        ["建模力"],
    )
    _create_asset(
        client,
        "体系方法",
        "方法论",
        {"核心原则": "先结构后动作"},
        ["体系力"],
        "可用",
    )
    _create_asset(
        client,
        "体系模型",
        "模型",
        {"核心变量": "模块、关系、反馈"},
        ["体系力"],
        "稳定",
    )
    reused = _create_asset(
        client,
        "落地 SOP",
        "SOP",
        {"执行步骤": "拆解、执行、验收"},
        ["落地力", "体系力"],
        "可用",
    )
    _create_asset(
        client,
        "落地清单",
        "清单",
        {"核心内容": "发布前检查项"},
        ["落地力"],
        "标准化",
    )
    _create_asset(
        client,
        "无标签资产",
        "通用资产",
        {"核心内容": "不计入能力模块"},
        [],
    )
    client.post(f"/api/assets/{reused['id']}/reuse")
    client.post(f"/api/assets/{reused['id']}/reuse")
    _create_entry(client, "建模力", "一次建模训练")
    _create_entry(client, "建模力", "第二次建模训练")


def _module(summary, name):
    return next(item for item in summary["modules"] if item["module"] == name)


def _practice_path(client, module):
    return client.get(
        f"/api/capabilities/{_module_url(module)}/practice-path"
    ).get_json()["data"]


def test_capabilities_page_opens(client):
    response = client.get("/capabilities")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "能力总览" in html
    assert 'id="capability-training-title"' in html


def test_capability_summary_counts_assets_tags_and_reuse(client):
    _seed_capability_dashboard(client)

    response = client.get("/api/capabilities/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    summary = payload["data"]

    assert summary["overview"]["total_assets"] == 7
    assert summary["overview"]["tagged_assets"] == 6
    assert summary["overview"]["assigned_asset_total"] == 7

    essence = _module(summary, "本质力")
    assert essence["asset_count"] == 1
    assert essence["status"] == "薄弱"

    modeling = _module(summary, "建模力")
    assert modeling["entry_count"] == 2
    assert {"module": "建模力", "entry_count": 2, "asset_count": 1} in summary["overview"]["record_asset_gaps"]

    system = _module(summary, "体系力")
    assert system["asset_count"] == 3
    assert system["usable_asset_count"] == 3
    assert system["mature_asset_count"] == 1
    assert system["reuse_total"] == 2
    assert {"name": "成熟", "count": 1} in system["maturity_distribution"]

    execution = _module(summary, "落地力")
    assert execution["asset_count"] == 2
    assert execution["usable_asset_count"] == 2
    assert execution["mature_asset_count"] == 1
    assert execution["reuse_total"] == 2
    assert execution["status"] == "有优势"

    aesthetic = _module(summary, "审美力")
    assert aesthetic["asset_count"] == 0
    assert aesthetic["status"] == "薄弱"
    assert len(_module(summary, "建模力")["practice_steps"]) == 4


def test_default_practice_paths_are_seeded(client):
    response = client.get("/api/capabilities/practice-paths")
    assert response.status_code == 200
    paths = response.get_json()["data"]

    assert set(paths) >= {"本质力", "建模力", "体系力", "产品力", "审美力", "创造力", "落地力", "AI驾驭力"}
    assert len(paths["本质力"]) == 4
    assert paths["本质力"][0]["title"] == "取样"
    assert paths["AI驾驭力"][3]["title"] == "资产化"


def test_get_capability_practice_path(client):
    response = client.get(f"/api/capabilities/{_module_url('建模力')}/practice-path")
    assert response.status_code == 200
    steps = response.get_json()["data"]

    assert [step["step_order"] for step in steps] == [1, 2, 3, 4]
    assert [step["title"] for step in steps] == ["取样", "归因", "变量", "建模"]


def test_create_update_delete_practice_step_and_normalize_order(client):
    create_response = client.post(
        f"/api/capabilities/{_module_url('建模力')}/practice-steps",
        json={
            "title": "验证",
            "description": "验证模型是否可复用",
            "detail": "用真实项目检验模型。",
        },
    )
    assert create_response.status_code == 200
    created = create_response.get_json()["data"]
    assert created["step_order"] == 5

    patch_response = client.patch(
        f"/api/capabilities/practice-steps/{created['id']}",
        json={
            "title": "验证反馈",
            "description": "验证并记录反馈",
            "detail": "把反馈写回模型迭代记录。",
            "step_order": 2,
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.get_json()["data"]
    assert updated["title"] == "验证反馈"
    assert updated["step_order"] == 2

    titles_after_move = [step["title"] for step in _practice_path(client, "建模力")]
    assert titles_after_move[:3] == ["取样", "验证反馈", "归因"]

    delete_response = client.delete(
        f"/api/capabilities/practice-steps/{updated['id']}"
    )
    assert delete_response.status_code == 200

    steps_after_delete = _practice_path(client, "建模力")
    assert [step["step_order"] for step in steps_after_delete] == [1, 2, 3, 4]
    assert [step["title"] for step in steps_after_delete] == ["取样", "归因", "变量", "建模"]


def test_practice_path_changes_do_not_break_summary(client):
    client.post(
        f"/api/capabilities/{_module_url('体系力')}/practice-steps",
        json={"title": "压测", "description": "压测系统闭环", "detail": "检查链路是否可持续。"},
    )

    response = client.get("/api/capabilities/summary")
    assert response.status_code == 200
    summary = response.get_json()["data"]
    system = _module(summary, "体系力")
    assert system["module"] == "体系力"
    assert len(system["practice_steps"]) == 5
    assert system["practice_steps"][-1]["title"] == "压测"


def test_ai_diagnosis_uses_capability_summary(client, monkeypatch):
    _seed_capability_dashboard(client)

    def fake_chat_json(_system_prompt, user_prompt):
        assert "能力资产看板总览" in user_prompt
        assert "落地力" in user_prompt
        assert "训练路径" in user_prompt
        return {
            "summary": "落地力已经形成复用优势，建模力记录多但资产少。",
            "imbalances": ["建模力需要把记录转成模型资产"],
            "strengths": ["落地力有复用记录"],
            "weaknesses": ["审美力缺少资产"],
            "record_asset_gaps": ["建模力：训练记录多，资产少"],
            "low_reuse_modules": [],
            "focus_modules": ["建模力", "审美力"],
            "suggested_asset_types": ["建模力沉淀模型，审美力沉淀案例复盘"],
            "focus_module": "建模力",
            "focus_action": "把两条训练记录合并成一个模型资产。",
        }

    monkeypatch.setattr(ai_service, "_chat_json", fake_chat_json)

    response = client.post("/api/ai/diagnose-capabilities", json={})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["focus_module"] == "建模力"
    assert data["focus_modules"] == ["建模力", "审美力"]
    assert data["stats"]["建模力"]["total"] == 2
    assert data["asset_overview"]["tagged_assets"] == 6
