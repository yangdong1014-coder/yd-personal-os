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