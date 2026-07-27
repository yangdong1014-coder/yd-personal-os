import ai_service
import deliberation_service
from pathlib import Path


INITIAL_PAYLOAD = {
    "title": "销售 AI 介入时机",
    "problem": "销售 AI 应该做实时辅助，还是销售结束后的分析反馈？",
    "context": "团队希望先验证更低阻力的产品形态。",
    "initial_judgment": "目前更应该做事后分析，而不是实时辅助。",
    "reasoning": "销售人员正在面对客户，不适合操作额外界面，实时交互成本高。",
    "assumptions": "销售过程中无法自然使用第二个 AI 界面。",
}

AI_ANALYSIS = {
    "essence": "真正需要判断的是哪种介入方式能以最低使用摩擦产生可验证价值。",
    "counter_argument": "事后分析也可能因为反馈延迟而无法改变行为，实时提示未必需要第二界面。",
    "hidden_assumptions": "假设实时辅助必然要求销售主动操作独立界面。",
    "missing_information": "缺少销售流程中可被自然打断的节点和用户实际操作数据。",
    "validation": "用现有通话转写做一次被动实时提示原型，与事后报告各测试五次。",
}

DECISION_PAYLOAD = {
    "final_judgment": "先验证事后分析，但保留被动实时提示作为对照。",
    "decision": "用同一批通话分别生成事后报告和被动提示原型。",
    "decision_reasoning": "两种方案都能用现有转写低成本验证，不必先开发完整界面。",
    "next_action": "选择五段历史通话，邀请两名销售盲测两种输出。",
}

REVIEW_PAYLOAD = {
    "actual_result": "销售更愿意复盘事后报告，但经理更看重实时风险提示。",
    "judgment_accuracy": "额外主动操作确实降低了销售使用意愿。",
    "judgment_error": "低估了无需操作的被动实时提示价值。",
    "key_variable": "是否要求销售在通话中主动切换界面。",
    "lesson": "应区分主动实时交互与被动实时提示，而不是把实时方案视为一个整体。",
    "principle": "先按用户操作成本拆分方案，再比较介入时机。",
}


def create_deliberation(client, payload=None):
    response = client.post(
        "/api/deliberations",
        json=payload or INITIAL_PAYLOAD,
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def install_ai_success(monkeypatch, result=None):
    monkeypatch.setattr(
        deliberation_service.ai_service,
        "request_structured_completion",
        lambda _system, _user: result or AI_ANALYSIS,
    )


def test_deliberation_pages_and_navigation(client):
    assert client.get("/deliberations").status_code == 200
    new_page = client.get("/deliberations/new").get_data(as_text=True)
    assert "你现在真正需要判断什么？" in new_page
    assert "你现在倾向怎么判断？" in new_page
    assert "这个判断成立，需要哪些事情是真的？" in new_page
    assert 'id="delib-title"' not in new_page
    assert 'id="delib-reasoning" class="textarea" rows="3" required' not in new_page
    assert client.get("/deliberations/99").status_code == 200
    page = client.get("/").get_data(as_text=True)
    assert "推演" in page
    assert "/deliberations" in page
    prompts_page = client.get("/prompts").get_data(as_text=True)
    assert "deliberation" in prompts_page
    prompt_items = client.get(
        "/api/ai/prompts?module=deliberation"
    ).get_json()["data"]
    assert {item["kind"] for item in prompt_items} == {"system", "user"}
    prompt = client.get(
        "/api/ai/prompts/deliberation/challenge"
    ).get_json()["data"]
    assert prompt["system"]
    assert "{initial_judgment}" in prompt["user"]


def test_create_requires_independent_judgment(client):
    response = client.post(
        "/api/deliberations",
        json={"title": "不完整", "problem": "问题"},
    )
    assert response.status_code == 400
    assert "当前判断" in response.get_json()["error"]
    assert client.get("/api/deliberations").get_json()["data"] == []


def test_create_auto_generates_title_and_allows_optional_thinking_fields(client):
    problem = "公司 AI 应用应该继续扩工具，还是集中击穿销售分析闭环？"
    response = client.post(
        "/api/deliberations",
        json={
            "problem": problem,
            "initial_judgment": "先集中击穿销售分析闭环。",
        },
    )
    assert response.status_code == 200
    created = response.get_json()["data"]
    assert created["title"] == problem
    assert created["reasoning"] == ""
    assert created["assumptions"] == ""
    assert created["status"] == "draft"


def test_deliberation_uses_natural_chinese_status_and_stage_labels():
    script = Path("static/js/deliberations.js").read_text(encoding="utf-8")
    for label in ("思考中", "已对抗", "已决策", "已复盘"):
        assert label in script
    for label in (
        "现在，你怎么判断？",
        "所以你决定做什么？",
        "后来发生了什么？",
        "留下一条原则",
    ):
        assert label in script


def test_create_edit_and_reload_draft(client):
    project_goal = client.post(
        "/api/goals",
        json={"name": "验证销售 AI", "type": "季度"},
    ).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": project_goal["id"], "name": "销售 AI MVP"},
    ).get_json()["data"]

    created = create_deliberation(
        client,
        {
            **INITIAL_PAYLOAD,
            "related_type": "project",
            "related_id": project["id"],
        },
    )
    assert created["status"] == "draft"
    assert created["related_type"] == "project"

    response = client.patch(
        f"/api/deliberations/{created['id']}",
        json={"reasoning": "真实工作流测试成本最低。"},
    )
    assert response.status_code == 200
    updated = response.get_json()["data"]
    assert updated["reasoning"] == "真实工作流测试成本最低。"

    reloaded = client.get(
        f"/api/deliberations/{created['id']}"
    ).get_json()["data"]
    assert reloaded == updated


def test_ai_analysis_is_validated_and_persisted(client, monkeypatch):
    install_ai_success(monkeypatch)
    created = create_deliberation(client)

    response = client.post(f"/api/deliberations/{created['id']}/analyze")
    assert response.status_code == 200
    analyzed = response.get_json()["data"]
    assert analyzed["status"] == "analyzed"
    assert analyzed["ai_analysis"] == AI_ANALYSIS

    reloaded = client.get(
        f"/api/deliberations/{created['id']}"
    ).get_json()["data"]
    assert reloaded["ai_analysis"]["validation"] == AI_ANALYSIS["validation"]

    locked = client.patch(
        f"/api/deliberations/{created['id']}",
        json={"problem": "篡改初始问题"},
    )
    assert locked.status_code == 400
    assert "不能修改" in locked.get_json()["error"]


def test_ai_provider_failure_keeps_draft(client, monkeypatch):
    created = create_deliberation(client)

    def fail(_system, _user):
        raise ai_service.AIServiceError("AI 服务暂时不可用，请稍后重试")

    monkeypatch.setattr(
        deliberation_service.ai_service,
        "request_structured_completion",
        fail,
    )
    response = client.post(f"/api/deliberations/{created['id']}/analyze")
    assert response.status_code == 400
    assert "AI 服务暂时不可用" in response.get_json()["error"]
    reloaded = client.get(
        f"/api/deliberations/{created['id']}"
    ).get_json()["data"]
    assert reloaded["status"] == "draft"
    assert reloaded["ai_analysis"] == {}


def test_ai_invalid_structure_keeps_draft(client, monkeypatch):
    install_ai_success(monkeypatch, {"essence": "只有一个字段"})
    created = create_deliberation(client)
    response = client.post(f"/api/deliberations/{created['id']}/analyze")
    assert response.status_code == 400
    assert "counter_argument" in response.get_json()["error"]
    reloaded = client.get(
        f"/api/deliberations/{created['id']}"
    ).get_json()["data"]
    assert reloaded["status"] == "draft"


def test_ai_text_arrays_are_normalized(client, monkeypatch):
    result = {
        **AI_ANALYSIS,
        "hidden_assumptions": [
            "实时辅助必须要求主动操作。",
            "事后反馈一定能及时改变行为。",
        ],
        "missing_information": ["真实工作流观察", "不同提醒形式的干扰数据"],
    }
    install_ai_success(monkeypatch, result)
    created = create_deliberation(client)
    response = client.post(f"/api/deliberations/{created['id']}/analyze")
    assert response.status_code == 200
    analysis = response.get_json()["data"]["ai_analysis"]
    assert analysis["hidden_assumptions"] == (
        "- 实时辅助必须要求主动操作。\n"
        "- 事后反馈一定能及时改变行为。"
    )
    assert analysis["missing_information"].startswith("- 真实工作流观察")


def test_final_decision_requires_analysis_and_saves(client, monkeypatch):
    created = create_deliberation(client)
    blocked = client.patch(
        f"/api/deliberations/{created['id']}/decision",
        json=DECISION_PAYLOAD,
    )
    assert blocked.status_code == 400
    assert "先完成 AI 对抗" in blocked.get_json()["error"]

    install_ai_success(monkeypatch)
    client.post(f"/api/deliberations/{created['id']}/analyze")
    response = client.patch(
        f"/api/deliberations/{created['id']}/decision",
        json=DECISION_PAYLOAD,
    )
    assert response.status_code == 200
    decided = response.get_json()["data"]
    assert decided["status"] == "decided"
    assert decided["final_judgment"] == DECISION_PAYLOAD["final_judgment"]
    assert decided["next_action"] == DECISION_PAYLOAD["next_action"]


def test_result_feedback_completes_review(client, monkeypatch):
    install_ai_success(monkeypatch)
    created = create_deliberation(client)
    client.post(f"/api/deliberations/{created['id']}/analyze")
    client.patch(
        f"/api/deliberations/{created['id']}/decision",
        json=DECISION_PAYLOAD,
    )

    response = client.patch(
        f"/api/deliberations/{created['id']}/review",
        json=REVIEW_PAYLOAD,
    )
    assert response.status_code == 200
    reviewed = response.get_json()["data"]
    assert reviewed["status"] == "reviewed"
    assert reviewed["reviewed"] is True
    assert reviewed["principle"] == REVIEW_PAYLOAD["principle"]

    listed = client.get("/api/deliberations").get_json()["data"]
    assert listed[0]["actual_result"] == REVIEW_PAYLOAD["actual_result"]


def test_delete_deliberation(client):
    created = create_deliberation(client)
    response = client.delete(f"/api/deliberations/{created['id']}")
    assert response.status_code == 200
    assert response.get_json()["data"]["deleted"] is True
    assert client.get(f"/api/deliberations/{created['id']}").status_code == 404
    assert client.get("/api/deliberations").get_json()["data"] == []


def test_export_import_round_trip_includes_deliberations(client, monkeypatch):
    install_ai_success(monkeypatch)
    created = create_deliberation(client)
    client.post(f"/api/deliberations/{created['id']}/analyze")
    client.patch(
        f"/api/deliberations/{created['id']}/decision",
        json=DECISION_PAYLOAD,
    )

    backup = client.get("/api/export").get_json()
    assert backup["deliberations"][0]["id"] == created["id"]
    assert "deliberations" in backup["meta"]["tables"]

    client.delete(f"/api/deliberations/{created['id']}")
    response = client.post("/api/import", json=backup)
    assert response.status_code == 200
    restored = client.get(
        f"/api/deliberations/{created['id']}"
    ).get_json()["data"]
    assert restored["status"] == "decided"
    assert restored["ai_analysis"] == AI_ANALYSIS
