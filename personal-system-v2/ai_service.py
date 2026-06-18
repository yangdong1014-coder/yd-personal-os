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