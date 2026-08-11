import ai_service
import database
from prompts import load as load_prompt


ANALYSIS_FIELDS = database.DELIBERATION_ANALYSIS_FIELDS


class DeliberationServiceError(Exception):
    pass


def _normalize_analysis(data):
    if not isinstance(data, dict):
        raise DeliberationServiceError("AI 返回格式异常：分析结果必须是对象")

    normalized = {}
    for field in ANALYSIS_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            text = value.strip()
        elif isinstance(value, list):
            items = [
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip()
            ]
            if len(items) != len(value):
                raise DeliberationServiceError(
                    f"AI 返回格式异常：字段 {field} 必须是文本或文本数组"
                )
            text = "\n".join(f"- {item}" for item in items)
        else:
            text = ""
        if not text:
            raise DeliberationServiceError(
                f"AI 返回格式异常：缺少有效字段 {field}"
            )
        normalized[field] = text
    return normalized


def analyze(deliberation_id, user_id):
    deliberation = database.get_deliberation(deliberation_id, user_id)
    if not deliberation:
        raise DeliberationServiceError("推演不存在")
    if deliberation["status"] != "draft":
        raise DeliberationServiceError("只有待分析的推演可以开始 AI 对抗")

    missing = [
        field
        for field in ("problem", "initial_judgment", "reasoning", "assumptions")
        if not str(deliberation.get(field) or "").strip()
    ]
    if missing:
        raise DeliberationServiceError("请先完成自己的判断、理由和关键假设")

    system_prompt = load_prompt("deliberation", "challenge")
    user_prompt = load_prompt(
        "deliberation",
        "challenge",
        kind="user",
        problem=deliberation["problem"],
        context=deliberation.get("context") or "无补充背景",
        initial_judgment=deliberation["initial_judgment"],
        reasoning=deliberation["reasoning"],
        assumptions=deliberation["assumptions"],
    )

    try:
        raw_analysis = ai_service.request_structured_completion(
            system_prompt,
            user_prompt,
        )
    except ai_service.AIServiceError as exc:
        raise DeliberationServiceError(str(exc)) from exc

    analysis = _normalize_analysis(raw_analysis)
    return database.save_deliberation_analysis(
        deliberation_id, analysis, user_id
    )
