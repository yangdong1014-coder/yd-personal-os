import ai_service
import database

CONFIDENCE_UNCERTAIN_THRESHOLD = 0.6


class InboxServiceError(Exception):
    pass


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