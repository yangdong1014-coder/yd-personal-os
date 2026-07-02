import ai_service
import asset_schemas
import database

CONFIDENCE_UNCERTAIN_THRESHOLD = 0.6
ASSET_ACTIONS = ("create", "append", "merge", "stash")
ASSET_TYPE_ALIASES = {
    "insight": "本质洞察",
    "essence": "本质洞察",
    "methodology": "方法论",
    "method": "方法论",
    "model": "模型",
    "sop": "SOP",
    "template": "模板",
    "prompt": "提示词",
    "case": "案例复盘",
    "checklist": "清单",
    "principle": "原则规则",
    "tool": "工具组件",
    "generic": "通用资产",
}
MATURITY_ALIASES = {
    "draft": "草稿",
    "ready": "可用",
    "usable": "可用",
    "stable": "稳定",
    "standard": "标准化",
    "standardized": "标准化",
}


class InboxServiceError(Exception):
    pass


def _as_text(value):
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _normalize_asset_type(value, title="", content=""):
    raw = _as_text(value)
    alias = ASSET_TYPE_ALIASES.get(raw.lower())
    if alias:
        return alias
    return asset_schemas.normalize_asset_type(raw, title, content)


def _normalize_maturity(value):
    raw = _as_text(value)
    if raw in database.MATURITY_LEVELS:
        return raw
    return MATURITY_ALIASES.get(raw.lower(), "草稿")


def _normalize_unmatched_fragments(value):
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]
    text = _as_text(value)
    return [text] if text else []


def _normalize_capability_tags(value):
    if not isinstance(value, list):
        return []
    return [tag for tag in (_as_text(item) for item in value) if tag in database.CAPABILITY_MODULES]


def _normalize_asset_fields(asset_type, raw_fields, unmatched):
    fields = asset_schemas.parse_fields(raw_fields)
    if not fields:
        return {}, unmatched

    allowed = {key for key, _ in asset_schemas.get_field_defs(asset_type)}
    cleaned = {}
    for key, value in fields.items():
        text = _as_text(value)
        if not text:
            continue
        if key in allowed:
            cleaned[key] = text
        else:
            unmatched.append(f"{key}: {text}")
    return cleaned, unmatched


def _normalize_asset_payload(raw, payload, title, content):
    payload = dict(payload or {})
    asset_title = _as_text(payload.get("title")) or title
    core_content = _as_text(payload.get("core_content")) or content
    asset_type = _normalize_asset_type(
        payload.get("asset_type") or raw.get("asset_type"),
        asset_title,
        core_content,
    )
    unmatched = _normalize_unmatched_fragments(payload.get("unmatched_fragments"))
    unmatched.extend(_normalize_unmatched_fragments(raw.get("unmatched_fragments")))
    fields, unmatched = _normalize_asset_fields(asset_type, payload.get("fields"), unmatched)
    action = _as_text(raw.get("action") or payload.get("action") or "create").lower()
    if action not in ASSET_ACTIONS:
        action = "create"

    normalized = {
        **payload,
        "action": action,
        "asset_type": asset_type,
        "title": asset_title,
        "trigger_context": _as_text(payload.get("trigger_context")),
        "core_content": core_content,
        "summary": _as_text(payload.get("summary") or raw.get("summary")),
        "capability_tags": _normalize_capability_tags(payload.get("capability_tags")),
        "reusable_scenario": _as_text(payload.get("reusable_scenario")),
        "maturity": _normalize_maturity(payload.get("maturity")),
        "fields": fields,
        "unmatched_fragments": unmatched,
    }
    return normalized


def _normalize_ai_items(items):
    if not isinstance(items, list):
        raise InboxServiceError("AI 返回格式异常：items 必须为数组")

    normalized = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        target_type = (raw.get("target_type") or "uncertain").strip()
        if target_type not in database.INBOX_TARGET_TYPES:
            target_type = "uncertain"
        try:
            confidence = float(raw.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        if confidence < CONFIDENCE_UNCERTAIN_THRESHOLD and target_type not in (
            "uncertain",
            "ignored",
        ):
            target_type = "uncertain"
        title = (raw.get("title") or "").strip() or f"未命名条目 {index + 1}"
        content = (raw.get("content") or "").strip()
        reason = (raw.get("reason") or "").strip()
        payload = raw.get("suggested_payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        if target_type == "asset":
            payload = _normalize_asset_payload(raw, payload, title, content)
        normalized.append(
            {
                "target_type": target_type,
                "title": title,
                "content": content,
                "confidence": confidence,
                "reason": reason,
                "suggested_payload": payload,
            }
        )
    return normalized


def _suggestion_response(suggestion):
    return {
        "id": suggestion["id"],
        "target_type": suggestion["target_type"],
        "title": suggestion["title"],
        "content": suggestion["content"],
        "confidence": suggestion["confidence"],
        "reason": suggestion["reason"],
        "suggested_payload": suggestion["suggested_payload"],
        "status": suggestion["status"],
    }


def analyze_text(text, analyze_fn):
    raw_text = (text or "").strip()
    if not raw_text:
        raise InboxServiceError("输入文本不能为空")

    entry = database.create_inbox_entry(raw_text)
    entry_id = entry["id"]
    try:
        ai_data = analyze_fn(raw_text)
        items = _normalize_ai_items(ai_data.get("items", []))
        suggestions = database.create_inbox_suggestions(entry_id, items)
        database.update_inbox_entry_status(entry_id, "analyzed")
        return {
            "inbox_entry_id": entry_id,
            "entry": database.get_inbox_entry(entry_id),
            "suggestions": [_suggestion_response(s) for s in suggestions],
        }
    except InboxServiceError:
        database.update_inbox_entry_status(entry_id, "failed")
        raise
    except ai_service.AIServiceError as exc:
        database.update_inbox_entry_status(entry_id, "failed")
        raise InboxServiceError(str(exc)) from exc
    except Exception as exc:
        database.update_inbox_entry_status(entry_id, "failed")
        message = str(exc) or "AI 解析失败"
        raise InboxServiceError(message) from exc


def get_inbox_detail(entry_id):
    entry = database.get_inbox_entry(entry_id)
    if not entry:
        raise InboxServiceError("inbox 记录不存在")
    suggestions = database.list_inbox_suggestions(entry_id)
    return {
        "entry": entry,
        "suggestions": [_suggestion_response(s) for s in suggestions],
    }


def commit_suggestions(suggestion_ids, override_payload=None):
    try:
        return database.commit_inbox_suggestions(
            suggestion_ids, override_payload=override_payload
        )
    except database.InboxError as exc:
        raise InboxServiceError(str(exc), getattr(exc, "stats", None)) from exc
    except ValueError as exc:
        raise InboxServiceError(str(exc)) from exc


def reject_suggestion(suggestion_id):
    try:
        suggestion = database.reject_inbox_suggestion(suggestion_id)
        return _suggestion_response(suggestion)
    except ValueError as exc:
        raise InboxServiceError(str(exc)) from exc
