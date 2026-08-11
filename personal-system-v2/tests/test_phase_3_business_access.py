import ai_service
import auth_service
from conftest import extract_csrf_token


def _login_session(test_app, user, password, *, change_password=False):
    client = test_app.test_client()
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "identifier": user["username"],
            "password": password,
            "csrf_token": extract_csrf_token(login_page),
        },
    )
    assert response.status_code == 302
    if change_password:
        assert response.headers["Location"] == "/change-password"
        page = client.get("/change-password")
        permanent = f"phase 3 permanent password {user['username']}"
        changed = client.post(
            "/change-password",
            data={
                "current_password": password,
                "new_password": permanent,
                "confirm_password": permanent,
                "csrf_token": extract_csrf_token(page),
            },
        )
        assert changed.status_code == 302
    home = client.get("/")
    assert home.status_code == 200
    return {
        "client": client,
        "csrf": extract_csrf_token(home),
        "user": user,
    }


def _call(session, method, path, payload=None):
    kwargs = {}
    if method != "get":
        kwargs["headers"] = {"X-CSRFToken": session["csrf"]}
    if payload is not None:
        kwargs["json"] = payload
    return getattr(session["client"], method)(path, **kwargs)


def _data(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)
    return response.get_json()["data"]


def _seed_through_api(session, marker, spoof_user_id):
    goal = _data(
        _call(
            session,
            "post",
            "/api/goals",
            {
                "name": f"{marker}_GOAL",
                "type": "当前主线",
                "user_id": spoof_user_id,
            },
        )
    )
    project = _data(
        _call(
            session,
            "post",
            "/api/projects",
            {"goal_id": goal["id"], "name": f"{marker}_PROJECT"},
        )
    )
    task = _data(
        _call(
            session,
            "post",
            "/api/tasks",
            {"project_id": project["id"], "name": f"{marker}_TASK"},
        )
    )
    review = _data(
        _call(
            session,
            "post",
            "/api/reviews",
            {
                "review_date": "2026-08-11",
                "type": "每日",
                "what_done": f"{marker}_REVIEW",
            },
        )
    )
    asset = _data(
        _call(
            session,
            "post",
            "/api/assets",
            {
                "title": f"{marker}_ASSET",
                "asset_type": "通用资产",
                "core_content": f"{marker}_ASSET_CONTENT",
                "source_review_id": review["id"],
            },
        )
    )
    capability_entry = _data(
        _call(
            session,
            "post",
            "/api/capability-entries",
            {
                "module": "本质力",
                "entry_date": "2026-08-11",
                "content": f"{marker}_CAPABILITY",
                "source_project": f"{marker}_PROJECT",
                "level_type": "能力层",
            },
        )
    )
    practice_step = _data(
        _call(
            session,
            "post",
            "/api/capabilities/本质力/practice-steps",
            {"title": f"{marker}_PRACTICE"},
        )
    )
    opportunity = _data(
        _call(
            session,
            "post",
            "/api/opportunities",
            {"name": f"{marker}_OPPORTUNITY"},
        )
    )
    experiment = _data(
        _call(
            session,
            "post",
            "/api/experiments",
            {
                "name": f"{marker}_EXPERIMENT",
                "opportunity_id": opportunity["id"],
            },
        )
    )
    feedback = _data(
        _call(
            session,
            "post",
            "/api/feedback",
            {
                "title": f"{marker}_FEEDBACK",
                "related_type": "experiment",
                "related_id": experiment["id"],
            },
        )
    )
    deliberation = _data(
        _call(
            session,
            "post",
            "/api/deliberations",
            {
                "problem": f"{marker}_DELIBERATION",
                "initial_judgment": f"{marker}_JUDGMENT",
                "reasoning": f"{marker}_REASONING",
                "assumptions": f"{marker}_ASSUMPTIONS",
                "related_type": "project",
                "related_id": project["id"],
            },
        )
    )
    anchor = _data(
        _call(
            session,
            "put",
            "/api/positioning/anchor",
            {"north_star": f"{marker}_ANCHOR"},
        )
    )
    calibration = _data(
        _call(
            session,
            "post",
            "/api/positioning/calibrations",
            {
                "calibrated_at": "2026-08-11",
                "conclusion": f"{marker}_CALIBRATION",
            },
        )
    )
    action = _data(
        _call(
            session,
            "post",
            f"/api/positioning/calibrations/{calibration['id']}/actions",
            {
                "action_type": "淘汰目标",
                "target_goal_id": goal["id"],
                "reason": f"{marker}_ACTION",
            },
        )
    )
    inbox = _data(
        _call(
            session,
            "post",
            "/api/inbox/analyze",
            {"text": f"{marker}_INBOX"},
        )
    )
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
        "inbox_entry_id": inbox["inbox_entry_id"],
        "suggestion_id": inbox["suggestions"][0]["id"],
    }


def _business_snapshot(session, calibration_id):
    endpoints = (
        "/api/goals",
        "/api/projects",
        "/api/tasks",
        "/api/reviews",
        "/api/assets",
        "/api/capability-entries",
        "/api/capabilities/practice-paths",
        "/api/opportunities",
        "/api/experiments",
        "/api/feedback",
        "/api/deliberations",
        "/api/positioning/anchor",
        f"/api/positioning/calibrations/{calibration_id}",
        "/api/inbox",
        "/api/dashboard",
        "/api/value-dashboard",
        "/api/capabilities/summary",
    )
    values = [_data(_call(session, "get", endpoint)) for endpoint in endpoints]
    export_response = _call(session, "get", "/api/export")
    assert export_response.status_code == 200
    values.append(export_response.get_json())
    return repr(values)


def test_three_accounts_use_business_features_without_horizontal_access(
    test_app, monkeypatch
):
    admin_password = "phase 3 admin business password"
    admin = auth_service.bootstrap_admin(
        "businessadmin", "businessadmin@example.com", admin_password
    )
    user_a, password_a = auth_service.create_standard_user(
        "businessa", "businessa@example.com"
    )
    user_b, password_b = auth_service.create_standard_user(
        "businessb", "businessb@example.com"
    )

    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {
            "items": [
                {
                    "target_type": "goal",
                    "title": f"{text}_SUGGESTION",
                    "confidence": 0.9,
                    "suggested_payload": {"name": f"{text}_SUGGESTED_GOAL"},
                }
            ]
        },
    )

    sessions = {
        "admin": _login_session(test_app, admin, admin_password),
        "a": _login_session(
            test_app, user_a, password_a, change_password=True
        ),
        "b": _login_session(
            test_app, user_b, password_b, change_password=True
        ),
    }
    markers = {
        "admin": "ADMIN_SECRET_MARK",
        "a": "USER_A_SECRET_MARK",
        "b": "USER_B_SECRET_MARK",
    }
    graphs = {
        key: _seed_through_api(
            session,
            markers[key],
            sessions["b" if key != "b" else "a"]["user"]["id"],
        )
        for key, session in sessions.items()
    }

    for key, session in sessions.items():
        own_marker = markers[key]
        snapshot = _business_snapshot(
            session, graphs[key]["calibration"]["id"]
        )
        assert own_marker in snapshot
        for other_key, other_marker in markers.items():
            if other_key != key:
                assert other_marker not in snapshot
        assert graphs[key]["goal"]["user_id"] == session["user"]["id"]

    b = sessions["b"]
    a = graphs["a"]
    cross_requests = (
        ("get", f"/api/reviews/{a['review']['id']}", None),
        ("get", f"/api/deliberations/{a['deliberation']['id']}", None),
        ("get", f"/api/assets/{a['asset']['id']}/links", None),
        ("get", f"/api/inbox/{a['inbox_entry_id']}", None),
        (
            "get",
            f"/api/positioning/calibrations/{a['calibration']['id']}",
            None,
        ),
        ("patch", f"/api/goals/{a['goal']['id']}", {"name": "hijack"}),
        ("patch", f"/api/tasks/{a['task']['id']}", {"name": "hijack"}),
        (
            "patch",
            f"/api/feedback/{a['feedback']['id']}",
            {"title": "hijack"},
        ),
        (
            "put",
            f"/api/positioning/actions/{a['action']['id']}",
            {"reason": "hijack"},
        ),
        ("delete", f"/api/projects/{a['project']['id']}", None),
        ("delete", f"/api/assets/{a['asset']['id']}", None),
        (
            "post",
            f"/api/inbox/suggestions/{a['suggestion_id']}/reject",
            {},
        ),
    )
    for method, path, payload in cross_requests:
        response = _call(b, method, path, payload)
        assert response.status_code == 404, (method, path, response.get_data(as_text=True))

    relation_requests = (
        (
            "/api/projects",
            {"goal_id": a["goal"]["id"], "name": "cross project"},
        ),
        (
            "/api/tasks",
            {"project_id": a["project"]["id"], "name": "cross task"},
        ),
        (
            "/api/assets",
            {
                "title": "cross asset",
                "asset_type": "通用资产",
                "core_content": "cross",
                "source_review_id": a["review"]["id"],
            },
        ),
        (
            "/api/experiments",
            {"name": "cross experiment", "opportunity_id": a["opportunity"]["id"]},
        ),
        (
            "/api/feedback",
            {
                "title": "cross feedback",
                "related_type": "project",
                "related_id": a["project"]["id"],
            },
        ),
        (
            "/api/deliberations",
            {
                "problem": "cross deliberation",
                "initial_judgment": "reject",
                "reasoning": "reject",
                "assumptions": "reject",
                "related_type": "project",
                "related_id": a["project"]["id"],
            },
        ),
        (
            f"/api/positioning/calibrations/{graphs['b']['calibration']['id']}/actions",
            {
                "action_type": "淘汰目标",
                "target_goal_id": a["goal"]["id"],
                "reason": "cross action",
            },
        ),
    )
    for path, payload in relation_requests:
        response = _call(b, "post", path, payload)
        assert response.status_code in {400, 404}, response.get_data(as_text=True)

    denied = _call(sessions["a"], "get", "/api/admin/users")
    assert denied.status_code == 403
    assert denied.get_json()["code"] == "admin_required"


def test_new_standard_user_starts_empty_with_only_owned_default_practice_steps(
    test_app
):
    user, temporary_password = auth_service.create_standard_user(
        "emptyuser", "emptyuser@example.com"
    )
    session = _login_session(
        test_app, user, temporary_password, change_password=True
    )
    for endpoint in (
        "/api/goals",
        "/api/projects",
        "/api/tasks",
        "/api/reviews",
        "/api/assets",
        "/api/capability-entries",
        "/api/opportunities",
        "/api/experiments",
        "/api/feedback",
        "/api/deliberations",
        "/api/inbox",
        "/api/positioning/calibrations",
    ):
        assert _data(_call(session, "get", endpoint)) == []
    paths = _data(_call(session, "get", "/api/capabilities/practice-paths"))
    steps = [step for module_steps in paths.values() for step in module_steps]
    assert steps
    assert all(step["user_id"] == user["id"] for step in steps)
