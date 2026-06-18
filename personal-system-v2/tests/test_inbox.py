import json

import ai_service
import database
import inbox_service


def _mock_ai_items():
    return {
        "items": [
            {
                "target_type": "goal",
                "title": "学习 AI 应用",
                "content": "希望系统掌握 AI 工具的使用",
                "confidence": 0.82,
                "reason": "表达了长期方向",
                "suggested_payload": {"name": "学习 AI 应用", "type": "年度"},
            },
            {
                "target_type": "uncertain",
                "title": "模糊想法",
                "content": "可能要做点什么",
                "confidence": 0.4,
                "reason": "信息不足",
                "suggested_payload": {},
            },
        ]
    }


def test_inbox_analyze_empty_text(client):
    response = client.post("/api/inbox/analyze", json={"text": ""})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "空" in payload["error"]


def test_inbox_analyze_creates_entry_and_suggestions(client, monkeypatch):
    monkeypatch.setattr(ai_service, "analyze_inbox_text", lambda text: _mock_ai_items())

    response = client.post(
        "/api/inbox/analyze",
        json={"text": "今天我复盘了 AI 项目推进，明天要梳理 MVP。"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    entry_id = payload["data"]["inbox_entry_id"]
    suggestions = payload["data"]["suggestions"]
    assert entry_id
    assert len(suggestions) == 2
    assert suggestions[0]["target_type"] == "goal"
    assert suggestions[0]["confidence"] == 0.82

    entry = database.get_inbox_entry(entry_id)
    assert entry["status"] == "analyzed"
    assert "AI 项目推进" in entry["raw_text"]


def test_inbox_analyze_invalid_ai_response_no_dirty_suggestions(client, monkeypatch):
    def _bad_ai(_text):
        raise ai_service.AIServiceError("AI 返回格式异常，请重试")

    monkeypatch.setattr(ai_service, "analyze_inbox_text", _bad_ai)

    response = client.post(
        "/api/inbox/analyze",
        json={"text": "一段测试文本"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False

    conn = database.get_connection()
    entries = conn.execute("SELECT * FROM inbox_entries").fetchall()
    suggestions = conn.execute("SELECT * FROM inbox_suggestions").fetchall()
    conn.close()
    assert len(entries) == 1
    assert entries[0]["status"] == "failed"
    assert len(suggestions) == 0


def test_inbox_get_detail(client, monkeypatch):
    monkeypatch.setattr(ai_service, "analyze_inbox_text", lambda text: _mock_ai_items())
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "测试获取详情"},
    ).get_json()["data"]
    entry_id = analyze["inbox_entry_id"]

    response = client.get(f"/api/inbox/{entry_id}")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["entry"]["id"] == entry_id
    assert len(payload["suggestions"]) == 2


def test_inbox_commit_task_suggestion(client, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "task",
                    "title": "梳理 MVP",
                    "content": "梳理 AI 修图项目 MVP 范围",
                    "confidence": 0.9,
                    "reason": "明确行动",
                    "suggested_payload": {"status": "todo"},
                }
            ]
        },
    )

    goal = client.post(
        "/api/goals",
        json={"name": "归档目标", "type": "季度"},
    ).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "归档项目"},
    ).get_json()["data"]

    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "明天梳理 MVP"},
    ).get_json()["data"]
    suggestion = analyze["suggestions"][0]
    suggestion_id = suggestion["id"]

    conn = database.get_connection()
    conn.execute(
        """
        UPDATE inbox_suggestions
        SET suggested_payload = ?
        WHERE id = ?
        """,
        (
            json.dumps(
                {
                    "name": "梳理 MVP",
                    "status": "todo",
                    "project_id": project["id"],
                },
                ensure_ascii=False,
            ),
            suggestion_id,
        ),
    )
    conn.commit()
    conn.close()

    response = client.post(
        "/api/inbox/commit",
        json={"suggestion_ids": [suggestion_id]},
    )
    assert response.status_code == 200
    created = response.get_json()["data"]["created"]
    assert created["tasks"] == 1

    tasks = client.get("/api/tasks").get_json()["data"]
    assert any(task["name"] == "梳理 MVP" for task in tasks)

    updated = database.get_inbox_suggestion(suggestion_id)
    assert updated["status"] == "committed"


def test_inbox_commit_idempotent(client, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "goal",
                    "title": "重复目标",
                    "content": "测试重复提交",
                    "confidence": 0.95,
                    "reason": "目标",
                    "suggested_payload": {"type": "季度"},
                }
            ]
        },
    )
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "创建重复目标"},
    ).get_json()["data"]
    suggestion_id = analyze["suggestions"][0]["id"]

    first = client.post(
        "/api/inbox/commit",
        json={"suggestion_ids": [suggestion_id]},
    ).get_json()["data"]
    assert first["created"]["goals"] == 1

    second = client.post(
        "/api/inbox/commit",
        json={"suggestion_ids": [suggestion_id]},
    ).get_json()["data"]
    assert second["skipped"] == 1
    assert second["created"]["goals"] == 0

    goals = client.get("/api/goals").get_json()["data"]
    assert sum(1 for goal in goals if goal["name"] == "重复目标") == 1


def test_inbox_reject_suggestion(client, monkeypatch):
    monkeypatch.setattr(ai_service, "analyze_inbox_text", lambda text: _mock_ai_items())
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "拒绝测试"},
    ).get_json()["data"]
    suggestion_id = analyze["suggestions"][0]["id"]

    response = client.post(f"/api/inbox/suggestions/{suggestion_id}/reject")
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "rejected"

    updated = database.get_inbox_suggestion(suggestion_id)
    assert updated["status"] == "rejected"


def test_inbox_low_confidence_preserved(client, monkeypatch):
    monkeypatch.setattr(ai_service, "analyze_inbox_text", lambda text: _mock_ai_items())
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "低置信度测试"},
    ).get_json()["data"]
    uncertain = next(
        item for item in analyze["suggestions"] if item["target_type"] == "uncertain"
    )
    assert uncertain["confidence"] == 0.4


def test_inbox_page(client):
    response = client.get("/inbox")
    assert response.status_code == 200
    assert "智能归档" in response.get_data(as_text=True)


def test_inbox_commit_skips_invalid_foreign_keys(client, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "goal",
                    "title": "可入库目标",
                    "content": "目标内容",
                    "confidence": 0.9,
                    "reason": "方向",
                    "suggested_payload": {"type": "季度"},
                },
                {
                    "target_type": "project",
                    "title": "缺 goal 的项目",
                    "content": "项目内容",
                    "confidence": 0.9,
                    "reason": "项目",
                    "suggested_payload": {"goal_id": None},
                },
            ]
        },
    )
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "混合建议"},
    ).get_json()["data"]
    ids = [item["id"] for item in analyze["suggestions"]]

    response = client.post("/api/inbox/commit", json={"suggestion_ids": ids})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["created"]["goals"] == 1
    assert len(data["errors"]) >= 1
    assert any("goal_id" in err for err in data["errors"])


def test_inbox_chain_commit_project_task_parent_ref(client, monkeypatch):
    goal = client.post(
        "/api/goals",
        json={"name": "链式目标", "type": "季度"},
    ).get_json()["data"]
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "project",
                    "title": "AI修图项目",
                    "content": "推进修图项目",
                    "confidence": 0.9,
                    "reason": "多步骤项目",
                    "suggested_payload": {
                        "name": "AI修图项目",
                        "local_ref": "project_ai_retouche",
                    },
                },
                {
                    "target_type": "task",
                    "title": "输出MVP流程图",
                    "content": "明天输出流程图",
                    "confidence": 0.9,
                    "reason": "明确行动",
                    "suggested_payload": {
                        "name": "输出MVP流程图",
                        "parent_ref": "project_ai_retouche",
                        "status": "todo",
                    },
                },
            ]
        },
    )
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "推进 AI 修图项目并输出 MVP 流程图"},
    ).get_json()["data"]
    project_suggestion = next(
        s for s in analyze["suggestions"] if s["target_type"] == "project"
    )
    ids = [s["id"] for s in analyze["suggestions"]]

    response = client.post(
        "/api/inbox/commit",
        json={
            "suggestion_ids": ids,
            "override_payload": [
                {"suggestion_id": project_suggestion["id"], "goal_id": goal["id"]}
            ],
        },
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["created"]["projects"] == 1
    assert data["created"]["tasks"] == 1
    assert not data["errors"]

    tasks = client.get("/api/tasks").get_json()["data"]
    assert any(task["name"] == "输出MVP流程图" for task in tasks)


def test_inbox_override_goal_id_for_project(client, monkeypatch):
    goal = client.post(
        "/api/goals",
        json={"name": "覆盖目标", "type": "年度"},
    ).get_json()["data"]
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "project",
                    "title": "覆盖项目",
                    "content": "项目",
                    "confidence": 0.9,
                    "reason": "项目",
                    "suggested_payload": {"name": "覆盖项目"},
                }
            ]
        },
    )
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "项目测试"},
    ).get_json()["data"]
    suggestion_id = analyze["suggestions"][0]["id"]

    response = client.post(
        "/api/inbox/commit",
        json={
            "suggestion_ids": [suggestion_id],
            "override_payload": [{"suggestion_id": suggestion_id, "goal_id": goal["id"]}],
        },
    )
    assert response.get_json()["data"]["created"]["projects"] == 1


def test_inbox_override_project_id_for_task(client, monkeypatch):
    goal = client.post(
        "/api/goals",
        json={"name": "任务覆盖目标", "type": "季度"},
    ).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "任务覆盖项目"},
    ).get_json()["data"]
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "task",
                    "title": "覆盖任务",
                    "content": "任务",
                    "confidence": 0.9,
                    "reason": "任务",
                    "suggested_payload": {"name": "覆盖任务", "status": "todo"},
                }
            ]
        },
    )
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "任务测试"},
    ).get_json()["data"]
    suggestion_id = analyze["suggestions"][0]["id"]

    response = client.post(
        "/api/inbox/commit",
        json={
            "suggestion_ids": [suggestion_id],
            "override_payload": [
                {"suggestion_id": suggestion_id, "project_id": project["id"]}
            ],
        },
    )
    assert response.get_json()["data"]["created"]["tasks"] == 1


def test_inbox_override_ignores_sensitive_fields(client, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "goal",
                    "title": "原始目标名",
                    "content": "目标",
                    "confidence": 0.9,
                    "reason": "目标",
                    "suggested_payload": {"name": "原始目标名", "type": "季度"},
                }
            ]
        },
    )
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "敏感字段测试"},
    ).get_json()["data"]
    suggestion_id = analyze["suggestions"][0]["id"]

    response = client.post(
        "/api/inbox/commit",
        json={
            "suggestion_ids": [suggestion_id],
            "override_payload": [
                {
                    "suggestion_id": suggestion_id,
                    "name": "被篡改的名称",
                    "type": "当前主线",
                }
            ],
        },
    )
    data = response.get_json()["data"]
    assert data["created"]["goals"] == 1
    goals = client.get("/api/goals").get_json()["data"]
    created = next(g for g in goals if g["name"] == "原始目标名")
    assert created["type"] == "季度"


def test_inbox_list_entries(client, monkeypatch):
    monkeypatch.setattr(ai_service, "analyze_inbox_text", lambda text: _mock_ai_items())
    client.post("/api/inbox/analyze", json={"text": "历史列表测试文本"})
    response = client.get("/api/inbox")
    assert response.status_code == 200
    entries = response.get_json()["data"]
    assert len(entries) >= 1
    entry = entries[0]
    assert "raw_text_summary" in entry
    assert "suggestion_count" in entry
    assert "committed_count" in entry
    assert "pending_count" in entry
    assert "rejected_count" in entry


def test_inbox_history_page(client):
    response = client.get("/inbox/history")
    assert response.status_code == 200
    assert "归档历史" in response.get_data(as_text=True)


def test_inbox_normalize_low_confidence_to_uncertain():
    items = inbox_service._normalize_ai_items(
        [
            {
                "target_type": "task",
                "title": "低置信任务",
                "content": "内容",
                "confidence": 0.5,
                "reason": "测试",
                "suggested_payload": {},
            }
        ]
    )
    assert items[0]["target_type"] == "uncertain"


def test_inbox_commit_review_with_boolean_depositable(client, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "review",
                    "title": "MVP 复盘",
                    "content": "完成了个人成长飞轮 MVP 第一版",
                    "confidence": 0.98,
                    "reason": "复盘记录",
                    "suggested_payload": {
                        "type": "每日",
                        "what_done": "完成 MVP 第一版",
                        "stuck": False,
                        "next_adjust": "补充移动端",
                        "depositable": True,
                    },
                }
            ]
        },
    )
    analyze = client.post(
        "/api/inbox/analyze",
        json={"text": "今天完成了 MVP 第一版"},
    ).get_json()["data"]
    suggestion_id = analyze["suggestions"][0]["id"]

    response = client.post(
        "/api/inbox/commit",
        json={"suggestion_ids": [suggestion_id]},
    )
    assert response.status_code == 200
    created = response.get_json()["data"]["created"]
    assert created["reviews"] == 1

    reviews = client.get("/api/reviews").get_json()["data"]
    review = next(item for item in reviews if item["what_done"] == "完成 MVP 第一版")
    assert review["depositable"] == "完成了个人成长飞轮 MVP 第一版"
    assert review["stuck"] == ""