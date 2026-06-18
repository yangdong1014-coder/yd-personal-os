import json

from flask import Flask, Response, jsonify, render_template, request

import ai_service
import asset_schemas
import changelog
import config
import database
import inbox_service
import obsidian_export
import prompt_specs
import settings_store
from prompts import MODULES, PromptNotFoundError, list_prompts, read_raw, save as save_prompt

app = Flask(__name__)


@app.context_processor
def inject_globals():
    return {
        "ai_enabled": config.is_ai_enabled(),
        "current_version": changelog.get_current_version(),
    }

NAV_ITEMS = [
    {"endpoint": "index", "label": "首页", "path": "/"},
    {"endpoint": "goals", "label": "目标", "path": "/goals"},
    {"endpoint": "tasks", "label": "任务", "path": "/tasks"},
    {"endpoint": "reviews", "label": "复盘", "path": "/reviews"},
    {"endpoint": "assets", "label": "资产", "path": "/assets"},
    {"endpoint": "capabilities", "label": "能力", "path": "/capabilities"},
    {"endpoint": "inbox", "label": "智能归档", "path": "/inbox"},
    {"endpoint": "prompts", "label": "AI管理", "path": "/prompts"},
    {"endpoint": "changelog", "label": "版本日志", "path": "/changelog"},
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
        maturity_levels=database.MATURITY_LEVELS,
        asset_field_schemas=asset_schemas.get_frontend_schemas(),
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


@app.route("/inbox")
def inbox_page():
    return render_template(
        "inbox.html",
        active_page="inbox",
        nav_items=NAV_ITEMS,
    )


@app.route("/inbox/history")
def inbox_history_page():
    return render_template(
        "inbox_history.html",
        active_page="inbox",
        nav_items=NAV_ITEMS,
    )


@app.route("/prompts")
def prompts_page():
    return render_template(
        "prompts.html",
        active_page="prompts",
        nav_items=NAV_ITEMS,
        prompt_modules=MODULES,
    )


@app.route("/changelog")
def changelog_page():
    return render_template(
        "changelog.html",
        active_page="changelog",
        nav_items=NAV_ITEMS,
        entries=changelog.list_entries(),
        current_version=changelog.get_current_version(),
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


@app.route("/api/goals/<int:goal_id>", methods=["DELETE"])
def api_delete_goal(goal_id):
    try:
        result = database.delete_goal(goal_id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


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


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    try:
        result = database.delete_project(project_id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


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


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    try:
        result = database.delete_task(task_id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


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


@app.route("/api/export/obsidian.zip", methods=["GET"])
def api_export_obsidian():
    try:
        body = obsidian_export.build_obsidian_zip()
        filename = obsidian_export.zip_filename()
        return Response(
            body,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except obsidian_export.ObsidianExportError as exc:
        return _error(str(exc), 500)


@app.route("/api/import/preview", methods=["POST"])
def api_import_preview():
    payload = request.get_json(silent=True)
    if payload is None:
        return _error("请求体必须是有效的 JSON")
    try:
        stats = database.preview_import_data(payload)
        return jsonify({"ok": True, "data": stats})
    except database.DataImportError as exc:
        return _error(str(exc), 400)


@app.route("/api/import", methods=["POST"])
def api_import():
    payload = request.get_json(silent=True)
    if payload is None:
        return _error("请求体必须是有效的 JSON")
    try:
        stats = database.import_all_data(payload)
        return jsonify({"ok": True, "data": stats})
    except database.DataImportError as exc:
        body = {"ok": False, "error": str(exc)}
        body["data"] = exc.stats or database._import_failure_stats(
            errors=[str(exc)]
        )
        return jsonify(body), 400


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


@app.route("/api/reviews/<int:review_id>", methods=["DELETE"])
def api_delete_review(review_id):
    try:
        result = database.delete_review(review_id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


@app.route("/api/assets", methods=["GET"])
def api_list_assets():
    tag = request.args.get("tag") or None
    asset_type = request.args.get("asset_type") or None
    try:
        return jsonify({
            "ok": True,
            "data": database.list_assets(tag, asset_type=asset_type),
        })
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/assets", methods=["POST"])
def api_create_asset():
    payload = request.get_json(silent=True) or {}
    try:
        asset = database.create_asset(
            payload.get("title", ""),
            payload.get("asset_type", ""),
            capability_tags=payload.get("capability_tags", []),
            fields=payload.get("fields"),
            summary=payload.get("summary", ""),
            reusable_scenario=payload.get("reusable_scenario", ""),
            maturity=payload.get("maturity", "草稿"),
            source_review_id=payload.get("source_review_id"),
            trigger_context=payload.get("trigger_context"),
            core_content=payload.get("core_content"),
        )
        return jsonify({"ok": True, "data": asset})
    except (ValueError, TypeError) as exc:
        return _error(str(exc) if str(exc) else "参数无效")


@app.route("/api/assets/<int:asset_id>", methods=["PATCH"])
def api_update_asset(asset_id):
    payload = request.get_json(silent=True) or {}
    try:
        asset = database.update_asset(asset_id, **payload)
        return jsonify({"ok": True, "data": asset})
    except ValueError as exc:
        return _error(str(exc))


@app.route("/api/assets/<int:asset_id>/reuse", methods=["POST"])
def api_increment_asset_reuse(asset_id):
    try:
        asset = database.increment_asset_reuse(asset_id)
        return jsonify({"ok": True, "data": asset})
    except ValueError as exc:
        return _error(str(exc), 404)


@app.route("/api/assets/<int:asset_id>", methods=["DELETE"])
def api_delete_asset(asset_id):
    try:
        result = database.delete_asset(asset_id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


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


@app.route("/api/ai/decompose-project", methods=["POST"])
def api_ai_decompose_project():
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    if not project_id:
        return _error("缺少 project_id")
    try:
        result = ai_service.decompose_project_tasks(project_id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/recommend-today-tasks", methods=["POST"])
def api_ai_recommend_today_tasks():
    try:
        result = ai_service.recommend_today_tasks()
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/complete-review", methods=["POST"])
def api_ai_complete_review():
    payload = request.get_json(silent=True) or {}
    try:
        result = ai_service.complete_review_fields(
            payload.get("what_done", ""),
            payload.get("type", "每日"),
        )
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/classify-asset", methods=["POST"])
def api_ai_classify_asset():
    payload = request.get_json(silent=True) or {}
    asset_id = payload.get("asset_id")
    if not asset_id:
        return _error("缺少 asset_id")
    try:
        result = ai_service.classify_asset(asset_id)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/template-asset", methods=["POST"])
def api_ai_template_asset():
    payload = request.get_json(silent=True) or {}
    asset_id = payload.get("asset_id")
    target_type = payload.get("target_type")
    if not asset_id:
        return _error("缺少 asset_id")
    if not target_type:
        return _error("缺少 target_type")
    try:
        result = ai_service.template_asset(asset_id, target_type)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/attribute-capability", methods=["POST"])
def api_ai_attribute_capability():
    payload = request.get_json(silent=True) or {}
    module = payload.get("module")
    if not module:
        return _error("缺少 module")
    try:
        result = ai_service.attribute_capability(module)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/diagnose-capabilities", methods=["POST"])
def api_ai_diagnose_capabilities():
    try:
        result = ai_service.diagnose_capabilities()
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/aggregate-weekly-reviews", methods=["POST"])
def api_ai_aggregate_weekly_reviews():
    payload = request.get_json(silent=True) or {}
    review_ids = payload.get("review_ids")
    if not review_ids:
        return _error("缺少 review_ids")
    try:
        result = ai_service.aggregate_weekly_reviews(review_ids)
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/dispatch-actions", methods=["POST"])
def api_ai_dispatch_actions():
    try:
        result = ai_service.dispatch_dashboard_actions()
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/inbox/analyze", methods=["POST"])
def api_inbox_analyze():
    payload = request.get_json(silent=True) or {}
    try:
        result = inbox_service.analyze_text(
            payload.get("text", ""),
            ai_service.analyze_inbox_text,
        )
        return jsonify({
            "ok": True,
            "data": {
                "inbox_entry_id": result["inbox_entry_id"],
                "entry": result["entry"],
                "suggestions": result["suggestions"],
            },
        })
    except inbox_service.InboxServiceError as exc:
        return _error(str(exc))


@app.route("/api/inbox", methods=["GET"])
def api_list_inbox():
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit, 50))
    return jsonify({"ok": True, "data": database.list_inbox_entries(limit)})


@app.route("/api/inbox/<int:entry_id>", methods=["GET"])
def api_get_inbox(entry_id):
    try:
        result = inbox_service.get_inbox_detail(entry_id)
        return jsonify({"ok": True, "data": result})
    except inbox_service.InboxServiceError as exc:
        return _error(str(exc), 404)


@app.route("/api/inbox/commit", methods=["POST"])
def api_inbox_commit():
    payload = request.get_json(silent=True) or {}
    suggestion_ids = payload.get("suggestion_ids") or []
    override_payload = payload.get("override_payload") or []
    if not isinstance(suggestion_ids, list):
        return _error("suggestion_ids 必须为数组")
    if not isinstance(override_payload, list):
        return _error("override_payload 必须为数组")
    try:
        result = inbox_service.commit_suggestions(
            suggestion_ids, override_payload=override_payload
        )
        return jsonify({"ok": True, "data": result})
    except inbox_service.InboxServiceError as exc:
        return _error(str(exc))


@app.route("/api/inbox/suggestions/<int:suggestion_id>/reject", methods=["POST"])
def api_inbox_reject_suggestion(suggestion_id):
    try:
        suggestion = inbox_service.reject_suggestion(suggestion_id)
        return jsonify({"ok": True, "data": suggestion})
    except inbox_service.InboxServiceError as exc:
        return _error(str(exc))


@app.route("/api/changelog", methods=["GET"])
def api_changelog():
    return jsonify({
        "ok": True,
        "data": {
            "current": changelog.get_current_version(),
            "entries": changelog.list_entries(),
        },
    })


@app.route("/api/settings/ai-model", methods=["GET"])
def api_get_ai_model():
    stored = settings_store.get_stored_model()
    return jsonify({
        "ok": True,
        "data": {
            "model": config.get_deepseek_model(),
            "stored_model": stored or config.DEFAULT_DEEPSEEK_MODEL,
            "available": config.AVAILABLE_DEEPSEEK_MODELS,
            "env_locked": config.is_model_env_locked(),
            "env_model": config._ENV_DEEPSEEK_MODEL or None,
        },
    })


@app.route("/api/settings/ai-model", methods=["PUT"])
def api_set_ai_model():
    if config.is_model_env_locked():
        return _error(
            "模型已由环境变量 DEEPSEEK_MODEL 锁定，请在 .env 或系统环境中修改后重启服务"
        )
    payload = request.get_json(silent=True) or {}
    model = (payload.get("model") or "").strip()
    if model not in config.get_valid_model_ids():
        return _error("不支持的模型")
    settings_store.set_stored_model(model)
    return jsonify({"ok": True, "data": {"model": model}})


@app.route("/api/ai/prompts", methods=["GET"])
def api_list_prompts():
    module = request.args.get("module") or None
    items = list_prompts()
    if module:
        items = [item for item in items if item["module"] == module]
    return jsonify({"ok": True, "data": items})


@app.route("/api/ai/prompts/<module>/<scene>", methods=["GET"])
def api_get_prompt(module, scene):
    try:
        system = read_raw(module, scene, "system")
    except (PromptNotFoundError, ValueError) as exc:
        return _error(str(exc), 404)

    user = None
    try:
        user = read_raw(module, scene, "user")
    except PromptNotFoundError:
        pass

    return jsonify({
        "ok": True,
        "data": {
            "module": module,
            "scene": scene,
            "system": system,
            "user": user,
        },
    })


@app.route("/api/ai/prompts/<module>/<scene>/generate", methods=["POST"])
def api_generate_prompt(module, scene):
    payload = request.get_json(silent=True) or {}
    kind = payload.get("kind", "system")
    if kind not in ("system", "user"):
        return _error("kind 必须为 system 或 user")
    try:
        prompt_specs.get_scene_spec(module, scene)
    except ValueError as exc:
        return _error(str(exc), 404)
    try:
        result = ai_service.generate_prompt_draft(
            module,
            scene,
            kind,
            brief=payload.get("brief", ""),
            current=payload.get("current", ""),
        )
        return jsonify({"ok": True, "data": result})
    except ai_service.AIServiceError as exc:
        return _error(str(exc))


@app.route("/api/ai/prompts/<module>/<scene>", methods=["PUT"])
def api_save_prompt(module, scene):
    payload = request.get_json(silent=True) or {}
    kind = payload.get("kind", "system")
    content = payload.get("content")
    if content is None:
        return _error("缺少 content")
    if kind not in ("system", "user"):
        return _error("kind 必须为 system 或 user")
    try:
        path = save_prompt(module, scene, kind, content)
        return jsonify({"ok": True, "data": {"path": path}})
    except ValueError as exc:
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


@app.route("/api/capability-entries/<int:entry_id>", methods=["DELETE"])
def api_delete_capability_entry(entry_id):
    try:
        result = database.delete_capability_entry(entry_id)
        return jsonify({"ok": True, "data": result})
    except ValueError as exc:
        return _error(str(exc), 404)
    except database.DeleteError as exc:
        return _error(str(exc), 409)


if __name__ == "__main__":
    database.init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)