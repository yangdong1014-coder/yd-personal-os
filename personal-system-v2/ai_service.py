import json
from datetime import datetime
from pathlib import Path

from openai import APIConnectionError, APIStatusError, OpenAI

import config
import database
import prompt_specs
from prompts import load as load_prompt

_META_GENERATE_PROMPT_PATH = (
    Path(__file__).parent / "prompts" / "_meta" / "generate-draft.system.txt"
)

CAPABILITY_LIST = "、".join(database.CAPABILITY_MODULES)
ASSET_TYPE_LIST = "、".join(database.ASSET_TYPES)


class AIServiceError(Exception):
    pass


def _get_client():
    if not config.is_ai_enabled():
        raise AIServiceError(
            "未配置 DEEPSEEK_API_KEY，请设置环境变量或在项目根目录 .env 文件中配置后重启服务"
        )
    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=config.DEEPSEEK_TIMEOUT,
    )


def _chat_json(system_prompt, user_prompt):
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=config.get_deepseek_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            stream=False,
        )
    except APIConnectionError as exc:
        raise AIServiceError("无法连接 DeepSeek API，请检查网络后重试") from exc
    except APIStatusError as exc:
        if exc.status_code == 401:
            raise AIServiceError("API Key 无效，请检查 DEEPSEEK_API_KEY") from exc
        raise AIServiceError(f"DeepSeek API 调用失败（{exc.status_code}）") from exc
    except Exception as exc:
        raise AIServiceError("AI 服务暂时不可用，请稍后重试") from exc

    content = response.choices[0].message.content
    if not content:
        raise AIServiceError("AI 返回内容为空，请重试")

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIServiceError("AI 返回格式异常，请重试") from exc


def _filter_capability_tags(tags):
    if not isinstance(tags, list):
        return []
    return [t for t in tags if t in database.CAPABILITY_MODULES]


def refine_review_to_asset(review_id):
    review = database.get_review(review_id)
    if not review:
        raise AIServiceError("复盘记录不存在")

    system_prompt = load_prompt(
        "reviews",
        "refine-to-asset",
        capability_list=CAPABILITY_LIST,
    )
    user_prompt = load_prompt(
        "reviews",
        "refine-to-asset",
        kind="user",
        review_date=review.get("review_date", ""),
        review_type=review.get("type", ""),
        what_done=review.get("what_done", ""),
        stuck=review.get("stuck", ""),
        next_adjust=review.get("next_adjust", ""),
        depositable=review.get("depositable", ""),
    )

    data = _chat_json(system_prompt, user_prompt)

    title = (data.get("title") or "").strip()
    core_content = (data.get("core_content") or "").strip()
    if not title or not core_content:
        raise AIServiceError("AI 未能生成有效草稿，请重试")

    return {
        "title": title,
        "core_content": core_content,
        "trigger_context": (data.get("trigger_context") or "").strip(),
        "capability_tags": _filter_capability_tags(data.get("capability_tags")),
        "source_review_id": review_id,
        "asset_type": "知识卡片",
    }


def optimize_asset(asset_id):
    asset = database.get_asset(asset_id)
    if not asset:
        raise AIServiceError("知识卡片不存在")

    system_prompt = load_prompt("assets", "optimize")
    user_prompt = load_prompt(
        "assets",
        "optimize",
        kind="user",
        title=asset.get("title", ""),
        trigger_context=asset.get("trigger_context", ""),
        core_content=asset.get("core_content", ""),
    )

    data = _chat_json(system_prompt, user_prompt)

    title = (data.get("title") or "").strip()
    core_content = (data.get("core_content") or "").strip()
    if not title or not core_content:
        raise AIServiceError("AI 未能生成有效优化结果，请重试")

    return {
        "asset_id": asset_id,
        "title": title,
        "trigger_context": (data.get("trigger_context") or "").strip(),
        "core_content": core_content,
    }


def _format_dashboard_context():
    dashboard = database.get_dashboard()
    lines = []

    goal = dashboard.get("mainline_goal")
    if goal:
        lines.append(f"当前主线目标：{goal['name']}（{goal['type']}）")
    else:
        lines.append("当前主线目标：无")

    projects = dashboard.get("week_projects") or []
    if projects:
        lines.append("本周进行中项目：" + "；".join(
            f"{p['name']}（所属：{p['goal_name']}）" for p in projects
        ))
    else:
        lines.append("本周进行中项目：无")

    tasks = dashboard.get("today_tasks") or []
    if tasks:
        lines.append("今日推进任务：" + "；".join(
            f"{t['name']}（{t['status']}）" for t in tasks
        ))
    else:
        lines.append("今日推进任务：无")

    reviews = database.list_reviews()[:3]
    if reviews:
        lines.append("最近复盘：")
        for r in reviews:
            lines.append(
                f"- {r['review_date']} {r['type']}：{r.get('what_done', '')[:80]}"
            )

    return "\n".join(lines)


def dashboard_briefing():
    context = _format_dashboard_context()
    system_prompt = load_prompt("dashboard", "briefing")
    data = _chat_json(system_prompt, context)

    briefing = (data.get("briefing") or "").strip()
    priorities = data.get("priorities") or []
    focus = (data.get("focus") or "").strip()

    if not briefing:
        raise AIServiceError("AI 未能生成有效简报，请重试")

    if not isinstance(priorities, list):
        priorities = []
    priorities = [str(p).strip() for p in priorities if str(p).strip()][:3]

    return {
        "briefing": briefing,
        "priorities": priorities,
        "focus": focus,
    }


def decompose_goal_projects(goal_id):
    goal = database.get_goal(goal_id)
    if not goal:
        raise AIServiceError("目标不存在")

    existing = database.list_projects(goal_id)
    existing_names = [p["name"] for p in existing]

    system_prompt = load_prompt("goals", "decompose-projects")
    user_prompt = load_prompt(
        "goals",
        "decompose-projects",
        kind="user",
        goal_name=goal["name"],
        goal_type=goal["type"],
        existing_projects=", ".join(existing_names) if existing_names else "无",
    )

    data = _chat_json(system_prompt, user_prompt)

    projects = data.get("projects") or []
    if not isinstance(projects, list) or not projects:
        raise AIServiceError("AI 未能生成有效项目建议，请重试")

    result = []
    existing_lower = {n.lower() for n in existing_names}
    for item in projects[:5]:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or name.lower() in existing_lower:
            continue
        result.append({
            "name": name,
            "reason": (item.get("reason") or "").strip(),
        })

    if not result:
        raise AIServiceError("AI 建议的项目均已存在或无效，请重试")

    return {
        "goal_id": goal_id,
        "goal_name": goal["name"],
        "projects": result,
    }


def decompose_project_tasks(project_id):
    project = database.get_project(project_id)
    if not project:
        raise AIServiceError("项目不存在")

    existing = database.list_tasks(project_id)
    existing_names = [t["name"] for t in existing]

    system_prompt = load_prompt("tasks", "decompose-tasks")
    user_prompt = load_prompt(
        "tasks",
        "decompose-tasks",
        kind="user",
        project_name=project["name"],
        goal_name=project["goal_name"],
        goal_type=project["goal_type"],
        existing_tasks=", ".join(existing_names) if existing_names else "无",
    )

    data = _chat_json(system_prompt, user_prompt)

    tasks = data.get("tasks") or []
    if not isinstance(tasks, list) or not tasks:
        raise AIServiceError("AI 未能生成有效任务建议，请重试")

    result = []
    existing_lower = {n.lower() for n in existing_names}
    for item in tasks[:8]:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or name.lower() in existing_lower:
            continue
        priority = (item.get("priority") or "").strip()
        if priority not in ("高", "中", "低"):
            priority = "中"
        result.append({
            "name": name,
            "priority": priority,
            "reason": (item.get("reason") or "").strip(),
        })

    if not result:
        raise AIServiceError("AI 建议的任务均已存在或无效，请重试")

    return {
        "project_id": project_id,
        "project_name": project["name"],
        "goal_name": project["goal_name"],
        "tasks": result,
    }


def recommend_today_tasks():
    dashboard = database.get_dashboard()
    open_tasks = [t for t in database.list_tasks() if t.get("status") != "完成"]
    if not open_tasks:
        raise AIServiceError("暂无未完成任务可推荐")

    lines = []
    goal = dashboard.get("mainline_goal")
    if goal:
        lines.append(f"当前主线目标：{goal['name']}")
    else:
        lines.append("当前主线目标：无")

    lines.append("未完成任务列表：")
    task_map = {}
    for t in open_tasks[:30]:
        task_map[t["id"]] = t
        lines.append(
            f"- id={t['id']} | {t['name']} | {t['status']} | "
            f"{t['goal_name']}/{t['project_name']}"
        )

    system_prompt = load_prompt("tasks", "recommend-today")
    data = _chat_json(system_prompt, "\n".join(lines))

    recommendations = data.get("recommendations") or []
    if not isinstance(recommendations, list):
        recommendations = []

    name_map = {t["name"].lower(): t for t in task_map.values()}
    result = []
    seen_ids = set()

    for item in recommendations[:3]:
        if not isinstance(item, dict):
            continue

        task = None
        task_id = item.get("task_id")
        try:
            task_id = int(task_id)
            task = task_map.get(task_id)
        except (TypeError, ValueError):
            task_id = None

        if not task:
            task_name = (item.get("task_name") or item.get("name") or "").strip().lower()
            if task_name:
                task = name_map.get(task_name)

        if not task or task["id"] in seen_ids:
            continue

        seen_ids.add(task["id"])
        result.append({
            "task_id": task["id"],
            "name": task["name"],
            "status": task["status"],
            "goal_name": task["goal_name"],
            "project_name": task["project_name"],
            "reason": (item.get("reason") or "").strip(),
        })

    if not result and len(open_tasks) == 1:
        task = open_tasks[0]
        result.append({
            "task_id": task["id"],
            "name": task["name"],
            "status": task["status"],
            "goal_name": task["goal_name"],
            "project_name": task["project_name"],
            "reason": "当前唯一未完成任务，建议今日推进",
        })

    if not result:
        raise AIServiceError("AI 推荐的任务无效，请重试")

    return {"recommendations": result}


def complete_review_fields(what_done, review_type="每日"):
    what_done = (what_done or "").strip()
    if not what_done:
        raise AIServiceError("请先填写「今天做了什么」")

    system_prompt = load_prompt("reviews", "complete-fields")
    user_prompt = load_prompt(
        "reviews",
        "complete-fields",
        kind="user",
        review_type=review_type or "每日",
        what_done=what_done,
    )

    data = _chat_json(system_prompt, user_prompt)

    stuck = (data.get("stuck") or "").strip()
    next_adjust = (data.get("next_adjust") or "").strip()
    if not stuck and not next_adjust:
        raise AIServiceError("AI 未能生成有效补全内容，请重试")

    return {
        "stuck": stuck,
        "next_adjust": next_adjust,
        "depositable": (data.get("depositable") or "").strip(),
    }


def _format_capability_context():
    lines = []

    tasks = database.list_tasks()[:10]
    if tasks:
        lines.append("近期任务：")
        for t in tasks:
            lines.append(
                f"- {t['name']}（{t['status']}）| {t['goal_name']}/{t['project_name']}"
            )
    else:
        lines.append("近期任务：无")

    reviews = database.list_reviews()[:5]
    if reviews:
        lines.append("近期复盘：")
        for r in reviews:
            lines.append(
                f"- {r['review_date']} {r['type']}：{(r.get('what_done') or '')[:60]}"
            )
    else:
        lines.append("近期复盘：无")

    assets = database.list_assets()[:5]
    if assets:
        lines.append("近期资产：")
        for a in assets:
            lines.append(f"- {a['title']}（{a['asset_type']}）")
    else:
        lines.append("近期资产：无")

    return "\n".join(lines)


def classify_asset(asset_id):
    asset = database.get_asset(asset_id)
    if not asset:
        raise AIServiceError("知识卡片不存在")

    system_prompt = load_prompt(
        "assets",
        "classify",
        asset_types=ASSET_TYPE_LIST,
        capability_list=CAPABILITY_LIST,
    )
    user_prompt = load_prompt(
        "assets",
        "classify",
        kind="user",
        title=asset.get("title", ""),
        asset_type=asset.get("asset_type", ""),
        capability_tags=", ".join(asset.get("capability_tags") or []) or "无",
        trigger_context=asset.get("trigger_context", ""),
        core_content=asset.get("core_content", ""),
    )

    data = _chat_json(system_prompt, user_prompt)

    asset_type = (data.get("asset_type") or "").strip()
    if asset_type not in database.ASSET_TYPES:
        asset_type = asset.get("asset_type") or "知识卡片"

    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "capability_tags": _filter_capability_tags(data.get("capability_tags")),
        "reason": (data.get("reason") or "").strip(),
    }


def template_asset(asset_id, target_type):
    asset = database.get_asset(asset_id)
    if not asset:
        raise AIServiceError("知识卡片不存在")

    allowed = ("SOP", "提示词")
    target_type = (target_type or "").strip()
    if target_type not in allowed:
        raise AIServiceError("目标类型仅支持 SOP 或 提示词")

    system_prompt = load_prompt("assets", "template", target_type=target_type)
    user_prompt = load_prompt(
        "assets",
        "template",
        kind="user",
        title=asset.get("title", ""),
        asset_type=asset.get("asset_type", ""),
        trigger_context=asset.get("trigger_context", ""),
        core_content=asset.get("core_content", ""),
    )

    data = _chat_json(system_prompt, user_prompt)

    title = (data.get("title") or "").strip()
    core_content = (data.get("core_content") or "").strip()
    if not title or not core_content:
        raise AIServiceError("AI 未能生成有效模板，请重试")

    return {
        "asset_id": asset_id,
        "asset_type": target_type,
        "title": title,
        "trigger_context": (data.get("trigger_context") or "").strip(),
        "core_content": core_content,
    }


def attribute_capability(module):
    if module not in database.CAPABILITY_MODULES:
        raise AIServiceError("无效的能力模块")

    context = _format_capability_context()
    system_prompt = load_prompt("capabilities", "attribute", module=module)
    data = _chat_json(system_prompt, context)

    content = (data.get("content") or "").strip()
    level_type = (data.get("level_type") or "").strip()
    if not content:
        raise AIServiceError("AI 未能生成有效进展建议，请重试")
    if level_type not in database.LEVEL_TYPES:
        level_type = "应用层"

    return {
        "module": module,
        "content": content,
        "level_type": level_type,
        "source_project": (data.get("source_project") or "").strip(),
        "reason": (data.get("reason") or "").strip(),
    }


def diagnose_capabilities():
    entries = database.list_capability_entries()
    stats = {
        m: {"能力层": 0, "应用层": 0, "total": 0}
        for m in database.CAPABILITY_MODULES
    }
    for entry in entries:
        module = entry.get("module")
        level = entry.get("level_type")
        if module not in stats:
            continue
        if level in stats[module]:
            stats[module][level] += 1
        stats[module]["total"] += 1

    lines = ["八模块记录统计："]
    for module in database.CAPABILITY_MODULES:
        s = stats[module]
        lines.append(
            f"- {module}：共{s['total']}条，能力层{s['能力层']}，应用层{s['应用层']}"
        )

    system_prompt = load_prompt("capabilities", "diagnose")
    data = _chat_json(system_prompt, "\n".join(lines))

    summary = (data.get("summary") or "").strip()
    if not summary:
        raise AIServiceError("AI 未能生成有效诊断，请重试")

    imbalances = data.get("imbalances") or []
    if not isinstance(imbalances, list):
        imbalances = []
    imbalances = [str(i).strip() for i in imbalances if str(i).strip()][:3]

    focus_module = (data.get("focus_module") or "").strip()
    if focus_module not in database.CAPABILITY_MODULES:
        focus_module = ""

    return {
        "summary": summary,
        "imbalances": imbalances,
        "focus_module": focus_module,
        "focus_action": (data.get("focus_action") or "").strip(),
        "stats": stats,
    }


def aggregate_weekly_reviews(review_ids):
    if not review_ids or not isinstance(review_ids, list):
        raise AIServiceError("请选择至少两条日复盘")

    reviews = []
    for raw_id in review_ids[:14]:
        try:
            review_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        review = database.get_review(review_id)
        if review and review.get("type") == "每日":
            reviews.append(review)

    if len(reviews) < 2:
        raise AIServiceError("请至少选择两条「每日」复盘进行聚合")

    reviews.sort(key=lambda r: r.get("review_date", ""))

    lines = [f"共 {len(reviews)} 条日复盘，日期 {reviews[0]['review_date']} 至 {reviews[-1]['review_date']}："]
    for review in reviews:
        lines.append(f"\n【{review['review_date']}】")
        lines.append(f"做了什么：{review.get('what_done', '')}")
        lines.append(f"卡住了：{review.get('stuck', '')}")
        lines.append(f"下一步：{review.get('next_adjust', '')}")
        if review.get("depositable"):
            lines.append(f"可沉淀：{review.get('depositable', '')}")

    system_prompt = load_prompt("reviews", "aggregate-weekly")
    data = _chat_json(system_prompt, "\n".join(lines))

    what_done = (data.get("what_done") or "").strip()
    if not what_done:
        raise AIServiceError("AI 未能生成有效周复盘，请重试")

    return {
        "review_date": datetime.now().strftime("%Y-%m-%d"),
        "type": "每周",
        "what_done": what_done,
        "stuck": (data.get("stuck") or "").strip(),
        "next_adjust": (data.get("next_adjust") or "").strip(),
        "depositable": (data.get("depositable") or "").strip(),
        "source_review_ids": [r["id"] for r in reviews],
        "source_count": len(reviews),
    }


def dispatch_dashboard_actions():
    context = _format_dashboard_context()
    projects = database.list_projects()
    open_tasks = [t for t in database.list_tasks() if t.get("status") != "完成"]

    if not projects and not open_tasks:
        raise AIServiceError("暂无项目或任务可分发行动")

    lines = [context, ""]
    project_map = {}
    if projects:
        lines.append("可用项目（新建任务时 project_id 必须来自此列表）：")
        for project in projects[:20]:
            project_map[project["id"]] = project
            lines.append(
                f"- id={project['id']} | {project['goal_name']}/{project['name']}"
            )
    else:
        lines.append("可用项目：无")

    task_map = {}
    if open_tasks:
        lines.append("未完成任务（标记今日推进时 task_id 必须来自此列表）：")
        for task in open_tasks[:30]:
            task_map[task["id"]] = task
            lines.append(
                f"- id={task['id']} | {task['name']} | {task['status']} | "
                f"{task['goal_name']}/{task['project_name']}"
            )
    else:
        lines.append("未完成任务：无")

    system_prompt = load_prompt("dashboard", "dispatch-actions")
    data = _chat_json(system_prompt, "\n".join(lines))

    mark_today = []
    seen_task_ids = set()
    for item in (data.get("mark_today") or [])[:3]:
        if not isinstance(item, dict):
            continue
        try:
            task_id = int(item.get("task_id"))
        except (TypeError, ValueError):
            continue
        task = task_map.get(task_id)
        if not task or task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        mark_today.append({
            "task_id": task_id,
            "name": task["name"],
            "goal_name": task["goal_name"],
            "project_name": task["project_name"],
            "reason": (item.get("reason") or "").strip(),
        })

    new_tasks = []
    seen_names = set()
    for item in (data.get("new_tasks") or [])[:3]:
        if not isinstance(item, dict):
            continue
        try:
            project_id = int(item.get("project_id"))
        except (TypeError, ValueError):
            continue
        project = project_map.get(project_id)
        name = (item.get("name") or "").strip()
        if not project or not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        new_tasks.append({
            "project_id": project_id,
            "name": name,
            "goal_name": project["goal_name"],
            "project_name": project["name"],
            "reason": (item.get("reason") or "").strip(),
        })

    if not mark_today and not new_tasks:
        raise AIServiceError("AI 未能生成有效行动建议，请重试")

    return {
        "mark_today": mark_today,
        "new_tasks": new_tasks,
    }


def _load_meta_generate_prompt():
    if not _META_GENERATE_PROMPT_PATH.is_file():
        raise AIServiceError("提示词生成元提示词缺失")
    return _META_GENERATE_PROMPT_PATH.read_text(encoding="utf-8").strip()


def generate_prompt_draft(module, scene, kind, brief="", current=""):
    if kind not in ("system", "user"):
        raise AIServiceError("kind 必须为 system 或 user")

    try:
        spec = prompt_specs.get_scene_spec(module, scene)
    except ValueError as exc:
        raise AIServiceError(str(exc)) from exc

    if kind == "user" and not prompt_specs.can_generate_user(module, scene):
        raise AIServiceError("该场景的用户上下文由系统自动拼装，无需用户模板")

    module_label = prompt_specs.MODULE_LABELS.get(module, module)
    system_vars = spec.get("system_vars") or []
    user_vars = spec.get("user_vars") or []

    lines = [
        f"模块：{module_label}（{module}）",
        f"场景：{spec['label']}（{scene}）",
        f"场景用途：{spec['purpose']}",
        f"生成类型：{'系统提示词' if kind == 'system' else '用户上下文模板'}",
    ]

    if kind == "system":
        lines.append(f"期望 AI 输出 JSON 结构：{spec['json_schema']}")
        if system_vars:
            lines.append(
                "系统提示词可用变量："
                + " ".join(f"{{{name}}}" for name in system_vars)
            )
    elif user_vars:
        lines.append(
            "用户模板必须包含变量："
            + " ".join(f"{{{name}}}" for name in user_vars)
        )

    current = (current or "").strip()
    if current:
        lines.append(f"\n当前内容（可在此基础上优化）：\n{current}")

    brief = (brief or "").strip()
    if brief:
        lines.append(f"\n补充说明：{brief}")

    meta_system = _load_meta_generate_prompt()
    data = _chat_json(meta_system, "\n".join(lines))

    content = (data.get("content") or "").strip()
    if not content:
        raise AIServiceError("AI 未能生成有效提示词初稿，请重试")

    return {
        "content": content,
        "kind": kind,
        "module": module,
        "scene": scene,
    }