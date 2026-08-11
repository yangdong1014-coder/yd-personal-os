import inspect
import io
import zipfile

import pytest

import ai_service
import auth_service
import deliberation_service
import inbox_service
import obsidian_export
import positioning_service
from test_deliberations import AI_ANALYSIS
from test_phase_3_repository_isolation import _seed_owner_graph
import database


SERVICE_OWNER_APIS = (
    (ai_service, "value_chain_ai_advice"),
    (ai_service, "refine_review_to_asset"),
    (ai_service, "optimize_asset"),
    (ai_service, "dashboard_briefing"),
    (ai_service, "decompose_goal_projects"),
    (ai_service, "decompose_project_tasks"),
    (ai_service, "recommend_today_tasks"),
    (ai_service, "classify_asset"),
    (ai_service, "template_asset"),
    (ai_service, "attribute_capability"),
    (ai_service, "diagnose_capabilities"),
    (ai_service, "aggregate_weekly_reviews"),
    (ai_service, "dispatch_dashboard_actions"),
    (deliberation_service, "analyze"),
    (inbox_service, "analyze_text"),
    (inbox_service, "get_inbox_detail"),
    (inbox_service, "commit_suggestions"),
    (inbox_service, "reject_suggestion"),
    (positioning_service, "get_anchor"),
    (positioning_service, "update_anchor"),
    (positioning_service, "create_calibration"),
    (positioning_service, "update_calibration"),
    (positioning_service, "delete_calibration"),
    (positioning_service, "list_calibrations"),
    (positioning_service, "get_calibration_detail"),
    (positioning_service, "create_goal_action"),
    (positioning_service, "update_goal_action"),
    (positioning_service, "delete_goal_action"),
    (positioning_service, "update_goal_action_status"),
    (obsidian_export, "build_obsidian_zip"),
)


@pytest.fixture
def service_tenants(test_app):
    admin = auth_service.bootstrap_admin(
        "serviceadmin",
        "serviceadmin@example.com",
        "phase 3 service admin password",
    )
    user_a, _ = auth_service.create_standard_user(
        "servicea", "servicea@example.com"
    )
    user_b, _ = auth_service.create_standard_user(
        "serviceb", "serviceb@example.com"
    )
    graphs = {
        "admin": _seed_owner_graph(admin["id"], "ADMIN_SECRET_MARK"),
        "a": _seed_owner_graph(user_a["id"], "USER_A_SECRET_MARK"),
        "b": _seed_owner_graph(user_b["id"], "USER_B_SECRET_MARK"),
    }
    graphs["a"]["second_review"] = database.create_review(
        "2026-08-12",
        "每日",
        "USER_A_SECRET_MARK_SECOND_REVIEW",
        "",
        "",
        "",
        user_a["id"],
    )
    return {"admin": admin, "a": user_a, "b": user_b, "graphs": graphs}


def test_database_backed_services_require_explicit_user_id():
    for module, name in SERVICE_OWNER_APIS:
        parameter = inspect.signature(getattr(module, name)).parameters.get("user_id")
        assert parameter is not None, f"{module.__name__}.{name} lacks user_id"
        assert parameter.default is inspect.Parameter.empty, (
            f"{module.__name__}.{name}.user_id must be required"
        )


def _capture_ai_context(monkeypatch, response, callback):
    captured = {}

    def fake_chat(system_prompt, user_prompt):
        captured["text"] = f"{system_prompt}\n{user_prompt}"
        return response

    monkeypatch.setattr(ai_service, "_chat_json", fake_chat)
    callback()
    text = captured["text"]
    assert "USER_A_SECRET_MARK" in text
    assert "ADMIN_SECRET_MARK" not in text
    assert "USER_B_SECRET_MARK" not in text


def test_all_database_backed_ai_contexts_only_include_current_user(
    service_tenants, monkeypatch
):
    a_id = service_tenants["a"]["id"]
    graph = service_tenants["graphs"]["a"]

    calls = (
        (
            {"title": "草稿", "core_content": "内容"},
            lambda: ai_service.refine_review_to_asset(graph["review"]["id"], a_id),
        ),
        (
            {"title": "优化", "core_content": "优化内容"},
            lambda: ai_service.optimize_asset(graph["asset"]["id"], a_id),
        ),
        (
            {"briefing": "简报", "priorities": [], "focus": "聚焦"},
            lambda: ai_service.dashboard_briefing(a_id),
        ),
        (
            {"projects": [{"name": "AI 建议项目", "reason": "验证"}]},
            lambda: ai_service.decompose_goal_projects(graph["goal"]["id"], a_id),
        ),
        (
            {
                "tasks": [
                    {"name": "AI 建议任务", "priority": "中", "reason": "验证"}
                ]
            },
            lambda: ai_service.decompose_project_tasks(
                graph["project"]["id"], a_id
            ),
        ),
        (
            {
                "recommendations": [
                    {"task_id": graph["task"]["id"], "reason": "今日推进"}
                ]
            },
            lambda: ai_service.recommend_today_tasks(a_id),
        ),
        (
            {"asset_type": "通用资产", "capability_tags": ["本质力"]},
            lambda: ai_service.classify_asset(graph["asset"]["id"], a_id),
        ),
        (
            {"title": "模板", "core_content": "模板内容"},
            lambda: ai_service.template_asset(
                graph["asset"]["id"], "方法论", a_id
            ),
        ),
        (
            {"content": "能力建议", "level_type": "能力层"},
            lambda: ai_service.attribute_capability("本质力", a_id),
        ),
        (
            {"summary": "能力诊断"},
            lambda: ai_service.diagnose_capabilities(a_id),
        ),
        (
            {"what_done": "周复盘聚合"},
            lambda: ai_service.aggregate_weekly_reviews(
                [graph["review"]["id"], graph["second_review"]["id"]], a_id
            ),
        ),
        (
            {"mark_today": [{"task_id": graph["task"]["id"]}]},
            lambda: ai_service.dispatch_dashboard_actions(a_id),
        ),
    )
    for response, callback in calls:
        _capture_ai_context(monkeypatch, response, callback)

    for object_type, entity_id in (
        ("opportunity", graph["opportunity"]["id"]),
        ("experiment", graph["experiment"]["id"]),
        ("feedback", graph["feedback"]["id"]),
    ):
        for action in ("advance", "red_team", "audit"):
            _capture_ai_context(
                monkeypatch,
                {
                    "title": "分析",
                    "summary": "结论",
                    "sections": [],
                    "recommendation": "继续验证",
                },
                lambda object_type=object_type, action=action, entity_id=entity_id: (
                    ai_service.value_chain_ai_advice(
                        object_type, action, entity_id, a_id
                    )
                ),
            )


def test_deliberation_ai_and_foreign_ids_fail_before_provider(
    service_tenants, monkeypatch
):
    a_id = service_tenants["a"]["id"]
    b_id = service_tenants["b"]["id"]
    graph = service_tenants["graphs"]["a"]
    captured = {}

    def fake_completion(system_prompt, user_prompt):
        captured["text"] = f"{system_prompt}\n{user_prompt}"
        return AI_ANALYSIS

    monkeypatch.setattr(
        deliberation_service.ai_service,
        "request_structured_completion",
        fake_completion,
    )
    deliberation_service.analyze(graph["deliberation"]["id"], a_id)
    assert "USER_A_SECRET_MARK" in captured["text"]
    assert "ADMIN_SECRET_MARK" not in captured["text"]
    assert "USER_B_SECRET_MARK" not in captured["text"]

    called = False

    def forbidden_provider(*_args):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(ai_service, "_chat_json", forbidden_provider)
    with pytest.raises(ai_service.AIServiceError, match="不存在"):
        ai_service.refine_review_to_asset(graph["review"]["id"], b_id)
    with pytest.raises(ai_service.AIServiceError, match="不存在"):
        ai_service.value_chain_ai_advice(
            "opportunity", "advance", graph["opportunity"]["id"], b_id
        )
    with pytest.raises(deliberation_service.DeliberationServiceError, match="不存在"):
        deliberation_service.analyze(graph["deliberation"]["id"], b_id)
    assert called is False


def test_inbox_and_positioning_services_do_not_cross_owner(service_tenants):
    a_id = service_tenants["a"]["id"]
    b_id = service_tenants["b"]["id"]
    graph = service_tenants["graphs"]["a"]

    with pytest.raises(inbox_service.InboxServiceError, match="不存在"):
        inbox_service.get_inbox_detail(graph["inbox_entry"]["id"], b_id)
    result = inbox_service.commit_suggestions(
        [graph["suggestion"]["id"]], b_id
    )
    assert not any(result["created"].values())
    assert result["errors"] == [f"建议 #{graph['suggestion']['id']} 不存在"]

    with pytest.raises(positioning_service.PositioningServiceError, match="不存在"):
        positioning_service.get_calibration_detail(
            graph["calibration"]["id"], b_id
        )
    with pytest.raises(positioning_service.PositioningServiceError, match="不存在"):
        positioning_service.update_goal_action(
            graph["action"]["id"], {"reason": "hijack"}, b_id
        )


def test_obsidian_zip_contains_only_current_users_content(service_tenants):
    a_id = service_tenants["a"]["id"]
    body = obsidian_export.build_obsidian_zip(a_id)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        exported = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".md")
        )
    assert "USER_A_SECRET_MARK" in exported
    assert "ADMIN_SECRET_MARK" not in exported
    assert "USER_B_SECRET_MARK" not in exported
