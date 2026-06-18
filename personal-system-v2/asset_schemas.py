"""资产类型字段 schema 与迁移辅助。"""

import json

ASSET_TYPES = (
    "本质洞察",
    "方法论",
    "模型",
    "SOP",
    "模板",
    "提示词",
    "案例复盘",
    "清单",
    "原则规则",
    "工具组件",
    "通用资产",
)

MATURITY_LEVELS = ("草稿", "可用", "稳定", "标准化")

LEGACY_ASSET_TYPES = ("知识卡片", "SOP", "提示词", "工作流", "案例复盘", "方法论")

LEGACY_TYPE_DIRECT_MAP = {
    "SOP": "SOP",
    "提示词": "提示词",
    "案例复盘": "案例复盘",
    "方法论": "方法论",
    "工作流": "SOP",
}

GENERIC_ASSET_TYPES = frozenset(
    {"模板", "案例复盘", "清单", "原则规则", "工具组件", "通用资产"}
)

TYPE_FIELD_DEFS = {
    "SOP": [
        ("适用场景", "textarea"),
        ("前置条件", "textarea"),
        ("执行步骤", "textarea"),
        ("关键标准", "textarea"),
        ("常见错误", "textarea"),
        ("验收标准", "textarea"),
    ],
    "本质洞察": [
        ("现象", "textarea"),
        ("表层问题", "textarea"),
        ("底层本质", "textarea"),
        ("推导过程", "textarea"),
        ("适用边界", "textarea"),
        ("可迁移场景", "textarea"),
    ],
    "方法论": [
        ("解决的问题", "textarea"),
        ("核心原则", "textarea"),
        ("操作流程", "textarea"),
        ("判断标准", "textarea"),
        ("案例验证", "textarea"),
        ("可复用场景", "textarea"),
    ],
    "模型": [
        ("核心变量", "textarea"),
        ("变量关系", "textarea"),
        ("运行机制", "textarea"),
        ("适用场景", "textarea"),
        ("局限性", "textarea"),
        ("迭代记录", "textarea"),
    ],
    "提示词": [
        ("使用场景", "textarea"),
        ("角色设定", "textarea"),
        ("输入要求", "textarea"),
        ("执行任务", "textarea"),
        ("输出格式", "textarea"),
        ("示例", "textarea"),
        ("优化记录", "textarea"),
    ],
}

GENERIC_FIELD_DEFS = [
    ("资产说明", "textarea"),
    ("适用场景", "textarea"),
    ("核心内容", "textarea"),
    ("使用方法", "textarea"),
    ("可复用价值", "textarea"),
]

REUSABLE_SCENARIO_KEYS = (
    "可复用场景",
    "可迁移场景",
    "适用场景",
    "使用场景",
)

SUMMARY_PRIORITY_KEYS = (
    "核心内容",
    "底层本质",
    "核心原则",
    "资产说明",
    "执行步骤",
    "解决的问题",
)


def get_field_defs(asset_type):
    if asset_type in TYPE_FIELD_DEFS:
        return TYPE_FIELD_DEFS[asset_type]
    return GENERIC_FIELD_DEFS


def get_frontend_schemas():
    schemas = {}
    for asset_type in ASSET_TYPES:
        schemas[asset_type] = [
            {"key": key, "label": key, "input": input_type}
            for key, input_type in get_field_defs(asset_type)
        ]
    return schemas


def empty_fields(asset_type):
    return {key: "" for key, _ in get_field_defs(asset_type)}


def parse_fields(raw):
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): "" if v is None else str(v) for k, v in raw.items()}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return {str(k): "" if v is None else str(v) for k, v in data.items()}
    return {}


def serialize_fields(fields):
    if not isinstance(fields, dict):
        return "{}"
    cleaned = {str(k): "" if v is None else str(v) for k, v in fields.items()}
    return json.dumps(cleaned, ensure_ascii=False)


def _text_blob(*parts):
    return "\n".join(p.strip() for p in parts if p and str(p).strip())


def infer_legacy_target_type(old_type, title="", core_content=""):
    if old_type in LEGACY_TYPE_DIRECT_MAP:
        return LEGACY_TYPE_DIRECT_MAP[old_type]
    blob = _text_blob(title, core_content)
    if any(k in blob for k in ("方法论", "原则", "流程", "判断标准")):
        return "方法论"
    if any(k in blob for k in ("本质", "洞察", "底层", "现象")):
        return "本质洞察"
    if old_type == "知识卡片":
        return "本质洞察"
    return "通用资产"


def normalize_asset_type(asset_type, title="", core_content=""):
    value = (asset_type or "").strip()
    if value in ASSET_TYPES:
        return value
    if value in LEGACY_ASSET_TYPES or value == "知识卡片":
        return infer_legacy_target_type(value, title, core_content)
    return "通用资产"


def build_fields_from_legacy(asset_type, trigger_context="", core_content=""):
    fields = empty_fields(asset_type)
    trigger = (trigger_context or "").strip()
    core = (core_content or "").strip()
    defs = get_field_defs(asset_type)
    keys = [key for key, _ in defs]

    if asset_type == "SOP":
        if trigger:
            fields["适用场景"] = trigger
        if core:
            fields["执行步骤"] = core
    elif asset_type == "本质洞察":
        if trigger:
            fields["现象"] = trigger
        if core:
            fields["底层本质"] = core
    elif asset_type == "方法论":
        if trigger:
            fields["解决的问题"] = trigger
        if core:
            fields["核心原则"] = core
    elif asset_type == "模型":
        if trigger:
            fields["适用场景"] = trigger
        if core:
            fields["运行机制"] = core
    elif asset_type == "提示词":
        if trigger:
            fields["使用场景"] = trigger
        if core:
            fields["执行任务"] = core
    else:
        if "适用场景" in keys and trigger:
            fields["适用场景"] = trigger
        if "核心内容" in keys and core:
            fields["核心内容"] = core
        elif keys and core:
            fields[keys[0]] = core
    return fields


def extract_summary(fields, fallback=""):
    for key in SUMMARY_PRIORITY_KEYS:
        value = (fields.get(key) or "").strip()
        if value:
            return value[:240]
    text = (fallback or "").strip()
    return text[:240] if text else ""


def extract_reusable_scenario(asset_type, fields):
    for key in REUSABLE_SCENARIO_KEYS:
        if key in fields and (fields[key] or "").strip():
            return (fields[key] or "").strip()
    return ""


def sync_legacy_columns(asset_type, fields):
    """从 fields 推导旧列 trigger_context / core_content，保持兼容。"""
    trigger = ""
    core = ""
    if asset_type == "SOP":
        trigger = fields.get("适用场景", "")
        core = _text_blob(
            fields.get("执行步骤", ""),
            fields.get("关键标准", ""),
            fields.get("验收标准", ""),
        )
    elif asset_type == "本质洞察":
        trigger = fields.get("现象", "")
        core = _text_blob(fields.get("底层本质", ""), fields.get("推导过程", ""))
    elif asset_type == "方法论":
        trigger = fields.get("解决的问题", "")
        core = _text_blob(fields.get("核心原则", ""), fields.get("操作流程", ""))
    elif asset_type == "模型":
        trigger = fields.get("适用场景", "")
        core = _text_blob(fields.get("运行机制", ""), fields.get("变量关系", ""))
    elif asset_type == "提示词":
        trigger = fields.get("使用场景", "")
        core = _text_blob(fields.get("执行任务", ""), fields.get("输出格式", ""))
    else:
        trigger = fields.get("适用场景", "")
        core = fields.get("核心内容", "") or fields.get("资产说明", "")
    return (trigger or "").strip(), (core or "").strip()


def merge_ai_fields(asset_type, existing_fields, ai_data):
    fields = dict(existing_fields or {})
    for key, _ in get_field_defs(asset_type):
        if key in ai_data and ai_data[key] is not None:
            fields[key] = str(ai_data[key]).strip()
    trigger = (ai_data.get("trigger_context") or "").strip()
    core = (ai_data.get("core_content") or "").strip()
    if trigger or core:
        legacy_fields = build_fields_from_legacy(asset_type, trigger, core)
        for key, value in legacy_fields.items():
            if value and not (fields.get(key) or "").strip():
                fields[key] = value
    return fields


def asset_content_valid(asset_type, fields, core_content=""):
    if any((fields.get(key) or "").strip() for key, _ in get_field_defs(asset_type)):
        return True
    return bool((core_content or "").strip())