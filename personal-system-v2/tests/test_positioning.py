import database


def test_init_db_creates_positioning_tables(client):
    conn = database.get_connection()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    goal_columns = database._table_columns(conn, "goals")
    conn.close()

    assert "positioning_anchor" in tables
    assert "positioning_calibration" in tables
    assert "positioning_goal_action" in tables
    assert "status" in goal_columns


def test_positioning_anchor_upsert_and_persist(client):
    first = database.upsert_positioning_anchor(
        {
            "first_principle": "研究并构建稳定系统",
            "identity_core": "创造者",
            "north_star": "完成一次真实校准闭环",
            "current_stage": "自我验证",
        }
    )
    assert first["first_principle"] == "研究并构建稳定系统"
    assert first["north_star"] == "完成一次真实校准闭环"

    second = database.upsert_positioning_anchor(
        {"north_star": "北极星已更新", "current_stage": "外化企业"}
    )
    assert second["id"] == first["id"]
    assert second["north_star"] == "北极星已更新"
    assert second["first_principle"] == "研究并构建稳定系统"

    stored = database.get_positioning_anchor()
    assert stored["north_star"] == "北极星已更新"


def test_positioning_calibration_create_and_list(client):
    older = database.create_positioning_calibration(
        {
            "calibrated_at": "2026-06-01",
            "cycle": "月度",
            "primary_contradiction": "执行太多，方向太少",
            "conclusion": "先砍低价值目标",
        }
    )
    newer = database.create_positioning_calibration(
        {
            "calibrated_at": "2026-06-20",
            "cycle": "季度",
            "primary_contradiction": "主线目标过多",
            "alignment_review": "两条主线未对齐北极星",
            "conclusion": "保留一条主线",
        }
    )

    rows = database.list_positioning_calibrations()
    assert rows[0]["id"] == newer["id"]
    assert rows[1]["id"] == older["id"]


def test_positioning_goal_action_create_pending(client):
    goal = database.create_goal("旧主线", "当前主线")
    calibration = database.create_positioning_calibration(
        {
            "calibrated_at": "2026-06-26",
            "conclusion": "降级一条主线",
        }
    )

    action = database.create_positioning_goal_action(
        calibration["id"],
        {
            "action_type": "降级目标",
            "target_goal_id": goal["id"],
            "payload": {"type": "月度"},
            "reason": "与北极星不对齐，应降为月度观察",
        },
    )

    assert action["status"] == "pending"
    assert action["payload"]["type"] == "月度"

    detail_actions = database.list_positioning_goal_actions(calibration["id"])
    assert len(detail_actions) == 1
    assert detail_actions[0]["action_type"] == "降级目标"


def test_api_positioning_anchor_and_calibrations(client):
    put_response = client.put(
        "/api/positioning/anchor",
        json={
            "first_principle": "第一性原理",
            "identity_core": "提炼者",
            "north_star": "唯一北极星",
        },
    )
    assert put_response.status_code == 200
    put_payload = put_response.get_json()
    assert put_payload["ok"] is True
    assert put_payload["data"]["north_star"] == "唯一北极星"

    get_response = client.get("/api/positioning/anchor")
    assert get_response.status_code == 200
    assert get_response.get_json()["data"]["first_principle"] == "第一性原理"

    create_response = client.post(
        "/api/positioning/calibrations",
        json={
            "calibrated_at": "2026-06-26",
            "cycle": "触发式",
            "primary_contradiction": "主线发散",
            "conclusion": "收敛到一条主线",
        },
    )
    assert create_response.status_code == 200
    calibration_id = create_response.get_json()["data"]["id"]

    list_response = client.get("/api/positioning/calibrations")
    assert list_response.status_code == 200
    assert list_response.get_json()["data"][0]["id"] == calibration_id

    detail_response = client.get(f"/api/positioning/calibrations/{calibration_id}")
    assert detail_response.status_code == 200
    detail = detail_response.get_json()["data"]
    assert detail["calibration"]["conclusion"] == "收敛到一条主线"
    assert detail["actions"] == []


def test_api_positioning_calibration_validation(client):
    response = client.post("/api/positioning/calibrations", json={"cycle": "月度"})
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_positioning_page_loads(client):
    response = client.get("/positioning")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "战略定位" in html
    assert "定位锚" in html
    assert "新建校准" in html
    assert "目标变更意图" in html
    assert "记录意图，请手动前往目标模块执行对应变更" in html
    assert 'href="/positioning"' in html or "positioning.js" in html


def test_api_create_positioning_action(client):
    calibration = database.create_positioning_calibration(
        {"calibrated_at": "2026-06-26", "conclusion": "测试"}
    )
    goal = database.create_goal("待降级目标", "当前主线")

    response = client.post(
        f"/api/positioning/calibrations/{calibration['id']}/actions",
        json={
            "action_type": "降级目标",
            "target_goal_id": goal["id"],
            "payload": {"type": "月度"},
            "reason": "与北极星不对齐",
        },
    )
    assert response.status_code == 200
    action = response.get_json()["data"]
    assert action["status"] == "pending"
    assert action["payload"]["type"] == "月度"


def test_positioning_calibration_update_and_delete(client):
    calibration = database.create_positioning_calibration(
        {
            "calibrated_at": "2026-06-10",
            "primary_contradiction": "旧矛盾",
            "conclusion": "旧结论",
        }
    )
    database.create_positioning_goal_action(
        calibration["id"],
        {
            "action_type": "淘汰目标",
            "target_goal_id": database.create_goal("待淘汰", "月度")["id"],
            "reason": "不对齐",
        },
    )

    updated = database.update_positioning_calibration(
        calibration["id"],
        {
            "calibrated_at": "2026-06-11",
            "primary_contradiction": "新矛盾",
            "conclusion": "新结论",
        },
    )
    assert updated["primary_contradiction"] == "新矛盾"
    assert updated["conclusion"] == "新结论"

    database.delete_positioning_calibration(calibration["id"])
    assert database.get_positioning_calibration(calibration["id"]) is None
    assert database.list_positioning_goal_actions(calibration["id"]) == []


def test_positioning_goal_action_update_delete_and_status(client):
    goal = database.create_goal("主线 A", "当前主线")
    calibration = database.create_positioning_calibration(
        {"calibrated_at": "2026-06-26", "conclusion": "调整主线"}
    )
    action = database.create_positioning_goal_action(
        calibration["id"],
        {
            "action_type": "降级目标",
            "target_goal_id": goal["id"],
            "payload": {"type": "月度"},
            "reason": "先观察",
        },
    )

    updated = database.update_positioning_goal_action(
        action["id"],
        {
            "action_type": "降级目标",
            "target_goal_id": goal["id"],
            "payload": {"type": "季度"},
            "reason": "改为季度观察",
        },
    )
    assert updated["reason"] == "改为季度观察"
    assert updated["payload"]["type"] == "季度"

    confirmed = database.update_positioning_goal_action_status(
        action["id"], "confirmed"
    )
    assert confirmed["status"] == "confirmed"

    stored_goal = database.get_goal(goal["id"])
    assert stored_goal["type"] == "当前主线"

    database.delete_positioning_goal_action(action["id"])
    assert database.get_positioning_goal_action(action["id"]) is None
    assert stored_goal["type"] == "当前主线"


def test_api_positioning_calibration_update_delete(client):
    create_response = client.post(
        "/api/positioning/calibrations",
        json={
            "calibrated_at": "2026-06-20",
            "primary_contradiction": "待更新",
        },
    )
    calibration_id = create_response.get_json()["data"]["id"]

    update_response = client.put(
        f"/api/positioning/calibrations/{calibration_id}",
        json={
            "calibrated_at": "2026-06-21",
            "primary_contradiction": "已更新",
            "conclusion": "更新结论",
        },
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["primary_contradiction"] == "已更新"

    delete_response = client.delete(
        f"/api/positioning/calibrations/{calibration_id}"
    )
    assert delete_response.status_code == 200
    detail_response = client.get(f"/api/positioning/calibrations/{calibration_id}")
    assert detail_response.status_code == 404


def test_api_positioning_action_update_delete_status(client):
    goal = database.create_goal("关联目标", "季度")
    calibration = database.create_positioning_calibration(
        {"calibrated_at": "2026-06-26", "conclusion": "测试"}
    )
    create_response = client.post(
        f"/api/positioning/calibrations/{calibration['id']}/actions",
        json={
            "action_type": "淘汰目标",
            "target_goal_id": goal["id"],
            "reason": "暂不对齐",
        },
    )
    action_id = create_response.get_json()["data"]["id"]

    update_response = client.put(
        f"/api/positioning/actions/{action_id}",
        json={
            "action_type": "淘汰目标",
            "target_goal_id": goal["id"],
            "reason": "理由已改",
        },
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["reason"] == "理由已改"

    status_response = client.patch(
        f"/api/positioning/actions/{action_id}/status",
        json={"status": "rejected"},
    )
    assert status_response.status_code == 200
    assert status_response.get_json()["data"]["status"] == "rejected"

    delete_response = client.delete(f"/api/positioning/actions/{action_id}")
    assert delete_response.status_code == 200
    assert database.get_goal(goal["id"])["name"] == "关联目标"