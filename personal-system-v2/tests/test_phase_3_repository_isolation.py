import inspect

import pytest

import auth_repository
import auth_service
import database
from conftest import extract_csrf_token


REPOSITORY_OWNER_APIS = (
    "create_deliberation",
    "list_deliberations",
    "get_deliberation",
    "update_deliberation",
    "save_deliberation_analysis",
    "save_deliberation_decision",
    "save_deliberation_review",
    "delete_deliberation",
    "create_goal",
    "update_goal",
    "list_goals",
    "get_goal",
    "create_project",
    "get_project",
    "update_project",
    "list_projects",
    "create_task",
    "list_tasks",
    "update_task",
    "update_task_status",
    "update_task_today_progress",
    "get_mainline_goal",
    "list_active_projects",
    "list_today_progress_tasks",
    "get_dashboard",
    "create_review",
    "list_reviews",
    "get_review",
    "create_asset",
    "create_asset_from_feedback",
    "get_asset",
    "list_assets",
    "update_asset",
    "increment_asset_reuse",
    "create_capability_entry",
    "list_capability_entries",
    "list_capability_practice_paths",
    "get_capability_practice_path",
    "create_capability_practice_step",
    "update_capability_practice_step",
    "delete_capability_practice_step",
    "get_capability_summary",
    "delete_goal",
    "delete_project",
    "delete_task",
    "delete_review",
    "delete_asset",
    "delete_capability_entry",
    "list_opportunities",
    "get_opportunity",
    "create_opportunity",
    "update_opportunity",
    "delete_opportunity",
    "list_experiments",
    "get_experiment",
    "create_experiment",
    "update_experiment",
    "delete_experiment",
    "list_feedback_items",
    "get_feedback_item",
    "create_feedback_item",
    "update_feedback_item",
    "delete_feedback_item",
    "get_opportunity_links",
    "get_experiment_links",
    "get_feedback_links",
    "get_asset_links",
    "get_value_dashboard",
    "create_inbox_entry",
    "update_inbox_entry_status",
    "get_inbox_entry",
    "list_inbox_entries",
    "create_inbox_suggestions",
    "list_inbox_suggestions",
    "get_inbox_suggestion",
    "reject_inbox_suggestion",
    "commit_inbox_suggestions",
    "get_positioning_anchor",
    "upsert_positioning_anchor",
    "create_positioning_calibration",
    "update_positioning_calibration",
    "delete_positioning_calibration",
    "list_positioning_calibrations",
    "get_positioning_calibration",
    "list_positioning_goal_actions",
    "get_positioning_goal_action",
    "update_positioning_goal_action",
    "delete_positioning_goal_action",
    "update_positioning_goal_action_status",
    "create_positioning_goal_action",
)


@pytest.fixture
def tenants(test_app):
    admin = auth_service.bootstrap_admin(
        "phase3admin", "phase3admin@example.com", "phase 3 admin password"
    )
    user_a, password_a = auth_service.create_standard_user(
        "phase3a", "phase3a@example.com"
    )
    user_b, password_b = auth_service.create_standard_user(
        "phase3b", "phase3b@example.com"
    )
    return {
        "admin": admin,
        "a": user_a,
        "b": user_b,
        "password_a": password_a,
        "password_b": password_b,
    }


def _seed_owner_graph(user_id, marker):
    goal = database.create_goal(f"{marker}_GOAL", "当前主线", user_id)
    project = database.create_project(
        goal["id"], f"{marker}_PROJECT", user_id=user_id
    )
    task = database.create_task(
        project["id"], f"{marker}_TASK", user_id=user_id
    )
    review = database.create_review(
        "2026-08-11", "每日", f"{marker}_REVIEW", "", "", "", user_id
    )
    asset = database.create_asset(
        f"{marker}_ASSET",
        "通用资产",
        capability_tags=["本质力"],
        core_content=f"{marker}_ASSET_CONTENT",
        source_review_id=review["id"],
        user_id=user_id,
    )
    capability_entry = database.create_capability_entry(
        "本质力",
        "2026-08-11",
        f"{marker}_CAPABILITY",
        f"{marker}_PROJECT",
        "能力层",
        user_id,
    )
    practice_step = database.create_capability_practice_step(
        "本质力", f"{marker}_STEP", user_id=user_id
    )
    opportunity = database.create_opportunity(
        {"name": f"{marker}_OPPORTUNITY"}, user_id
    )
    experiment = database.create_experiment(
        {
            "name": f"{marker}_EXPERIMENT",
            "opportunity_id": opportunity["id"],
        },
        user_id,
    )
    feedback = database.create_feedback_item(
        {
            "title": f"{marker}_FEEDBACK",
            "related_type": "experiment",
            "related_id": experiment["id"],
        },
        user_id,
    )
    deliberation = database.create_deliberation(
        {
            "problem": f"{marker}_DELIBERATION",
            "initial_judgment": f"{marker}_JUDGMENT",
            "reasoning": f"{marker}_REASONING",
            "assumptions": f"{marker}_ASSUMPTIONS",
            "related_type": "project",
            "related_id": project["id"],
        },
        user_id,
    )
    anchor = database.upsert_positioning_anchor(
        {"north_star": f"{marker}_ANCHOR"}, user_id
    )
    calibration = database.create_positioning_calibration(
        {
            "calibrated_at": "2026-08-11",
            "conclusion": f"{marker}_CALIBRATION",
        },
        user_id,
    )
    action = database.create_positioning_goal_action(
        calibration["id"],
        {
            "action_type": "淘汰目标",
            "target_goal_id": goal["id"],
            "reason": f"{marker}_ACTION",
        },
        user_id,
    )
    inbox_entry = database.create_inbox_entry(
        f"{marker}_INBOX", user_id=user_id
    )
    suggestion = database.create_inbox_suggestions(
        inbox_entry["id"],
        [
            {
                "target_type": "goal",
                "title": f"{marker}_SUGGESTION",
                "suggested_payload": {
                    "name": f"{marker}_SUGGESTED_GOAL",
                    "user_id": 999999,
                },
            }
        ],
        user_id,
    )[0]
    return {
        "goal": goal,
        "project": project,
        "task": task,
        "review": review,
        "asset": asset,
        "capability_entry": capability_entry,
        "practice_step": practice_step,
        "opportunity": opportunity,
        "experiment": experiment,
        "feedback": feedback,
        "deliberation": deliberation,
        "anchor": anchor,
        "calibration": calibration,
        "action": action,
        "inbox_entry": inbox_entry,
        "suggestion": suggestion,
    }


def _assert_only_marker(items, field, marker):
    assert items
    assert all(marker in str(item.get(field) or "") for item in items)


def test_repository_business_apis_require_explicit_user_id():
    for name in REPOSITORY_OWNER_APIS:
        function = getattr(database, name)
        parameter = inspect.signature(function).parameters.get("user_id")
        assert parameter is not None, f"{name} lacks user_id"
        assert parameter.default is inspect.Parameter.empty, (
            f"{name}.user_id must not have a default"
        )

    with pytest.raises(TypeError):
        database.list_goals()


def test_all_sixteen_tables_helpers_and_aggregates_are_owner_scoped(tenants):
    graphs = {
        key: _seed_owner_graph(user["id"], f"{key.upper()}_SECRET_MARK")
        for key, user in (
            ("admin", tenants["admin"]),
            ("a", tenants["a"]),
            ("b", tenants["b"]),
        )
    }
    a_id = tenants["a"]["id"]
    marker = "A_SECRET_MARK"

    extra_goal = database.create_goal(f"{marker}_GOAL_RECENT", "当前主线", a_id)
    extra_project = database.create_project(
        extra_goal["id"], f"{marker}_PROJECT_RECENT", user_id=a_id
    )
    extra_task = database.create_task(
        extra_project["id"], f"{marker}_TASK_TODAY", user_id=a_id
    )
    database.create_task(
        extra_project["id"], f"{marker}_TASK_SECOND", user_id=a_id
    )
    database.update_task_today_progress(extra_task["id"], True, a_id)
    high_scores = {field: 5 for field in database.VALUE_SCORE_FIELDS}
    database.create_opportunity(
        {"name": f"{marker}_RANK_ONE", **high_scores}, a_id
    )
    recent_inbox = database.create_inbox_entry(
        f"{marker}_INBOX_RECENT", user_id=a_id
    )

    _assert_only_marker(database.list_goals(a_id), "name", marker)
    _assert_only_marker(database.list_projects(a_id), "name", marker)
    _assert_only_marker(database.list_tasks(a_id), "name", marker)
    _assert_only_marker(database.list_reviews(a_id), "what_done", marker)
    _assert_only_marker(database.list_assets(a_id), "title", marker)
    _assert_only_marker(
        database.list_capability_entries(a_id), "content", marker
    )
    _assert_only_marker(database.list_opportunities(a_id), "name", marker)
    _assert_only_marker(database.list_experiments(a_id), "name", marker)
    _assert_only_marker(database.list_feedback_items(a_id), "title", marker)
    _assert_only_marker(
        database.list_deliberations(a_id), "problem", marker
    )
    _assert_only_marker(
        database.list_positioning_calibrations(a_id), "conclusion", marker
    )
    assert marker in database.get_positioning_anchor(a_id)["north_star"]
    assert marker in database.list_positioning_goal_actions(
        graphs["a"]["calibration"]["id"], a_id
    )[0]["reason"]
    _assert_only_marker(database.list_inbox_entries(a_id), "raw_text", marker)
    assert marker in database.list_inbox_suggestions(
        graphs["a"]["inbox_entry"]["id"], a_id
    )[0]["title"]
    assert "user_id" not in graphs["a"]["suggestion"]["suggested_payload"]

    dashboard = database.get_dashboard(a_id)
    assert dashboard["dashboard_summary"] == {
        "goal_count": 2,
        "project_count": 2,
        "task_count": 3,
        "open_task_count": 3,
        "today_task_count": 1,
        "mainline_goal_id": extra_goal["id"],
        "focus_project_id": extra_project["id"],
    }
    assert database.get_mainline_goal(tenants["admin"]["id"])["id"] == graphs[
        "admin"
    ]["goal"]["id"]
    assert database.get_mainline_goal(tenants["b"]["id"])["id"] == graphs["b"][
        "goal"
    ]["id"]
    assert [item["id"] for item in database.list_today_progress_tasks(a_id)] == [
        extra_task["id"]
    ]
    assert {item["id"] for item in database.list_active_projects(a_id)} == {
        graphs["a"]["project"]["id"],
        extra_project["id"],
    }
    assert database.list_projects(a_id, graphs["a"]["goal"]["id"])[0][
        "id"
    ] == graphs["a"]["project"]["id"]
    assert database.list_assets(a_id, tag="本质力")[0]["id"] == graphs["a"][
        "asset"
    ]["id"]
    assert database.list_opportunities(a_id)[0]["name"] == f"{marker}_RANK_ONE"
    assert database.list_inbox_entries(a_id)[0]["id"] == recent_inbox["id"]
    assert database.list_inbox_entries(a_id)[1]["suggestion_count"] == 1
    assert len(database.get_value_dashboard(a_id)["chains"]) == 2
    capability = database.get_capability_summary(a_id)
    assert capability["overview"]["total_assets"] == 1
    assert capability["overview"]["total_entries"] == 1
    assert any(
        step["title"] == f"{marker}_STEP"
        for step in database.get_capability_practice_path("本质力", a_id)
    )

    for other in (tenants["admin"]["id"], tenants["b"]["id"]):
        serialized = repr(
            {
                "dashboard": database.get_dashboard(other),
                "value": database.get_value_dashboard(other),
                "capability": database.get_capability_summary(other),
                "inbox": database.list_inbox_entries(other),
            }
        )
        assert marker not in serialized


def test_cross_owner_crud_and_relationships_fail_closed(tenants):
    a_id = tenants["a"]["id"]
    b_id = tenants["b"]["id"]
    a = _seed_owner_graph(a_id, "USER_A_SECRET_MARK")
    b = _seed_owner_graph(b_id, "USER_B_SECRET_MARK")

    assert database.get_goal(a["goal"]["id"], b_id) is None
    assert database.get_project(a["project"]["id"], b_id) is None
    assert database.get_review(a["review"]["id"], b_id) is None
    assert database.get_asset(a["asset"]["id"], b_id) is None
    assert database.get_opportunity(a["opportunity"]["id"], b_id) is None
    assert database.get_experiment(a["experiment"]["id"], b_id) is None
    assert database.get_feedback_item(a["feedback"]["id"], b_id) is None
    assert database.get_deliberation(a["deliberation"]["id"], b_id) is None
    assert database.get_inbox_entry(a["inbox_entry"]["id"], b_id) is None
    assert database.get_inbox_suggestion(a["suggestion"]["id"], b_id) is None
    assert database.get_positioning_calibration(a["calibration"]["id"], b_id) is None
    assert database.get_positioning_goal_action(a["action"]["id"], b_id) is None

    cross_updates = (
        lambda: database.update_goal(a["goal"]["id"], {"name": "hijack"}, b_id),
        lambda: database.update_project(a["project"]["id"], {"name": "hijack"}, b_id),
        lambda: database.update_task(a["task"]["id"], {"name": "hijack"}, b_id),
        lambda: database.update_asset(
            a["asset"]["id"], user_id=b_id, summary="hijack"
        ),
        lambda: database.update_capability_practice_step(
            a["practice_step"]["id"], user_id=b_id, title="hijack"
        ),
        lambda: database.update_opportunity(
            a["opportunity"]["id"], {"name": "hijack"}, b_id
        ),
        lambda: database.update_experiment(
            a["experiment"]["id"], {"name": "hijack"}, b_id
        ),
        lambda: database.update_feedback_item(
            a["feedback"]["id"], {"title": "hijack"}, b_id
        ),
        lambda: database.update_deliberation(
            a["deliberation"]["id"], {"title": "hijack"}, b_id
        ),
        lambda: database.update_inbox_entry_status(
            a["inbox_entry"]["id"], "failed", b_id
        ),
        lambda: database.reject_inbox_suggestion(a["suggestion"]["id"], b_id),
        lambda: database.update_positioning_calibration(
            a["calibration"]["id"], {"conclusion": "hijack"}, b_id
        ),
        lambda: database.update_positioning_goal_action(
            a["action"]["id"], {"reason": "hijack"}, b_id
        ),
    )
    for operation in cross_updates:
        with pytest.raises(ValueError):
            operation()

    cross_deletes = (
        lambda: database.delete_goal(a["goal"]["id"], b_id),
        lambda: database.delete_project(a["project"]["id"], b_id),
        lambda: database.delete_task(a["task"]["id"], b_id),
        lambda: database.delete_review(a["review"]["id"], b_id),
        lambda: database.delete_asset(a["asset"]["id"], b_id),
        lambda: database.delete_capability_entry(
            a["capability_entry"]["id"], b_id
        ),
        lambda: database.delete_capability_practice_step(
            a["practice_step"]["id"], b_id
        ),
        lambda: database.delete_opportunity(a["opportunity"]["id"], b_id),
        lambda: database.delete_experiment(a["experiment"]["id"], b_id),
        lambda: database.delete_feedback_item(a["feedback"]["id"], b_id),
        lambda: database.delete_deliberation(a["deliberation"]["id"], b_id),
        lambda: database.delete_positioning_calibration(
            a["calibration"]["id"], b_id
        ),
        lambda: database.delete_positioning_goal_action(a["action"]["id"], b_id),
    )
    for operation in cross_deletes:
        with pytest.raises(ValueError):
            operation()

    cross_relations = (
        lambda: database.create_project(
            a["goal"]["id"], "cross project", user_id=b_id
        ),
        lambda: database.create_task(
            a["project"]["id"], "cross task", user_id=b_id
        ),
        lambda: database.create_asset(
            "cross review asset",
            "通用资产",
            core_content="cross",
            source_review_id=a["review"]["id"],
            user_id=b_id,
        ),
        lambda: database.create_asset(
            "cross feedback asset",
            "通用资产",
            core_content="cross",
            source_type="feedback",
            source_id=a["feedback"]["id"],
            user_id=b_id,
        ),
        lambda: database.create_experiment(
            {"name": "cross experiment", "opportunity_id": a["opportunity"]["id"]},
            b_id,
        ),
        lambda: database.create_feedback_item(
            {
                "title": "cross feedback",
                "related_type": "project",
                "related_id": a["project"]["id"],
            },
            b_id,
        ),
        lambda: database.create_deliberation(
            {
                "problem": "cross deliberation",
                "initial_judgment": "reject",
                "related_type": "project",
                "related_id": a["project"]["id"],
            },
            b_id,
        ),
        lambda: database.create_positioning_goal_action(
            b["calibration"]["id"],
            {
                "action_type": "淘汰目标",
                "target_goal_id": a["goal"]["id"],
                "reason": "cross action",
            },
            b_id,
        ),
        lambda: database.create_inbox_suggestions(
            a["inbox_entry"]["id"], [], b_id
        ),
    )
    for operation in cross_relations:
        with pytest.raises(ValueError):
            operation()

    cross_suggestion = database.create_inbox_suggestions(
        b["inbox_entry"]["id"],
        [
            {
                "target_type": "project",
                "title": "cross inbox project",
                "suggested_payload": {
                    "goal_id": a["goal"]["id"],
                    "user_id": a_id,
                },
            }
        ],
        b_id,
    )[0]
    assert cross_suggestion["user_id"] == b_id
    assert "user_id" not in cross_suggestion["suggested_payload"]
    result = database.commit_inbox_suggestions([cross_suggestion["id"]], b_id)
    assert result["created"]["projects"] == 0
    assert result["errors"]

    foreign_result = database.commit_inbox_suggestions(
        [a["suggestion"]["id"]], b_id
    )
    assert foreign_result["created"]["goals"] == 0
    assert foreign_result["errors"] == [f"建议 #{a['suggestion']['id']} 不存在"]
    assert "hijack" not in repr(database.list_goals(a_id))


def test_parent_delete_clears_owned_soft_links_without_touching_other_owner(
    tenants,
):
    a_id = tenants["a"]["id"]
    b_id = tenants["b"]["id"]
    a = _seed_owner_graph(a_id, "DELETE_USER_A_MARK")
    b = _seed_owner_graph(b_id, "DELETE_USER_B_MARK")
    project_feedback = database.create_feedback_item(
        {
            "title": "DELETE_USER_A_MARK_PROJECT_FEEDBACK",
            "related_type": "project",
            "related_id": a["project"]["id"],
        },
        a_id,
    )

    result = database.delete_goal(a["goal"]["id"], a_id)

    assert result["cascaded"] == {"projects": 1, "tasks": 1}
    assert result["cleared"]["feedback_items"] == 1
    assert result["cleared"]["deliberations"] == 1
    assert result["cleared"]["positioning_goal_action"] == 1
    assert database.get_goal(a["goal"]["id"], a_id) is None
    assert database.get_project(a["project"]["id"], a_id) is None
    cleared_feedback = database.get_feedback_item(project_feedback["id"], a_id)
    assert cleared_feedback["related_type"] == ""
    assert cleared_feedback["related_id"] is None
    cleared_deliberation = database.get_deliberation(
        a["deliberation"]["id"], a_id
    )
    assert cleared_deliberation["related_type"] == ""
    assert cleared_deliberation["related_id"] is None
    assert database.get_positioning_goal_action(a["action"]["id"], a_id)[
        "target_goal_id"
    ] is None

    assert database.get_goal(b["goal"]["id"], b_id)["name"] == (
        "DELETE_USER_B_MARK_GOAL"
    )
    assert database.get_project(b["project"]["id"], b_id)["name"] == (
        "DELETE_USER_B_MARK_PROJECT"
    )
    assert database.get_deliberation(b["deliberation"]["id"], b_id)[
        "related_id"
    ] == b["project"]["id"]
    assert database.get_positioning_goal_action(b["action"]["id"], b_id)[
        "target_goal_id"
    ] == b["goal"]["id"]


def test_admin_does_not_bypass_owner_and_request_user_id_is_ignored(client):
    admin = auth_repository.get_user_by_username("testadmin")
    user_a, _ = auth_service.create_standard_user(
        "spoofa", "spoofa@example.com"
    )
    a = _seed_owner_graph(user_a["id"], "USER_A_SECRET_MARK")

    response = client.post(
        "/api/goals",
        json={
            "name": "ADMIN_SECRET_MARK_GOAL",
            "type": "年度",
            "user_id": user_a["id"],
        },
    )
    assert response.status_code == 200
    created = response.get_json()["data"]
    assert created["user_id"] == admin["id"]
    assert all(
        item["user_id"] == admin["id"]
        for item in client.get("/api/goals").get_json()["data"]
    )
    assert "USER_A_SECRET_MARK" not in repr(
        client.get("/api/dashboard").get_json()["data"]
    )

    deliberation_id = a["deliberation"]["id"]
    assert client.get(f"/api/deliberations/{deliberation_id}").status_code == 404
    assert client.patch(
        f"/api/deliberations/{deliberation_id}", json={"title": "hijack"}
    ).status_code == 404
    assert client.delete(f"/api/deliberations/{deliberation_id}").status_code == 404
    assert client.patch(
        f"/api/goals/{a['goal']['id']}", json={"name": "hijack"}
    ).status_code == 404
    assert client.delete(f"/api/goals/{a['goal']['id']}").status_code == 404
    assert database.get_deliberation(deliberation_id, user_a["id"])[
        "title"
    ] != "hijack"


def _login(client, identifier, password):
    login_page = client.get("/login")
    return client.post(
        "/login",
        data={
            "identifier": identifier,
            "password": password,
            "csrf_token": extract_csrf_token(login_page),
        },
    )


def test_reinitialization_keeps_owners_and_phase_3_gate_open(test_app):
    auth_service.bootstrap_admin(
        "gateadmin", "gateadmin@example.com", "phase 3 gate admin password"
    )
    user_a, temporary_password = auth_service.create_standard_user(
        "gateuser", "gateuser@example.com"
    )
    graph = _seed_owner_graph(user_a["id"], "PERSISTENT_USER_A_MARK")

    database.init_db()
    assert database.get_goal(graph["goal"]["id"], user_a["id"])["user_id"] == user_a[
        "id"
    ]
    conn = database.get_connection()
    try:
        for table in database.PERSONAL_DATA_TABLES:
            owners = {
                row["user_id"]
                for row in conn.execute(
                    f'SELECT DISTINCT user_id FROM "{table}"'
                ).fetchall()
            }
            assert owners <= {
                auth_repository.get_user_by_username("gateadmin")["id"],
                user_a["id"],
            }
    finally:
        conn.close()

    browser = test_app.test_client()
    assert _login(browser, user_a["username"], temporary_password).status_code == 302
    change_page = browser.get("/change-password")
    permanent_password = "phase 3 permanent user password"
    changed = browser.post(
        "/change-password",
        data={
            "current_password": temporary_password,
            "new_password": permanent_password,
            "confirm_password": permanent_password,
            "csrf_token": extract_csrf_token(change_page),
        },
    )
    assert changed.status_code == 302
    allowed = browser.get("/api/goals")
    assert allowed.status_code == 200
    assert {
        item["id"] for item in allowed.get_json()["data"]
    } == {graph["goal"]["id"]}
