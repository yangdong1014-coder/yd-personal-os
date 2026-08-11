import copy

import auth_service
import database
from test_phase_3_repository_isolation import _seed_owner_graph


def _tenants():
    admin = auth_service.bootstrap_admin(
        "transferadmin",
        "transferadmin@example.com",
        "phase 3 transfer admin password",
    )
    user_a, _ = auth_service.create_standard_user(
        "transfera", "transfera@example.com"
    )
    user_b, _ = auth_service.create_standard_user(
        "transferb", "transferb@example.com"
    )
    return admin, user_a, user_b


def _row_with(rows, field, marker):
    return next(row for row in rows if marker in str(row.get(field) or ""))


def test_export_contains_only_current_users_sixteen_business_tables(test_app):
    admin, user_a, user_b = _tenants()
    _seed_owner_graph(admin["id"], "ADMIN_SECRET_MARK")
    _seed_owner_graph(user_a["id"], "USER_A_SECRET_MARK")
    _seed_owner_graph(user_b["id"], "USER_B_SECRET_MARK")

    payload = database.export_all_data(user_a["id"])

    assert set(payload["meta"]["tables"]) == set(database.PERSONAL_DATA_TABLES)
    assert set(payload) == {"meta", *database.PERSONAL_DATA_TABLES}
    assert "users" not in payload
    serialized = repr(payload)
    assert "USER_A_SECRET_MARK" in serialized
    assert "ADMIN_SECRET_MARK" not in serialized
    assert "USER_B_SECRET_MARK" not in serialized
    for table in database.PERSONAL_DATA_TABLES:
        assert all("user_id" not in row for row in payload[table]), table
    suggestion = payload["inbox_suggestions"][0]
    assert "user_id" not in suggestion["suggested_payload"]


def test_import_collision_remaps_full_graph_without_overwriting_other_owner(test_app):
    admin, user_a, user_b = _tenants()
    source = _seed_owner_graph(user_a["id"], "USER_A_SECRET_MARK")
    _seed_owner_graph(admin["id"], "ADMIN_SECRET_MARK")
    payload = database.export_all_data(user_a["id"])

    spoofed = copy.deepcopy(payload)
    spoofed["users"] = [{"id": user_a["id"], "role": "admin"}]
    for table in database.PERSONAL_DATA_TABLES:
        for row in spoofed[table]:
            row["user_id"] = user_a["id"]
    spoofed["inbox_suggestions"][0]["suggested_payload"]["user_id"] = user_a[
        "id"
    ]

    preview = database.preview_import_data(spoofed, user_b["id"])
    result = database.import_all_data(spoofed, user_b["id"])
    assert preview["will_fail"] == 0
    assert preview["will_import"] == result["created"]
    assert preview["will_update"] == result["updated"]
    assert preview["will_skip"] == result["skipped"]
    assert preview["remapped"] == result["remapped"]
    assert result["remapped"] > 0

    goal = _row_with(database.list_goals(user_b["id"]), "name", "USER_A_SECRET_MARK")
    project = _row_with(
        database.list_projects(user_b["id"]), "name", "USER_A_SECRET_MARK"
    )
    task = _row_with(
        database.list_tasks(user_b["id"]), "name", "USER_A_SECRET_MARK"
    )
    review = _row_with(
        database.list_reviews(user_b["id"]), "what_done", "USER_A_SECRET_MARK"
    )
    asset = _row_with(
        database.list_assets(user_b["id"]), "title", "USER_A_SECRET_MARK"
    )
    opportunity = _row_with(
        database.list_opportunities(user_b["id"]), "name", "USER_A_SECRET_MARK"
    )
    experiment = _row_with(
        database.list_experiments(user_b["id"]), "name", "USER_A_SECRET_MARK"
    )
    feedback = _row_with(
        database.list_feedback_items(user_b["id"]),
        "title",
        "USER_A_SECRET_MARK",
    )
    deliberation = _row_with(
        database.list_deliberations(user_b["id"]),
        "problem",
        "USER_A_SECRET_MARK",
    )
    calibration = _row_with(
        database.list_positioning_calibrations(user_b["id"]),
        "conclusion",
        "USER_A_SECRET_MARK",
    )
    action = _row_with(
        database.list_positioning_goal_actions(calibration["id"], user_b["id"]),
        "reason",
        "USER_A_SECRET_MARK",
    )
    inbox_entry_summary = _row_with(
        database.list_inbox_entries(user_b["id"]),
        "raw_text",
        "USER_A_SECRET_MARK",
    )
    inbox_entry = database.get_inbox_entry(
        inbox_entry_summary["id"], user_b["id"]
    )
    suggestion = database.list_inbox_suggestions(inbox_entry["id"], user_b["id"])[0]

    assert all(
        row["user_id"] == user_b["id"]
        for row in (
            goal,
            project,
            task,
            review,
            asset,
            opportunity,
            experiment,
            feedback,
            deliberation,
            calibration,
            action,
            inbox_entry,
            suggestion,
        )
    )
    assert goal["id"] != source["goal"]["id"]
    assert project["goal_id"] == goal["id"]
    assert task["project_id"] == project["id"]
    assert asset["source_review_id"] == review["id"]
    assert asset["source_id"] == review["id"]
    assert experiment["opportunity_id"] == opportunity["id"]
    assert feedback["related_id"] == experiment["id"]
    assert deliberation["related_id"] == project["id"]
    assert action["calibration_id"] == calibration["id"]
    assert action["target_goal_id"] == goal["id"]
    assert suggestion["inbox_entry_id"] == inbox_entry["id"]
    assert "user_id" not in suggestion["suggested_payload"]

    source_after = database.get_goal(source["goal"]["id"], user_a["id"])
    assert source_after["name"] == "USER_A_SECRET_MARK_GOAL"
    assert "USER_A_SECRET_MARK" not in repr(database.export_all_data(admin["id"]))


def test_import_foreign_id_collision_creates_owned_rows_instead_of_update(test_app):
    admin, user_a, _user_b = _tenants()
    foreign_goal = database.create_goal("USER_A_ORIGINAL", "年度", user_a["id"])
    payload = {
        "meta": {"version": "1.0", "exported_at": "2026-08-11 00:00:00"},
        "goals": [
            {
                "id": foreign_goal["id"],
                "user_id": user_a["id"],
                "name": "ADMIN_IMPORTED_COPY",
                "type": "年度",
                "created_at": "2026-08-11 00:00:00",
            }
        ],
        "projects": [],
        "tasks": [],
        "reviews": [],
        "assets": [],
        "capability_entries": [],
    }

    preview = database.preview_import_data(payload, admin["id"])
    result = database.import_all_data(payload, admin["id"])
    imported = _row_with(
        database.list_goals(admin["id"]), "name", "ADMIN_IMPORTED_COPY"
    )

    assert preview["will_import"] == result["created"] == 1
    assert preview["will_update"] == result["updated"] == 0
    assert result["remapped"] == 1
    assert imported["id"] != foreign_goal["id"]
    assert imported["user_id"] == admin["id"]
    assert database.get_goal(foreign_goal["id"], user_a["id"])["name"] == (
        "USER_A_ORIGINAL"
    )
