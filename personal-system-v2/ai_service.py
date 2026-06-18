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