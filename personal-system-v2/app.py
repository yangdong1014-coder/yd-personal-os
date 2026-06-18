import json

from flask import Flask, Response, jsonify, render_template, request

import ai_service
import config
import database

app = Flask(__name__)


@app.context_processor
def inject_globals():
    return {"ai_enabled": config.is_ai_enabled()}

NAV_ITEMS = [
    {"endpoint": "index", "label": "首页", "path": "/"},
    {"endpoint": "goals", "label": "目标", "path": "/goals"},
    {"endpoint": "tasks", "label": "任务", "path": "/tasks"},
    {"endpoint": "reviews", "label": "复盘", "path": "/reviews"},
    {"endpoint": "assets", "label": "资产", "path": "/assets"},
    {"endpoint": "capabilities", "label": "能力", "path": "/capabilities"},
]


def _error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


@app.route("/")
def index():
    return render_template("index.html", active_page="index", nav_items=NAV_ITEMS)


@app.route("/goals")
def goals():
    return render_template(
        "goals.html",
        active_page="goals",
        nav_items=NAV_ITEMS,
        goal_types=database.GOAL_TYPES,
    )


@app.route("/tasks")
def tasks():
    return render_template(
        "tasks.html",
        active_page="tasks",
        nav_items=NAV_ITEMS,
        task_statuses=database.TASK_STATUSES,
    )


@app.route("/reviews")
def reviews():
    return render_template(
        "reviews.html",
        active_page="reviews",
        nav_items=NAV_ITEMS,
        review_types=database.REVIEW_TYPES,
        capability_modules=database.CAPABILITY_MODULES,
    )


@app.route("/assets")
def assets():
    return render_template(
        "assets.html",
        active_page="assets",
        nav_items=NAV_ITEMS,
        asset_types=database.ASSET_TYPES,
        capability_modules=database.CAPABILITY_MODULES,
    )


@app.route("/capabilities")
def capabilities():
    return render_template(
        "capabilities.html",
        active_page="capabilities",
        nav_items=NAV_ITEMS,
        capability_modules=database.CAPABILITY_MODULES,
        capability_layers=database.CAPABILITY_LAYERS,
        level_types=database.LEVEL_TYPES,
    )


@app.route("/api/goals", methods=["GET"])
def api_list_goals():
    return jsonify({"ok": True, "data": database.list_goals()})


@app.route("/api/goals", methods=["POST"])
def api_create_goal():
    payload = request.get_json(silent=True) or {}
    try:
        goal = database.create_goal(payload.get("name", ""), payload.get("type", ""))
        return jsonify({"ok": True, "data": goal})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/goals/<int:goal_id>", methods=["PATCH"])
def api_update_goal(goal_id):
    payload = request.get_json(silent=True) or {}
    try:
        goal = database.update_goal(goal_id, payload.get("type", ""))
        return jsonify({"ok": True, "data": goal})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    goal_id = request.args.get("goal_id", type=int)
    return jsonify({"ok": True, "data": database.list_projects(goal_id)})


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    payload = request.get_json(silent=True) or {}
    try:
        project = database.create_project(
            payload.get("goal_id"), payload.get("name", "")
        )
        return jsonify({"ok": True, "data": project})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/tasks", methods=["GET"])
def api_list_tasks():
    return jsonify({"ok": True, "data": database.list_tasks()})


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    payload = request.get_json(silent=True) or {}
    try:
        task = database.create_task(payload.get("project_id"), payload.get("name", ""))
        return jsonify({"ok": True, "data": task})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/tasks/<int:task_id>/status", methods=["PATCH"])
def api_update_task_status(task_id):
    payload = request.get_json(silent=True) or {}
    try:
        task = database.update_task_status(task_id, payload.get("status", ""))
        return jsonify({"ok": True, "data": task})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/tasks/<int:task_id>/today-progress", methods=["PATCH"])
def api_update_task_today_progress(task_id):
    payload = request.get_json(silent=True) or {}
    try:
        task = database.update_task_today_progress(
            task_id, bool(payload.get("enabled"))
        )
        return jsonify({"ok": True, "data": task})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    return jsonify({"ok": True, "data": database.get_dashboard()})


@app.route("/api/export", methods=["GET"])
def api_export():
    try:
        payload = database.export_all_data()
        filename = database.backup_filename()
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            body,
            mimetype="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except database.ExportError as exc:
        return _error(str(exc), 500)


@app.route("/api/reviews", methods=["GET"])
def api_list_reviews():
    return jsonify({"ok": True, "data": database.list_reviews()})


@app.route("/api/reviews", methods=["POST"])
def api_create_review():
    payload = request.get_json(silent=True) or {}
    try:
        review = database.create_review(
            payload.get("review_date", ""),
            payload.get("type", ""),
            payload.get("what_done", ""),
            payload.get("stuck", ""),
            payload.get("next_adjust", ""),
            payload.get("depositable", ""),
        )
        return jsonify({"ok": True, "data": review})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/reviews/<int:review_id>", methods=["GET"])
def api_get_review(review_id):
    review = database.get_review(review_id)
    if not review:
        return _error("复盘不存在", 404)
    return jsonify({"ok": True, "data": review})


@app.route("/api/assets", methods=["GET"])
def api_list_assets():
    tag = request.args.get("tag") or None
    try:
        return jsonify({"ok": True, "data": database.list_assets(tag)})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/assets", methods=["POST"])
def api_create_asset():
    payload = request.get_json(silent=True) or {}
    try:
        asset = database.create_asset(
            payload.get("title", ""),
            payload.get("trigger_context", ""),
            payload.get("core_content", ""),
            payload.get("asset_type", ""),
            payload.get("capability_tags", []),
            payload.get("source_review_id"),
        )
        return jsonify({"ok": True, "data": asset})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/assets/<int:asset_id>", methods=["PATCH"])
def api_update_asset(asset_id):
    payload = request.get_json(silent=True) or {}
    try:
        asset = database.update_asset(
            asset_id,
            payload.get("title", ""),
            payload.get("trigger_context", ""),
            payload.get("core_content", ""),
        )
        return jsonify({"ok": True, "data": asset})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/ai/refine-review", methods=["POST"])
def api_ai_refine_review():
    payload = request.get_json(silent=True) or {}
    review_id = payload.get("review_id")
    if not review_id:
        return _error("缺少 review_id")
    try:
        draft = ai_service.refine_review_to_asset(review_id)
        return jsonify({"ok": True, "data": draft})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/optimize-asset", methods=["POST"])
def api_ai_optimize_asset():
    payload = request.get_json(silent=True) or {}
    asset_id = payload.get("asset_id")
    if not asset_id:
        return _error("缺少 asset_id")
    try:
        result = ai_service.optimize_asset(asset_id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/dashboard-briefing", methods=["POST"])
def api_ai_dashboard_briefing():
    try:
        result = ai_service.dashboard_briefing()
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/decompose-goal", methods=["POST"])
def api_ai_decompose_goal():
    payload = request.get_json(silent=True) or {}
    goal_id = payload.get("goal_id")
    if not goal_id:
        return _error("缺少 goal_id")
    try:
        result = ai_service.decompose_goal_projects(goal_id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/capability-entries", methods=["GET"])
def api_list_capability_entries():
    module = request.args.get("module") or None
    try:
        return jsonify({"ok": True, "data": database.list_capability_entries(module)})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/capability-entries", methods=["POST"])
def api_create_capability_entry():
    payload = request.get_json(silent=True) or {}
    try:
        entry = database.create_capability_entry(
            payload.get("module", ""),
            payload.get("entry_date", ""),
            payload.get("content", ""),
            payload.get("source_project", ""),
            payload.get("level_type", ""),
        )
        return jsonify({"ok": True, "data": entry})
    except ValueError as exc:
        return _error(str(exc))


if __name__ == "__main__":
    database.init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)