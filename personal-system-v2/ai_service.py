import json

from openai import APIConnectionError, APIStatusError, OpenAI

import config
import database

CAPABILITY_LIST = "、".join(database.CAPABILITY_MODULES)


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
            model=config.DEEPSEEK_MODEL,
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

    system_prompt = f"""你是个人知识资产提炼助手。根据复盘内容生成一张知识卡片草稿。
只输出 JSON，字段：
- title: 字符串，简洁标题
- core_content: 字符串，结构化核心知识（可分点）
- capability_tags: 字符串数组，从以下模块选 1-3 个：{CAPABILITY_LIST}
- trigger_context: 字符串，这张卡片从什么事情来的（概括复盘情境）"""

    user_prompt = f"""复盘日期：{review.get('review_date', '')}
复盘类型：{review.get('type', '')}
今天做了什么：{review.get('what_done', '')}
卡住了什么：{review.get('stuck', '')}
下一步调整：{review.get('next_adjust', '')}
可沉淀内容：{review.get('depositable', '')}"""

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

    system_prompt = """你是个人知识资产优化助手。对现有知识卡片进行润色和结构化。
保持原意，提升清晰度、可复用性与结构层次。
只输出 JSON，字段：
- title: 优化后的标题
- trigger_context: 优化后的触发情境
- core_content: 优化后的核心内容（可分点、小标题）"""

    user_prompt = f"""标题：{asset.get('title', '')}
触发情境：{asset.get('trigger_context', '')}
核心内容：{asset.get('core_content', '')}"""

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

    system_prompt = """你是个人作战指挥助手。根据用户当前目标、项目、任务与复盘，生成今日作战简报。
语气简洁、可执行，避免空话。
只输出 JSON，字段：
- briefing: 字符串，3-5句话的总览简报
- priorities: 字符串数组，今日优先事项 1-3 条
- focus: 字符串，一句话今日最重要的一件事"""

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

    system_prompt = """你是目标拆解助手。将目标拆解为可执行的项目（不是任务）。
每个项目应是可独立推进的工作包，名称简洁（2-12字）。
避免与已有项目重复。
只输出 JSON，字段：
- projects: 对象数组，每项含 name（项目名）和 reason（一句话说明为何需要）"""

    user_prompt = f"""目标名称：{goal['name']}
目标类型：{goal['type']}
已有项目：{', '.join(existing_names) if existing_names else '无'}"""

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

    system_prompt = """你是任务拆解助手。将项目拆解为可执行的具体任务（不是子项目）。
每个任务应是今天或本周可推进的动作，名称简洁（2-20字）。
可建议优先级：高 / 中 / 低（仅作参考，不写入系统）。
避免与已有任务重复。
只输出 JSON，字段：
- tasks: 对象数组，每项含 name（任务名）、priority（高/中/低）、reason（一句话说明）"""

    user_prompt = f"""项目名称：{project['name']}
所属目标：{project['goal_name']}（{project['goal_type']}）
已有任务：{', '.join(existing_names) if existing_names else '无'}"""

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

    system_prompt = """你是个人任务优先级助手。从给定的未完成任务中，推荐今日最应推进的 1-3 项。
优先：与主线目标相关、状态为进行中、阻塞后续工作的任务。
只输出 JSON，字段：
- recommendations: 对象数组，每项含 task_id（整数，必须来自列表中的 id）、reason（一句话推荐理由）"""

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

    system_prompt = """你是复盘补全助手。根据用户描述的今日事项，合理补全复盘字段。
语气具体、可执行，避免空话。可合理推断卡点，但不要编造未提及的重大事件。
只输出 JSON，字段：
- stuck: 字符串，可能的卡点与原因
- next_adjust: 字符串，下一步调整建议
- depositable: 字符串，可沉淀为知识资产的内容（无则空字符串）"""

    user_prompt = f"""复盘类型：{review_type or '每日'}
今天做了什么：{what_done}"""

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