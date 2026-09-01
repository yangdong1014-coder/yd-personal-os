import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

import asset_schemas

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "yd_os.db")
DB_PATH = os.environ.get("YD_OS_DB_PATH", _DEFAULT_DB_PATH)

SCHEMA_USER_VERSION = 220
PERSONAL_DATA_TABLES = (
    "goals",
    "projects",
    "tasks",
    "reviews",
    "assets",
    "capability_entries",
    "capability_practice_steps",
    "opportunities",
    "experiments",
    "feedback_items",
    "deliberations",
    "positioning_anchor",
    "positioning_calibration",
    "positioning_goal_action",
    "inbox_entries",
    "inbox_suggestions",
)

GOAL_TYPES = ("年度", "季度", "月度", "当前主线")
TASK_STATUSES = ("待处理", "进行中", "完成")
PRIORITY_LEVELS = ("high", "medium", "low")
PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
PRIORITY_SCORES = {"high": 3, "medium": 2, "low": 1}
REVIEW_TYPES = ("每日", "每周", "项目", "事件")
ASSET_TYPES = asset_schemas.ASSET_TYPES
MATURITY_LEVELS = asset_schemas.MATURITY_LEVELS
CAPABILITY_MODULES = (
    "本质力",
    "建模力",
    "体系力",
    "产品力",
    "审美力",
    "创造力",
    "落地力",
    "AI驾驭力",
)
LEVEL_TYPES = ("能力层", "应用层")
INBOX_ENTRY_STATUSES = ("draft", "analyzed", "committed", "archived", "failed")
INBOX_SUGGESTION_STATUSES = ("pending", "accepted", "rejected", "committed")
INBOX_TARGET_TYPES = (
    "goal",
    "project",
    "task",
    "review",
    "asset",
    "capability_entry",
    "opportunity",
    "experiment",
    "feedback",
    "uncertain",
    "ignored",
)
INBOX_COMMITTABLE_TYPES = (
    "goal",
    "project",
    "task",
    "review",
    "asset",
    "capability_entry",
    "opportunity",
    "experiment",
    "feedback",
)
OPPORTUNITY_STATUSES = ("待审计", "值得测试", "已进入MVP", "已转项目", "暂停", "删除", "已归档")
EXPERIMENT_TYPES = ("交易型MVP", "结果型MVP", "反证型MVP", "功能型MVP")
EXPERIMENT_STATUSES = ("设计中", "进行中", "已验证", "未验证", "已转项目", "已暂停")
FEEDBACK_SOURCES = (
    "自我判断",
    "使用者反馈",
    "业务反馈",
    "老板反馈",
    "客户反馈",
    "市场反馈",
    "数据反馈",
)
FEEDBACK_LEVELS = (
    "L0 只是想法",
    "L1 我自己觉得有价值",
    "L2 同事/使用者觉得有价值",
    "L3 业务流程开始使用",
    "L4 产生可量化结果",
    "L5 带来收入、降本、加薪、资源、外部机会",
)
FEEDBACK_RELATED_TYPES = ("opportunity", "experiment", "project", "asset", "review")
DELIBERATION_STATUSES = ("draft", "analyzed", "decided", "reviewed")
DELIBERATION_RELATED_TYPES = ("project", "opportunity")
DELIBERATION_ANALYSIS_FIELDS = (
    "essence",
    "counter_argument",
    "hidden_assumptions",
    "missing_information",
    "validation",
)
DELIBERATION_INITIAL_FIELDS = (
    "title",
    "problem",
    "context",
    "initial_judgment",
    "reasoning",
    "assumptions",
    "related_type",
    "related_id",
)
DELIBERATION_DECISION_FIELDS = (
    "final_judgment",
    "decision",
    "decision_reasoning",
    "next_action",
)
DELIBERATION_REVIEW_FIELDS = (
    "actual_result",
    "judgment_accuracy",
    "judgment_error",
    "key_variable",
    "lesson",
    "principle",
)
ASSET_LEVELS = ("资料", "模板", "方法", "案例", "产品", "筹码")
VALUE_SCORE_FIELDS = (
    "importance_score",
    "feedback_speed_score",
    "revenue_score",
    "asset_score",
    "leverage_score",
)
PROJECT_AUDIT_FIELDS = (
    "core_hypothesis",
    "disconfirming_signal",
    "seven_day_mvp",
    "real_feedback",
    "result_data",
    "asset_deposit",
    "value_capture",
    "stop_condition",
    "value_tags",
    "importance_score",
    "feedback_speed_score",
    "revenue_score",
    "asset_score",
    "leverage_score",
    "total_score",
)
ASSET_VALUE_FIELDS = (
    "asset_level",
    "evidence",
    "external_expression",
    "transferable_scene",
    "productization_next_step",
)
OPPORTUNITY_TEXT_FIELDS = (
    "source",
    "description",
    "related_context",
    "target_user",
    "affects_revenue",
    "affects_cost",
    "affects_efficiency",
    "affects_experience",
    "productization_potential",
    "transaction_potential",
    "seven_day_mvp",
    "case_asset_potential",
    "leverage_potential",
    "next_action",
)
EXPERIMENT_TEXT_FIELDS = (
    "hypothesis",
    "minimum_action",
    "test_target",
    "feedback_source",
    "validation_period",
    "success_criteria",
    "failure_criteria",
    "progress",
    "real_feedback",
    "data_result",
    "next_decision",
    "review_conclusion",
)
INBOX_OVERRIDE_FIELDS = frozenset({"goal_id", "project_id", "target_type"})
INBOX_COMMIT_ORDER = {
    "goal": 0,
    "project": 1,
    "review": 2,
    "asset": 3,
    "capability_entry": 4,
    "task": 5,
    "opportunity": 6,
    "experiment": 7,
    "feedback": 8,
}
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
POSITIONING_CYCLES = ("月度", "季度", "触发式")
POSITIONING_ACTION_TYPES = ("新建目标", "淘汰目标", "降级目标", "升级为主线")
POSITIONING_ACTION_STATUSES = ("pending", "confirmed", "rejected")
GOAL_STATUSES = ("active", "已淘汰")
CAPABILITY_LAYERS = {
    "本质力": "基础认知层",
    "建模力": "基础认知层",
    "体系力": "系统创造层",
    "产品力": "系统创造层",
    "审美力": "系统创造层",
    "创造力": "系统创造层",
    "落地力": "结果放大层",
    "AI驾驭力": "结果放大层",
}
USABLE_MATURITY_LEVELS = ("可用", "稳定", "标准化")
MATURE_MATURITY_LEVELS = ("稳定", "标准化")
DISPLAY_MATURITY_BUCKETS = ("草稿", "可用", "成熟")
RECOMMENDED_CAPABILITY_ASSET_TYPES = {
    "本质力": "本质洞察",
    "建模力": "模型",
    "体系力": "SOP",
    "产品力": "方法论",
    "审美力": "案例复盘",
    "创造力": "模板",
    "落地力": "SOP",
    "AI驾驭力": "提示词",
}
DEFAULT_CAPABILITY_PRACTICE_STEPS = {
    "本质力": [
        {
            "title": "取样",
            "description": "从真实业务、沟通、复盘、案例中抓一个具体问题。",
            "detail": "训练目标是从现象看到底层规律。推荐输出资产：本质洞察、原则规则、判断清单。训练问题：这个问题表面是什么？真实矛盾是什么？如果换一个场景，规律还成立吗？",
        },
        {
            "title": "追问",
            "description": "连续追问为什么，拆掉表层说法。",
            "detail": "识别表层理由背后的真实因果链，避免被现象牵引。",
        },
        {
            "title": "抽象",
            "description": "提炼背后的稳定结构、关键变量和主要矛盾。",
            "detail": "把具体问题抽象成可迁移的结构，找到跨场景成立的规律。",
        },
        {
            "title": "原则",
            "description": "沉淀为一句可复用的判断原则。",
            "detail": "把洞察压缩成未来能快速调用的判断规则。",
        },
    ],
    "建模力": [
        {
            "title": "取样",
            "description": "选择一个重复出现的问题或流程。",
            "detail": "训练目标是把经验变成稳定模型。推荐输出资产：模型、方法论、流程图、判断框架。",
        },
        {
            "title": "归因",
            "description": "找出影响结果的关键因素。",
            "detail": "拆出导致结果差异的关键变量，不停留在感受判断。",
        },
        {
            "title": "变量",
            "description": "把关键因素拆成可观察、可调整的变量。",
            "detail": "让模型可以被检查、被调整、被复用。",
        },
        {
            "title": "建模",
            "description": "形成结构图、公式、SOP 或判断模型。",
            "detail": "把经验固化成别人也能理解和复用的结构。",
        },
    ],
    "体系力": [
        {
            "title": "拆链路",
            "description": "把一个目标拆成完整链路。",
            "detail": "训练目标是从单点动作升级为系统运转。推荐输出资产：系统结构、SOP、机制设计、流程闭环。",
        },
        {
            "title": "分层级",
            "description": "区分目标层、项目层、任务层、资产层。",
            "detail": "让复杂系统分层清晰，避免所有事情混在一起。",
        },
        {
            "title": "连关系",
            "description": "找出模块之间的输入、输出和依赖。",
            "detail": "明确每个模块如何相互影响，找到断点和卡点。",
        },
        {
            "title": "闭循环",
            "description": "形成可持续运转的反馈闭环。",
            "detail": "让系统不是一次性动作，而是能持续迭代。",
        },
    ],
    "产品力": [
        {
            "title": "定场景",
            "description": "明确谁在什么场景下使用。",
            "detail": "训练目标是把功能变成可用、好用、愿意用的产品。推荐输出资产：产品机制、用户路径、体验判断、MVP方案。",
        },
        {
            "title": "找痛点",
            "description": "识别用户真正卡住的地方。",
            "detail": "判断用户不是“不想用”，还是“第一步太难、价值不清、路径太复杂”。",
        },
        {
            "title": "设机制",
            "description": "设计让用户更容易完成动作的机制。",
            "detail": "用默认值、低阻力入口、反馈机制降低使用成本。",
        },
        {
            "title": "验效果",
            "description": "用真实使用反馈验证产品价值。",
            "detail": "不要只看功能完成，要看用户是否真的愿意持续使用。",
        },
    ],
    "审美力": [
        {
            "title": "收集",
            "description": "收集高质量案例。",
            "detail": "训练目标是形成可表达、可判断、可传递的审美标准。推荐输出资产：审美案例、设计原则、表达模板、风格标准。",
        },
        {
            "title": "对比",
            "description": "比较好与差的差异。",
            "detail": "通过对比找到高级感、秩序感、表达力的来源。",
        },
        {
            "title": "判断",
            "description": "提炼审美判断标准。",
            "detail": "把“感觉不错”转化成可以解释的标准。",
        },
        {
            "title": "表达",
            "description": "把审美标准转化为设计语言或修改意见。",
            "detail": "让审美判断可以指导别人修改，而不是只停留在个人感受。",
        },
    ],
    "创造力": [
        {
            "title": "重组",
            "description": "把已有元素重新组合。",
            "detail": "训练目标是从灵感式创造升级为可重复创造。推荐输出资产：创意模型、原型方案、案例复盘、表达模板。",
        },
        {
            "title": "变体",
            "description": "基于一个原型生成多个变化。",
            "detail": "通过变体训练打开可能性，而不是只押注一个想法。",
        },
        {
            "title": "原型",
            "description": "快速做出可看、可测的小样。",
            "detail": "用最小成本把想法变成可以被反馈的东西。",
        },
        {
            "title": "验证",
            "description": "用真实反馈判断是否值得继续。",
            "detail": "用反馈筛选创意，把创造力接入现实结果。",
        },
    ],
    "落地力": [
        {
            "title": "拆解",
            "description": "把目标拆成具体任务。",
            "detail": "训练目标是把想法变成真实结果。推荐输出资产：执行清单、SOP、复盘、项目推进模板。",
        },
        {
            "title": "排期",
            "description": "明确优先级、负责人和时间节点。",
            "detail": "让任务进入真实时间和责任系统。",
        },
        {
            "title": "执行",
            "description": "推动任务进入真实动作。",
            "detail": "把计划从文字变成动作，避免停留在想法层。",
        },
        {
            "title": "复盘",
            "description": "根据结果修正方法和机制。",
            "detail": "用结果反馈优化下一轮行动。",
        },
    ],
    "AI驾驭力": [
        {
            "title": "定场景",
            "description": "找到适合 AI 介入的高频或高价值场景。",
            "detail": "训练目标是从会用 AI 升级为用 AI 构建系统。推荐输出资产：提示词、AI流程、自动化组件、工具说明。",
        },
        {
            "title": "写提示",
            "description": "把任务目标、上下文、边界和输出格式说清楚。",
            "detail": "让 AI 输入稳定，减少随机输出。",
        },
        {
            "title": "建流程",
            "description": "把单次 AI 使用固化为工作流。",
            "detail": "从一次性问答升级为可重复流程。",
        },
        {
            "title": "资产化",
            "description": "把提示词、流程、模板沉淀为可复用资产。",
            "detail": "让 AI 能力进入个人资产库，而不是停留在临时使用。",
        },
    ],
}


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _resolve_owner_id(conn, user_id):
    """Validate the explicit owner supplied by the authenticated request context."""
    if user_id is None:
        raise OwnershipContextError("业务数据访问必须提供 user_id")
    try:
        owner_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise OwnershipContextError("无效的数据所有者") from exc
    if owner_id <= 0 or not conn.execute(
        "SELECT 1 FROM users WHERE id = ?", (owner_id,)
    ).fetchone():
        raise OwnershipContextError("数据所有者不存在")
    return owner_id


def _row_to_dict(row):
    return dict(row) if row else None


def _normalize_priority(value, strict=False):
    if value in PRIORITY_LEVELS:
        return value
    if value in (None, ""):
        return "medium"
    if strict:
        raise ValueError("无效的优先级")
    return "medium"


def _clean_text(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _score(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(number, 5))


def _value_scores_from_payload(payload, existing=None):
    if existing is None:
        existing = {}
    elif not isinstance(existing, dict):
        existing = dict(existing)
    scores = {}
    for field in VALUE_SCORE_FIELDS:
        scores[field] = _score(payload.get(field, existing.get(field, 0)))
    scores["total_score"] = sum(scores.values())
    return scores


def _priority_label(value):
    return PRIORITY_LABELS[_normalize_priority(value)]


def _priority_score(value):
    return PRIORITY_SCORES[_normalize_priority(value)]


def _project_row(row):
    data = _row_to_dict(row)
    if data:
        data["priority"] = _normalize_priority(data.get("priority"))
        for field in VALUE_SCORE_FIELDS:
            data[field] = _score(data.get(field))
        data["total_score"] = sum(data[field] for field in VALUE_SCORE_FIELDS)
        for field in PROJECT_AUDIT_FIELDS:
            if field.endswith("_score"):
                continue
            data[field] = data.get(field) or ""
    return data


def _task_row(row):
    data = _row_to_dict(row)
    if data:
        data["priority"] = _normalize_priority(data.get("priority"))
    return data


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _today_local():
    return datetime.now().strftime("%Y-%m-%d")


def _as_text(value, default=""):
    """将 AI/JSON 中的字段安全转为字符串（兼容 bool、数字、列表等）。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [_as_text(item, "") for item in value]
        joined = ", ".join(part for part in parts if part)
        return joined if joined else default
    text = str(value).strip()
    return text if text else default


def _week_start_local():
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate_projects_table(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    columns = _table_columns(conn, "projects")
    if "priority" not in columns:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'"
        )


def _migrate_tasks_table(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    columns = _table_columns(conn, "tasks")
    if "today_progress" not in columns:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN today_progress INTEGER NOT NULL DEFAULT 0"
        )
    if "today_progress_date" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN today_progress_date TEXT")
    if "priority" not in columns:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'"
        )


def _add_columns(conn, table, additions):
    columns = _table_columns(conn, table)
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_projects_value_fields(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    _add_columns(conn, "projects", {
        "core_hypothesis": "TEXT NOT NULL DEFAULT ''",
        "disconfirming_signal": "TEXT NOT NULL DEFAULT ''",
        "seven_day_mvp": "TEXT NOT NULL DEFAULT ''",
        "real_feedback": "TEXT NOT NULL DEFAULT ''",
        "result_data": "TEXT NOT NULL DEFAULT ''",
        "asset_deposit": "TEXT NOT NULL DEFAULT ''",
        "value_capture": "TEXT NOT NULL DEFAULT ''",
        "stop_condition": "TEXT NOT NULL DEFAULT ''",
        "value_tags": "TEXT NOT NULL DEFAULT ''",
        "importance_score": "INTEGER NOT NULL DEFAULT 0",
        "feedback_speed_score": "INTEGER NOT NULL DEFAULT 0",
        "revenue_score": "INTEGER NOT NULL DEFAULT 0",
        "asset_score": "INTEGER NOT NULL DEFAULT 0",
        "leverage_score": "INTEGER NOT NULL DEFAULT 0",
        "total_score": "INTEGER NOT NULL DEFAULT 0",
    })


def _migrate_value_tables(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            related_context TEXT NOT NULL DEFAULT '',
            target_user TEXT NOT NULL DEFAULT '',
            affects_revenue TEXT NOT NULL DEFAULT '',
            affects_cost TEXT NOT NULL DEFAULT '',
            affects_efficiency TEXT NOT NULL DEFAULT '',
            affects_experience TEXT NOT NULL DEFAULT '',
            productization_potential TEXT NOT NULL DEFAULT '',
            transaction_potential TEXT NOT NULL DEFAULT '',
            seven_day_mvp TEXT NOT NULL DEFAULT '',
            case_asset_potential TEXT NOT NULL DEFAULT '',
            leverage_potential TEXT NOT NULL DEFAULT '',
            importance_score INTEGER NOT NULL DEFAULT 0,
            feedback_speed_score INTEGER NOT NULL DEFAULT 0,
            revenue_score INTEGER NOT NULL DEFAULT 0,
            asset_score INTEGER NOT NULL DEFAULT 0,
            leverage_score INTEGER NOT NULL DEFAULT 0,
            total_score INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '待审计',
            next_action TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER,
            name TEXT NOT NULL,
            hypothesis TEXT NOT NULL DEFAULT '',
            experiment_type TEXT NOT NULL DEFAULT '结果型MVP',
            minimum_action TEXT NOT NULL DEFAULT '',
            test_target TEXT NOT NULL DEFAULT '',
            feedback_source TEXT NOT NULL DEFAULT '',
            validation_period TEXT NOT NULL DEFAULT '',
            success_criteria TEXT NOT NULL DEFAULT '',
            failure_criteria TEXT NOT NULL DEFAULT '',
            progress TEXT NOT NULL DEFAULT '',
            real_feedback TEXT NOT NULL DEFAULT '',
            data_result TEXT NOT NULL DEFAULT '',
            next_decision TEXT NOT NULL DEFAULT '',
            review_conclusion TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '设计中',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS feedback_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            related_type TEXT NOT NULL DEFAULT '',
            related_id INTEGER,
            title TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '自我判断',
            level TEXT NOT NULL DEFAULT 'L0 只是想法',
            content TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            next_action TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _migrate_deliberations_table(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deliberations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            problem TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            initial_judgment TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            assumptions TEXT NOT NULL,
            related_type TEXT NOT NULL DEFAULT '',
            related_id INTEGER,
            ai_analysis TEXT NOT NULL DEFAULT '{}',
            final_judgment TEXT NOT NULL DEFAULT '',
            decision TEXT NOT NULL DEFAULT '',
            decision_reasoning TEXT NOT NULL DEFAULT '',
            next_action TEXT NOT NULL DEFAULT '',
            actual_result TEXT NOT NULL DEFAULT '',
            judgment_accuracy TEXT NOT NULL DEFAULT '',
            judgment_error TEXT NOT NULL DEFAULT '',
            key_variable TEXT NOT NULL DEFAULT '',
            lesson TEXT NOT NULL DEFAULT '',
            principle TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _migrate_users_table(conn):
    """Create the identity store before any owned business table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE
                CHECK (length(trim(username)) > 0 AND instr(username, '@') = 0),
            email TEXT NOT NULL COLLATE NOCASE UNIQUE
                CHECK (length(trim(email)) > 0 AND instr(email, '@') > 1),
            password_hash TEXT NOT NULL CHECK (length(password_hash) > 0),
            role TEXT NOT NULL DEFAULT 'user'
                CHECK (role IN ('admin', 'user')),
            is_active INTEGER NOT NULL DEFAULT 1
                CHECK (is_active IN (0, 1)),
            must_change_password INTEGER NOT NULL DEFAULT 0
                CHECK (must_change_password IN (0, 1)),
            auth_version INTEGER NOT NULL DEFAULT 1
                CHECK (auth_version >= 1),
            failed_login_count INTEGER NOT NULL DEFAULT 0
                CHECK (failed_login_count >= 0),
            locked_until TEXT,
            last_login_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


class LegacyMigrationRequired(RuntimeError):
    """Raised when an old database must use the explicit staged migration."""


class OwnershipContextError(RuntimeError):
    """Raised when a business write has no unambiguous owner."""


def _existing_table_names(conn):
    return {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        if not row["name"].startswith("sqlite_")
    }


def _foreign_key_groups(conn, table):
    groups = {}
    for row in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
        group = groups.setdefault(
            int(row["id"]), {"table": row["table"], "columns": {}}
        )
        group["columns"][row["from"]] = row["to"]
    return tuple(groups.values())


def _has_unique_index(conn, table, columns):
    expected = list(columns)
    for index in conn.execute(f'PRAGMA index_list("{table}")').fetchall():
        if not int(index["unique"]):
            continue
        actual = [
            row["name"]
            for row in conn.execute(
                f'PRAGMA index_info("{index["name"]}")'
            ).fetchall()
        ]
        if actual == expected:
            return True
    return False


def _assert_v22_or_fresh_schema(conn):
    """Fail closed instead of silently binding legacy rows to an account."""
    existing = _existing_table_names(conn)
    present = set(PERSONAL_DATA_TABLES) & existing
    if not present:
        return

    expected = set(PERSONAL_DATA_TABLES)
    if present != expected:
        missing = ", ".join(sorted(expected - present))
        raise LegacyMigrationRequired(
            "检测到不完整的旧业务 schema；请先运行离线 v2.2 staged migration。"
            f" 缺少表：{missing}"
        )
    if "users" not in existing:
        raise LegacyMigrationRequired(
            "检测到旧业务数据库；普通 app 启动不会自动创建管理员或绑定历史数据。"
        )

    invalid = []
    for table in PERSONAL_DATA_TABLES:
        columns = {
            row["name"]: row
            for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        }
        user_column = columns.get("user_id")
        if user_column is None or int(user_column["notnull"]) != 1:
            invalid.append(table)
            continue
        foreign_keys = _foreign_key_groups(conn, table)
        if not any(
            item["table"] == "users"
            and item["columns"] == {"user_id": "id"}
            for item in foreign_keys
        ):
            invalid.append(f"{table}(user FK)")
    if invalid:
        raise LegacyMigrationRequired(
            "检测到未完成数据所有权升级的业务表；请运行离线 v2.2 staged migration："
            + ", ".join(invalid)
        )

    composite_relations = (
        ("projects", "goals", {"goal_id": "id", "user_id": "user_id"}),
        ("tasks", "projects", {"project_id": "id", "user_id": "user_id"}),
        (
            "positioning_goal_action",
            "positioning_calibration",
            {"calibration_id": "id", "user_id": "user_id"},
        ),
        (
            "inbox_suggestions",
            "inbox_entries",
            {"inbox_entry_id": "id", "user_id": "user_id"},
        ),
    )
    missing_relations = []
    for table, parent, columns in composite_relations:
        if not any(
            item["table"] == parent and item["columns"] == columns
            for item in _foreign_key_groups(conn, table)
        ):
            missing_relations.append(f"{table}→{parent}")
    if missing_relations:
        raise LegacyMigrationRequired(
            "检测到缺少同用户复合外键的非标准 schema："
            + ", ".join(missing_relations)
        )
    if not _has_unique_index(conn, "positioning_anchor", ("user_id",)):
        raise LegacyMigrationRequired(
            "positioning_anchor 缺少每用户单例约束；请重新生成 staged DB"
        )


def _create_v22_business_tables(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            UNIQUE (id, user_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            goal_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL,
            core_hypothesis TEXT NOT NULL DEFAULT '',
            disconfirming_signal TEXT NOT NULL DEFAULT '',
            seven_day_mvp TEXT NOT NULL DEFAULT '',
            real_feedback TEXT NOT NULL DEFAULT '',
            result_data TEXT NOT NULL DEFAULT '',
            asset_deposit TEXT NOT NULL DEFAULT '',
            value_capture TEXT NOT NULL DEFAULT '',
            stop_condition TEXT NOT NULL DEFAULT '',
            value_tags TEXT NOT NULL DEFAULT '',
            importance_score INTEGER NOT NULL DEFAULT 0,
            feedback_speed_score INTEGER NOT NULL DEFAULT 0,
            revenue_score INTEGER NOT NULL DEFAULT 0,
            asset_score INTEGER NOT NULL DEFAULT 0,
            leverage_score INTEGER NOT NULL DEFAULT 0,
            total_score INTEGER NOT NULL DEFAULT 0,
            UNIQUE (id, user_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (goal_id, user_id)
                REFERENCES goals(id, user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待处理',
            priority TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL,
            today_progress INTEGER NOT NULL DEFAULT 0,
            today_progress_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (project_id, user_id)
                REFERENCES projects(id, user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            review_date TEXT NOT NULL,
            type TEXT NOT NULL,
            what_done TEXT NOT NULL DEFAULT '',
            stuck TEXT NOT NULL DEFAULT '',
            next_adjust TEXT NOT NULL DEFAULT '',
            depositable TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            trigger_context TEXT NOT NULL DEFAULT '',
            core_content TEXT NOT NULL DEFAULT '',
            asset_type TEXT NOT NULL,
            capability_tags TEXT NOT NULL DEFAULT '[]',
            source_review_id INTEGER,
            created_at TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            fields TEXT NOT NULL DEFAULT '{}',
            reusable_scenario TEXT NOT NULL DEFAULT '',
            maturity TEXT NOT NULL DEFAULT '草稿',
            reuse_count INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL DEFAULT '',
            source_id INTEGER,
            updated_at TEXT NOT NULL DEFAULT '',
            asset_level TEXT NOT NULL DEFAULT '资料',
            evidence TEXT NOT NULL DEFAULT '',
            external_expression TEXT NOT NULL DEFAULT '',
            transferable_scene TEXT NOT NULL DEFAULT '',
            productization_next_step TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (source_review_id) REFERENCES reviews(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS capability_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            content TEXT NOT NULL,
            source_project TEXT,
            level_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS capability_practice_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module TEXT NOT NULL,
            step_order INTEGER NOT NULL CHECK (step_order > 0),
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            related_context TEXT NOT NULL DEFAULT '',
            target_user TEXT NOT NULL DEFAULT '',
            affects_revenue TEXT NOT NULL DEFAULT '',
            affects_cost TEXT NOT NULL DEFAULT '',
            affects_efficiency TEXT NOT NULL DEFAULT '',
            affects_experience TEXT NOT NULL DEFAULT '',
            productization_potential TEXT NOT NULL DEFAULT '',
            transaction_potential TEXT NOT NULL DEFAULT '',
            seven_day_mvp TEXT NOT NULL DEFAULT '',
            case_asset_potential TEXT NOT NULL DEFAULT '',
            leverage_potential TEXT NOT NULL DEFAULT '',
            importance_score INTEGER NOT NULL DEFAULT 0,
            feedback_speed_score INTEGER NOT NULL DEFAULT 0,
            revenue_score INTEGER NOT NULL DEFAULT 0,
            asset_score INTEGER NOT NULL DEFAULT 0,
            leverage_score INTEGER NOT NULL DEFAULT 0,
            total_score INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '待审计',
            next_action TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            opportunity_id INTEGER,
            name TEXT NOT NULL,
            hypothesis TEXT NOT NULL DEFAULT '',
            experiment_type TEXT NOT NULL DEFAULT '结果型MVP',
            minimum_action TEXT NOT NULL DEFAULT '',
            test_target TEXT NOT NULL DEFAULT '',
            feedback_source TEXT NOT NULL DEFAULT '',
            validation_period TEXT NOT NULL DEFAULT '',
            success_criteria TEXT NOT NULL DEFAULT '',
            failure_criteria TEXT NOT NULL DEFAULT '',
            progress TEXT NOT NULL DEFAULT '',
            real_feedback TEXT NOT NULL DEFAULT '',
            data_result TEXT NOT NULL DEFAULT '',
            next_decision TEXT NOT NULL DEFAULT '',
            review_conclusion TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '设计中',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (opportunity_id)
                REFERENCES opportunities(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS feedback_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            related_type TEXT NOT NULL DEFAULT '' CHECK (
                related_type IN ('', 'opportunity', 'experiment', 'project', 'asset', 'review')
            ),
            related_id INTEGER,
            title TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '自我判断',
            level TEXT NOT NULL DEFAULT 'L0 只是想法',
            content TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            next_action TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS deliberations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            problem TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            initial_judgment TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            assumptions TEXT NOT NULL,
            related_type TEXT NOT NULL DEFAULT '' CHECK (
                related_type IN ('', 'project', 'opportunity')
            ),
            related_id INTEGER,
            ai_analysis TEXT NOT NULL DEFAULT '{}',
            final_judgment TEXT NOT NULL DEFAULT '',
            decision TEXT NOT NULL DEFAULT '',
            decision_reasoning TEXT NOT NULL DEFAULT '',
            next_action TEXT NOT NULL DEFAULT '',
            actual_result TEXT NOT NULL DEFAULT '',
            judgment_accuracy TEXT NOT NULL DEFAULT '',
            judgment_error TEXT NOT NULL DEFAULT '',
            key_variable TEXT NOT NULL DEFAULT '',
            lesson TEXT NOT NULL DEFAULT '',
            principle TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS positioning_anchor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            first_principle TEXT NOT NULL DEFAULT '',
            identity_core TEXT NOT NULL DEFAULT '',
            flywheel_def TEXT NOT NULL DEFAULT '',
            current_stage TEXT NOT NULL DEFAULT '',
            north_star TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS positioning_calibration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            calibrated_at TEXT NOT NULL,
            cycle TEXT NOT NULL DEFAULT '触发式',
            primary_contradiction TEXT NOT NULL DEFAULT '',
            doing_but_shouldnt TEXT NOT NULL DEFAULT '',
            should_but_not_doing TEXT NOT NULL DEFAULT '',
            alignment_review TEXT NOT NULL DEFAULT '',
            conclusion TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE (id, user_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS positioning_goal_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            calibration_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            target_goal_id INTEGER,
            payload TEXT NOT NULL DEFAULT '{}',
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (calibration_id, user_id)
                REFERENCES positioning_calibration(id, user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS inbox_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            UNIQUE (id, user_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS inbox_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            inbox_entry_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            suggested_payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (inbox_entry_id, user_id)
                REFERENCES inbox_entries(id, user_id) ON DELETE CASCADE
        );
        """
    )


def _create_v22_indexes(conn):
    for table in PERSONAL_DATA_TABLES:
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON "{table}" (user_id)'
        )
    relation_indexes = (
        ("projects", "goal_id"),
        ("tasks", "project_id"),
        ("assets", "source_review_id"),
        ("capability_practice_steps", "module, step_order"),
        ("experiments", "opportunity_id"),
        ("feedback_items", "related_type, related_id"),
        ("deliberations", "related_type, related_id"),
        ("positioning_goal_action", "calibration_id"),
        ("positioning_goal_action", "target_goal_id"),
        ("inbox_suggestions", "inbox_entry_id"),
    )
    for table, columns in relation_indexes:
        suffix = columns.replace(", ", "_")
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_{suffix} "
            f'ON "{table}" (user_id, {columns})'
        )


def _create_owner_guard_triggers(conn):
    for table in PERSONAL_DATA_TABLES:
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_owner_immutable
            BEFORE UPDATE OF user_id ON "{table}"
            WHEN OLD.user_id != NEW.user_id
            BEGIN
                SELECT RAISE(ABORT, 'business row owner is immutable');
            END
            """
        )

    optional_relations = (
        ("assets", "source_review_id", "reviews"),
        ("experiments", "opportunity_id", "opportunities"),
        ("positioning_goal_action", "target_goal_id", "goals"),
    )
    for table, column, parent in optional_relations:
        for operation, suffix in (("INSERT", "insert"), ("UPDATE", "update")):
            update_columns = f" OF user_id, {column}" if operation == "UPDATE" else ""
            conn.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_{column}_owner_{suffix}
                BEFORE {operation}{update_columns} ON "{table}"
                WHEN NEW.{column} IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1 FROM "{parent}"
                    WHERE id = NEW.{column} AND user_id = NEW.user_id
                 )
                BEGIN
                    SELECT RAISE(ABORT, 'cross-user relation is not allowed');
                END
                """
            )

    polymorphic_relations = {
        "feedback_items": {
            "opportunity": "opportunities",
            "experiment": "experiments",
            "project": "projects",
            "asset": "assets",
            "review": "reviews",
        },
        "deliberations": {
            "project": "projects",
            "opportunity": "opportunities",
        },
    }
    for table, targets in polymorphic_relations.items():
        invalid_cases = " OR ".join(
            "(NEW.related_type = '"
            + related_type
            + f"' AND NOT EXISTS (SELECT 1 FROM \"{target}\" "
            "WHERE id = NEW.related_id AND user_id = NEW.user_id))"
            for related_type, target in targets.items()
        )
        for operation, suffix in (("INSERT", "insert"), ("UPDATE", "update")):
            update_columns = (
                " OF user_id, related_type, related_id"
                if operation == "UPDATE"
                else ""
            )
            conn.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_related_owner_{suffix}
                BEFORE {operation}{update_columns} ON "{table}"
                WHEN NEW.related_id IS NOT NULL AND ({invalid_cases})
                BEGIN
                    SELECT RAISE(ABORT, 'cross-user polymorphic relation is not allowed');
                END
                """
            )


def initialize_v22_schema(conn):
    """Create or validate an empty/current v2.2 schema without migrating legacy rows."""
    conn.execute("PRAGMA foreign_keys = ON")
    _assert_v22_or_fresh_schema(conn)
    _migrate_users_table(conn)
    _create_v22_business_tables(conn)
    _create_v22_indexes(conn)
    _create_owner_guard_triggers(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_USER_VERSION}")


def init_db():
    conn = get_connection()
    try:
        initialize_v22_schema(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_positioning_tables(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS positioning_anchor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_principle TEXT NOT NULL DEFAULT '',
            identity_core TEXT NOT NULL DEFAULT '',
            flywheel_def TEXT NOT NULL DEFAULT '',
            current_stage TEXT NOT NULL DEFAULT '',
            north_star TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positioning_calibration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calibrated_at TEXT NOT NULL,
            cycle TEXT NOT NULL DEFAULT '触发式',
            primary_contradiction TEXT NOT NULL DEFAULT '',
            doing_but_shouldnt TEXT NOT NULL DEFAULT '',
            should_but_not_doing TEXT NOT NULL DEFAULT '',
            alignment_review TEXT NOT NULL DEFAULT '',
            conclusion TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positioning_goal_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calibration_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            target_goal_id INTEGER,
            payload TEXT NOT NULL DEFAULT '{}',
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (calibration_id) REFERENCES positioning_calibration(id) ON DELETE CASCADE
        );
        """
    )


def _migrate_goals_status(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    columns = _table_columns(conn, "goals")
    if "status" not in columns:
        conn.execute(
            "ALTER TABLE goals ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
        )


def _migrate_inbox_tables(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS inbox_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_text TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inbox_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inbox_entry_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            suggested_payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (inbox_entry_id) REFERENCES inbox_entries(id) ON DELETE CASCADE
        );
        """
    )


def _migrate_assets_table(conn):
    raise LegacyMigrationRequired("legacy schema migration must use the staged tool")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
    additions = {
        "summary": "TEXT NOT NULL DEFAULT ''",
        "fields": "TEXT NOT NULL DEFAULT '{}'",
        "reusable_scenario": "TEXT NOT NULL DEFAULT ''",
        "maturity": "TEXT NOT NULL DEFAULT '草稿'",
        "reuse_count": "INTEGER NOT NULL DEFAULT 0",
        "source_type": "TEXT NOT NULL DEFAULT ''",
        "source_id": "INTEGER",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        "asset_level": "TEXT NOT NULL DEFAULT '资料'",
        "evidence": "TEXT NOT NULL DEFAULT ''",
        "external_expression": "TEXT NOT NULL DEFAULT ''",
        "transferable_scene": "TEXT NOT NULL DEFAULT ''",
        "productization_next_step": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE assets ADD COLUMN {name} {definition}")

    rows = conn.execute("SELECT * FROM assets").fetchall()
    for row in rows:
        data = dict(row)
        fields = asset_schemas.parse_fields(data.get("fields"))
        title = data.get("title") or ""
        trigger = data.get("trigger_context") or ""
        core = data.get("core_content") or ""
        new_type = asset_schemas.normalize_asset_type(
            data.get("asset_type"), title, core
        )
        if not fields:
            fields = asset_schemas.build_fields_from_legacy(new_type, trigger, core)
        summary = (data.get("summary") or "").strip()
        if not summary:
            summary = asset_schemas.extract_summary(fields, core)
        reusable = (data.get("reusable_scenario") or "").strip()
        if not reusable:
            reusable = asset_schemas.extract_reusable_scenario(new_type, fields)
        maturity = data.get("maturity") or "草稿"
        if maturity not in MATURITY_LEVELS:
            maturity = "可用" if (summary or core) else "草稿"
        updated_at = (data.get("updated_at") or "").strip() or data.get("created_at")
        source_type = data.get("source_type") or ""
        if not source_type and data.get("source_review_id"):
            source_type = "review"
        legacy_trigger, legacy_core = asset_schemas.sync_legacy_columns(new_type, fields)
        if not legacy_trigger:
            legacy_trigger = trigger
        if not legacy_core:
            legacy_core = core
        conn.execute(
            """
            UPDATE assets SET
                asset_type = ?,
                summary = ?,
                fields = ?,
                reusable_scenario = ?,
                maturity = ?,
                source_type = ?,
                updated_at = ?,
                trigger_context = ?,
                core_content = ?
            WHERE id = ?
            """,
            (
                new_type,
                summary,
                asset_schemas.serialize_fields(fields),
                reusable,
                maturity,
                source_type,
                updated_at,
                legacy_trigger,
                legacy_core,
                data["id"],
            ),
        )


def _demote_other_mainline_goals(conn, keep_goal_id, user_id):
    conn.execute(
        """
        UPDATE goals SET type = '季度'
        WHERE user_id = ? AND type = '当前主线' AND id != ?
        """,
        (user_id, keep_goal_id),
        )


def ensure_default_capability_practice_steps(conn, user_id):
    user_id = _resolve_owner_id(conn, user_id)
    now = _now()
    for module in CAPABILITY_MODULES:
        existing = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM capability_practice_steps
            WHERE user_id = ? AND module = ?
            """,
            (user_id, module),
        ).fetchone()
        if existing and existing["cnt"]:
            continue
        for index, step in enumerate(DEFAULT_CAPABILITY_PRACTICE_STEPS[module], start=1):
            conn.execute(
                """
                INSERT INTO capability_practice_steps (
                    user_id, module, step_order, title, description, detail,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    module,
                    index,
                    step["title"],
                    step["description"],
                    step["detail"],
                    now,
                    now,
                ),
            )


def _normalize_mainline_goals(conn, user_id):
    user_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT id FROM goals
        WHERE user_id = ? AND type = '当前主线'
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    if len(rows) <= 1:
        return
    keep_id = rows[0][0]
    _demote_other_mainline_goals(conn, keep_id, user_id)


def _deliberation_row(row):
    data = _row_to_dict(row)
    if not data:
        return None
    raw_analysis = data.get("ai_analysis")
    if isinstance(raw_analysis, dict):
        analysis = raw_analysis
    else:
        try:
            analysis = json.loads(raw_analysis or "{}")
        except (TypeError, json.JSONDecodeError):
            analysis = {}
    data["ai_analysis"] = analysis if isinstance(analysis, dict) else {}
    data["reviewed"] = data.get("status") == "reviewed"
    return data


def _normalize_deliberation_relation(conn, related_type, related_id, user_id):
    related_type = _clean_text(related_type)
    if not related_type:
        return "", None
    if related_type not in DELIBERATION_RELATED_TYPES:
        raise ValueError("无效的关联类型")
    try:
        related_id = int(related_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("请选择有效的关联对象") from exc
    if related_id <= 0:
        raise ValueError("请选择有效的关联对象")

    table = "projects" if related_type == "project" else "opportunities"
    if not conn.execute(
        f"SELECT id FROM {table} WHERE id = ? AND user_id = ?",
        (related_id, int(user_id)),
    ).fetchone():
        label = "项目" if related_type == "project" else "机会"
        raise ValueError(f"关联的{label}不存在")
    return related_type, related_id


def _clean_deliberation_fields(payload, fields):
    return {field: _clean_text(payload.get(field)) for field in fields}


def _require_deliberation_fields(values, fields, message):
    if any(not values.get(field) for field in fields):
        raise ValueError(message)


def _deliberation_title_from_problem(problem, max_length=48):
    text = " ".join(_clean_text(problem).split())
    if not text:
        return ""
    sentence_end = len(text)
    for marker in ("。", "！", "？", "!", "?"):
        index = text.find(marker)
        if index >= 0:
            sentence_end = min(sentence_end, index + 1)
    title = text[:sentence_end]
    if len(title) <= max_length:
        return title
    return f"{title[: max_length - 1].rstrip()}…"


def create_deliberation(payload, user_id):
    payload = payload or {}
    values = _clean_deliberation_fields(payload, DELIBERATION_INITIAL_FIELDS)
    _require_deliberation_fields(
        values,
        ("problem", "initial_judgment"),
        "请先写下需要判断的问题和你的当前判断",
    )
    if not values["title"]:
        values["title"] = _deliberation_title_from_problem(values["problem"])

    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        related_type, related_id = _normalize_deliberation_relation(
            conn,
            values["related_type"],
            payload.get("related_id"),
            owner_id,
        )
        now = _now()
        cursor = conn.execute(
            """
            INSERT INTO deliberations (
                user_id, title, problem, context, initial_judgment, reasoning,
                assumptions, related_type, related_id, ai_analysis, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 'draft', ?, ?)
            """,
            (
                owner_id,
                values["title"],
                values["problem"],
                values["context"],
                values["initial_judgment"],
                values["reasoning"],
                values["assumptions"],
                related_type,
                related_id,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM deliberations WHERE id = ? AND user_id = ?",
            (cursor.lastrowid, owner_id),
        ).fetchone()
        return _deliberation_row(row)
    finally:
        conn.close()


def list_deliberations(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM deliberations
        WHERE user_id = ?
        ORDER BY updated_at DESC, created_at DESC, id DESC
        """,
        (owner_id,),
    ).fetchall()
    conn.close()
    return [_deliberation_row(row) for row in rows]


def get_deliberation(deliberation_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM deliberations WHERE id = ? AND user_id = ?",
        (deliberation_id, owner_id),
    ).fetchone()
    conn.close()
    return _deliberation_row(row)


def update_deliberation(deliberation_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        row = conn.execute(
            "SELECT * FROM deliberations WHERE id = ? AND user_id = ?",
            (deliberation_id, owner_id),
        ).fetchone()
        if not row:
            raise ValueError("推演不存在")
        current = _deliberation_row(row)
        if current["status"] != "draft":
            raise ValueError("AI 对抗开始后不能修改初始判断")

        merged = {
            field: payload.get(field, current.get(field))
            for field in DELIBERATION_INITIAL_FIELDS
        }
        values = _clean_deliberation_fields(merged, DELIBERATION_INITIAL_FIELDS)
        _require_deliberation_fields(
            values,
            ("problem", "initial_judgment"),
            "请先写下需要判断的问题和你的当前判断",
        )
        if not values["title"]:
            values["title"] = _deliberation_title_from_problem(values["problem"])
        related_type, related_id = _normalize_deliberation_relation(
            conn,
            values["related_type"],
            merged.get("related_id"),
            owner_id,
        )
        conn.execute(
            """
            UPDATE deliberations SET
                title = ?, problem = ?, context = ?, initial_judgment = ?,
                reasoning = ?, assumptions = ?, related_type = ?, related_id = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                values["title"],
                values["problem"],
                values["context"],
                values["initial_judgment"],
                values["reasoning"],
                values["assumptions"],
                related_type,
                related_id,
                _now(),
                deliberation_id,
                owner_id,
            ),
        )
        conn.commit()
        return get_deliberation(deliberation_id, owner_id)
    finally:
        conn.close()


def save_deliberation_analysis(deliberation_id, analysis, user_id):
    if not isinstance(analysis, dict):
        raise ValueError("AI 分析结果格式无效")
    normalized = {}
    for field in DELIBERATION_ANALYSIS_FIELDS:
        value = analysis.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"AI 分析缺少有效字段 {field}")
        normalized[field] = value.strip()

    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        row = conn.execute(
            "SELECT status FROM deliberations WHERE id = ? AND user_id = ?",
            (deliberation_id, owner_id),
        ).fetchone()
        if not row:
            raise ValueError("推演不存在")
        if row["status"] != "draft":
            raise ValueError("只有待分析的推演可以保存 AI 分析")
        conn.execute(
            """
            UPDATE deliberations
            SET ai_analysis = ?, status = 'analyzed', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                json.dumps(normalized, ensure_ascii=False),
                _now(),
                deliberation_id,
                owner_id,
            ),
        )
        conn.commit()
        return get_deliberation(deliberation_id, owner_id)
    finally:
        conn.close()


def save_deliberation_decision(deliberation_id, payload, user_id):
    payload = payload or {}
    values = _clean_deliberation_fields(payload, DELIBERATION_DECISION_FIELDS)
    _require_deliberation_fields(
        values,
        DELIBERATION_DECISION_FIELDS,
        "请完整填写最终判断、决定、理由和下一步最小行动",
    )

    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        row = conn.execute(
            "SELECT status FROM deliberations WHERE id = ? AND user_id = ?",
            (deliberation_id, owner_id),
        ).fetchone()
        if not row:
            raise ValueError("推演不存在")
        if row["status"] not in ("analyzed", "decided"):
            raise ValueError("请先完成 AI 对抗，再保存最终判断")
        conn.execute(
            """
            UPDATE deliberations SET
                final_judgment = ?, decision = ?, decision_reasoning = ?,
                next_action = ?, status = 'decided', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                values["final_judgment"],
                values["decision"],
                values["decision_reasoning"],
                values["next_action"],
                _now(),
                deliberation_id,
                owner_id,
            ),
        )
        conn.commit()
        return get_deliberation(deliberation_id, owner_id)
    finally:
        conn.close()


def save_deliberation_review(deliberation_id, payload, user_id):
    payload = payload or {}
    values = _clean_deliberation_fields(payload, DELIBERATION_REVIEW_FIELDS)
    _require_deliberation_fields(
        values,
        DELIBERATION_REVIEW_FIELDS,
        "请完整填写现实结果、判断得失、关键变量、教训和原则",
    )

    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        row = conn.execute(
            "SELECT status FROM deliberations WHERE id = ? AND user_id = ?",
            (deliberation_id, owner_id),
        ).fetchone()
        if not row:
            raise ValueError("推演不存在")
        if row["status"] not in ("decided", "reviewed"):
            raise ValueError("请先完成最终判断，再记录现实反馈")
        conn.execute(
            """
            UPDATE deliberations SET
                actual_result = ?, judgment_accuracy = ?, judgment_error = ?,
                key_variable = ?, lesson = ?, principle = ?,
                status = 'reviewed', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                values["actual_result"],
                values["judgment_accuracy"],
                values["judgment_error"],
                values["key_variable"],
                values["lesson"],
                values["principle"],
                _now(),
                deliberation_id,
                owner_id,
            ),
        )
        conn.commit()
        return get_deliberation(deliberation_id, owner_id)
    finally:
        conn.close()


def delete_deliberation(deliberation_id, user_id):
    return _delete_entity("deliberations", deliberation_id, "推演", user_id)


def create_goal(name, goal_type, user_id):
    if goal_type not in GOAL_TYPES:
        raise ValueError("无效的目标类型")
    name = name.strip()
    if not name:
        raise ValueError("目标名称不能为空")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    cur = conn.execute(
        "INSERT INTO goals (user_id, name, type, created_at) VALUES (?, ?, ?, ?)",
        (owner_id, name, goal_type, _now()),
    )
    goal_id = cur.lastrowid
    if goal_type == "当前主线":
        _demote_other_mainline_goals(conn, goal_id, owner_id)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, owner_id)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def update_goal(goal_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, owner_id)
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("目标不存在")

    updates = {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            conn.close()
            raise ValueError("目标名称不能为空")
        updates["name"] = name
    if "type" in payload:
        goal_type = payload.get("type")
        if goal_type not in GOAL_TYPES:
            conn.close()
            raise ValueError("无效的目标类型")
        updates["type"] = goal_type

    if not updates:
        conn.close()
        raise ValueError("没有可更新的目标字段")

    assignments = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE goals SET {assignments} WHERE id = ? AND user_id = ?",
        (*updates.values(), goal_id, owner_id),
    )
    if updates.get("type") == "当前主线":
        _demote_other_mainline_goals(conn, goal_id, owner_id)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, owner_id)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_goals(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        "SELECT * FROM goals WHERE user_id = ? ORDER BY created_at DESC",
        (owner_id,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_goal(goal_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, owner_id)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def create_project(goal_id, name, priority=None, *, user_id):
    name = name.strip()
    if not name:
        raise ValueError("项目名称不能为空")
    priority = _normalize_priority(priority, strict=True)

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    goal = conn.execute(
        "SELECT id FROM goals WHERE id = ? AND user_id = ?", (goal_id, owner_id)
    ).fetchone()
    if not goal:
        conn.close()
        raise ValueError("目标不存在")

    cur = conn.execute(
        """
        INSERT INTO projects (user_id, goal_id, name, priority, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (owner_id, goal_id, name, priority, _now()),
    )
    conn.commit()
    project_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ? AND user_id = ?",
        (project_id, owner_id),
    ).fetchone()
    conn.close()
    return _project_row(row)


def get_project(project_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        """
        SELECT p.*, g.name AS goal_name, g.type AS goal_type
        FROM projects p
        JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
        WHERE p.id = ? AND p.user_id = ?
        """,
        (project_id, owner_id),
    ).fetchone()
    conn.close()
    return _project_row(row)


def update_project(project_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, owner_id),
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("项目不存在")

    updates = {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            conn.close()
            raise ValueError("项目名称不能为空")
        updates["name"] = name
    if "priority" in payload:
        updates["priority"] = _normalize_priority(payload.get("priority"), strict=True)
    for field in PROJECT_AUDIT_FIELDS:
        if field in VALUE_SCORE_FIELDS or field == "total_score":
            continue
        if field in payload:
            updates[field] = _clean_text(payload.get(field))
    if any(field in payload for field in VALUE_SCORE_FIELDS):
        existing_row = conn.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, owner_id),
        ).fetchone()
        scores = _value_scores_from_payload(payload, existing_row)
        updates.update(scores)

    if not updates:
        conn.close()
        raise ValueError("没有可更新的项目字段")

    assignments = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE projects SET {assignments} WHERE id = ? AND user_id = ?",
        (*updates.values(), project_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT p.*, g.name AS goal_name, g.type AS goal_type
        FROM projects p
        JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
        WHERE p.id = ? AND p.user_id = ?
        """,
        (project_id, owner_id),
    ).fetchone()
    conn.close()
    return _project_row(row)


def list_projects(user_id, goal_id=None):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    if goal_id is not None:
        rows = conn.execute(
            """
            SELECT p.*, g.name AS goal_name
            FROM projects p
            JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
            WHERE p.goal_id = ? AND p.user_id = ?
            ORDER BY p.created_at DESC
            """,
            (goal_id, owner_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT p.*, g.name AS goal_name
            FROM projects p
            JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
            WHERE p.user_id = ?
            ORDER BY p.created_at DESC
            """,
            (owner_id,),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def create_task(project_id, name, priority=None, *, user_id):
    name = name.strip()
    if not name:
        raise ValueError("任务名称不能为空")
    priority = _normalize_priority(priority, strict=True)

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    project = conn.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, owner_id),
    ).fetchone()
    if not project:
        conn.close()
        raise ValueError("项目不存在")

    cur = conn.execute(
        """
        INSERT INTO tasks (user_id, project_id, name, status, priority, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (owner_id, project_id, name, "待处理", priority, _now()),
    )
    conn.commit()
    task_id = cur.lastrowid
    row = conn.execute(
        """
        SELECT t.*, p.name AS project_name, g.name AS goal_name
        FROM tasks t
        JOIN projects p ON p.id = t.project_id AND p.user_id = t.user_id
        JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
        WHERE t.id = ? AND t.user_id = ?
        """,
        (task_id, owner_id),
    ).fetchone()
    conn.close()
    return _task_row(row)


def _fetch_task(conn, task_id, user_id):
    row = conn.execute(
        """
        SELECT t.*, p.name AS project_name, g.name AS goal_name
        FROM tasks t
        JOIN projects p ON p.id = t.project_id AND p.user_id = t.user_id
        JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
        WHERE t.id = ? AND t.user_id = ?
        """,
        (task_id, user_id),
    ).fetchone()
    return _task_row(row)


def list_tasks(user_id, project_id=None):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    if project_id is not None:
        rows = conn.execute(
            """
            SELECT t.*, p.name AS project_name, g.name AS goal_name
            FROM tasks t
            JOIN projects p ON p.id = t.project_id AND p.user_id = t.user_id
            JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
            WHERE t.project_id = ? AND t.user_id = ?
            ORDER BY t.created_at DESC
            """,
            (project_id, owner_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT t.*, p.name AS project_name, g.name AS goal_name
            FROM tasks t
            JOIN projects p ON p.id = t.project_id AND p.user_id = t.user_id
            JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
            WHERE t.user_id = ?
            ORDER BY t.created_at DESC
            """,
            (owner_id,),
        ).fetchall()
    conn.close()
    return [_task_row(r) for r in rows]


def update_task(task_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT id FROM tasks WHERE id = ? AND user_id = ?", (task_id, owner_id)
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("任务不存在")

    updates = {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            conn.close()
            raise ValueError("任务名称不能为空")
        updates["name"] = name
    if "status" in payload:
        status = payload.get("status")
        if status not in TASK_STATUSES:
            conn.close()
            raise ValueError("无效的任务状态")
        updates["status"] = status
    if "priority" in payload:
        updates["priority"] = _normalize_priority(payload.get("priority"), strict=True)

    if not updates:
        conn.close()
        raise ValueError("没有可更新的任务字段")

    assignments = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE tasks SET {assignments} WHERE id = ? AND user_id = ?",
        (*updates.values(), task_id, owner_id),
    )
    conn.commit()
    row = _fetch_task(conn, task_id, owner_id)
    conn.close()
    return row


def update_task_status(task_id, status, user_id):
    if status not in TASK_STATUSES:
        raise ValueError("无效的任务状态")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT id FROM tasks WHERE id = ? AND user_id = ?", (task_id, owner_id)
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("任务不存在")

    conn.execute(
        "UPDATE tasks SET status = ? WHERE id = ? AND user_id = ?",
        (status, task_id, owner_id),
    )
    conn.commit()
    row = _fetch_task(conn, task_id, owner_id)
    conn.close()
    return row


def update_task_today_progress(task_id, enabled, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT id FROM tasks WHERE id = ? AND user_id = ?", (task_id, owner_id)
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("任务不存在")

    if enabled:
        conn.execute(
            """
            UPDATE tasks
            SET today_progress = 1, today_progress_date = ?
            WHERE id = ? AND user_id = ?
            """,
            (_today_local(), task_id, owner_id),
        )
    else:
        conn.execute(
            """
            UPDATE tasks
            SET today_progress = 0, today_progress_date = NULL
            WHERE id = ? AND user_id = ?
            """,
            (task_id, owner_id),
        )
    conn.commit()
    row = _fetch_task(conn, task_id, owner_id)
    conn.close()
    return row


def get_mainline_goal(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        """
        SELECT * FROM goals
        WHERE user_id = ? AND type = '当前主线'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (owner_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_active_projects(user_id):
    today = _today_local()
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT
            p.*,
            g.name AS goal_name,
            MAX(
                CASE
                    WHEN t.today_progress = 1 AND t.today_progress_date = ? THEN 1
                    ELSE 0
                END
            ) AS has_today_progress,
            MAX(CASE WHEN t.status = '进行中' THEN 1 ELSE 0 END) AS has_doing_task,
            SUM(
                CASE
                    WHEN t.status IN ('待处理', '进行中') THEN 1
                    ELSE 0
                END
            ) AS active_task_count
        FROM projects p
        JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
        JOIN tasks t ON t.project_id = p.id AND t.user_id = p.user_id
        WHERE p.user_id = ?
        GROUP BY p.id
        HAVING active_task_count > 0
        ORDER BY
            has_today_progress DESC,
            has_doing_task DESC,
            active_task_count DESC,
            p.created_at DESC
        """,
        (today, owner_id),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def list_today_progress_tasks(user_id):
    today = _today_local()
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT t.*, p.name AS project_name, g.name AS goal_name
        FROM tasks t
        JOIN projects p ON p.id = t.project_id AND p.user_id = t.user_id
        JOIN goals g ON g.id = p.goal_id AND g.user_id = p.user_id
        WHERE t.user_id = ? AND t.today_progress = 1 AND t.today_progress_date = ?
        ORDER BY t.created_at DESC
        """,
        (owner_id, today),
    ).fetchall()
    conn.close()
    return [_project_row(r) for r in rows]


def _is_today_progress_record(record, today):
    return (
        int(record.get("today_progress") or 0) == 1
        and record.get("today_progress_date") == today
    )


def _task_inferred_priority(task, today):
    if _is_today_progress_record(task, today) or task.get("status") == "进行中":
        return "高", 3
    if task.get("status") == "待处理":
        return "中", 2
    return "低", 1


def _project_inferred_priority(stats):
    if stats["today"] > 0 or stats["doing"] > 0:
        return "高", 3
    if stats["pending"] > 0:
        return "中", 2
    return "低", 1


def _task_sort_key(task):
    status_rank = {"进行中": 3, "待处理": 2, "完成": 1}
    return (
        task.get("priority_score", 0),
        1 if task.get("is_today_progress") else 0,
        status_rank.get(task.get("status"), 0),
        task.get("recent_activity_at") or task.get("created_at") or "",
    )


def _project_sort_key(project):
    stats = project["stats"]
    return (
        project.get("priority_score", 0),
        stats["today"],
        stats["doing"],
        stats["open"],
        1 if stats["open"] > 0 else 0,
        project.get("recent_activity_at") or "",
    )


def _goal_sort_key(group, mainline_goal_id):
    return (
        1 if group["id"] == mainline_goal_id else 0,
        group["stats"]["today"],
        group["stats"]["doing"],
        group["stats"]["open"],
        group.get("created_at") or "",
    )


def _goal_inferred_status(stats):
    if stats["today"] > 0:
        return "今日推进中"
    if stats["doing"] > 0:
        return "推进中"
    if stats["pending"] > 0:
        return "待推进"
    if stats["total"] > 0:
        return "已完成"
    if stats["projects"] > 0:
        return "暂无任务"
    return "暂无项目"


def _project_inferred_status(stats):
    if stats["today"] > 0:
        return "今日推进中"
    if stats["doing"] > 0:
        return "推进中"
    if stats["pending"] > 0:
        return "待推进"
    if stats["total"] > 0:
        return "已完成"
    return "暂无任务"


def _dashboard_task(task, today):
    item = dict(task)
    is_today = _is_today_progress_record(item, today)
    priority = _normalize_priority(item.get("priority"))
    inferred_priority, inferred_score = _task_inferred_priority(item, today)
    item.update({
        "priority": priority,
        "priority_label": _priority_label(priority),
        "priority_score": _priority_score(priority),
        "is_today_progress": is_today,
        "display_priority": _priority_label(priority),
        "display_priority_score": _priority_score(priority),
        "priority_source": "用户设置",
        "inferred_priority": inferred_priority,
        "inferred_priority_score": inferred_score,
        "inferred_priority_source": "系统推导",
        "recent_activity_at": item.get("created_at") or "",
    })
    return item


def _dashboard_project(project, tasks):
    item = dict(project)
    stats = {
        "total": len(tasks),
        "pending": sum(1 for task in tasks if task.get("status") == "待处理"),
        "doing": sum(1 for task in tasks if task.get("status") == "进行中"),
        "done": sum(1 for task in tasks if task.get("status") == "完成"),
        "today": sum(1 for task in tasks if task.get("is_today_progress")),
    }
    stats["open"] = stats["pending"] + stats["doing"]
    recent_candidates = [item.get("created_at") or ""]
    recent_candidates.extend(task.get("created_at") or "" for task in tasks)
    recent_activity_at = max(recent_candidates) if recent_candidates else ""
    priority = _normalize_priority(item.get("priority"))
    inferred_priority, inferred_score = _project_inferred_priority(stats)

    item.update({
        "priority": priority,
        "priority_label": _priority_label(priority),
        "priority_score": _priority_score(priority),
        "status": _project_inferred_status(stats),
        "status_source": "系统推导",
        "display_priority": _priority_label(priority),
        "display_priority_score": _priority_score(priority),
        "priority_source": "用户设置",
        "inferred_priority": inferred_priority,
        "inferred_priority_score": inferred_score,
        "inferred_priority_source": "系统推导",
        "stats": stats,
        "task_total": stats["total"],
        "pending_task_count": stats["pending"],
        "doing_task_count": stats["doing"],
        "done_task_count": stats["done"],
        "today_task_count": stats["today"],
        "open_task_count": stats["open"],
        "recent_activity_at": recent_activity_at,
        "is_focus_project": False,
    })
    return item


def _build_dashboard_context(user_id):
    today = _today_local()
    goals = list_goals(user_id)
    projects = list_projects(user_id)
    tasks = [_dashboard_task(task, today) for task in list_tasks(user_id)]
    mainline_goal = get_mainline_goal(user_id)
    mainline_goal_id = mainline_goal["id"] if mainline_goal else None

    tasks_by_project = {}
    for task in tasks:
        tasks_by_project.setdefault(task.get("project_id"), []).append(task)
    for project_tasks in tasks_by_project.values():
        project_tasks.sort(key=_task_sort_key, reverse=True)

    project_views = [
        _dashboard_project(project, tasks_by_project.get(project["id"], []))
        for project in projects
    ]
    project_views.sort(key=_project_sort_key, reverse=True)

    focus_project = next(
        (project for project in project_views if project["stats"]["open"] > 0),
        project_views[0] if project_views else None,
    )
    if focus_project:
        focus_project["is_focus_project"] = True

    projects_by_goal = {}
    for project in project_views:
        projects_by_goal.setdefault(project.get("goal_id"), []).append(project)

    goal_groups = []
    summary = {
        "goal_count": len(goals),
        "project_count": len(projects),
        "task_count": len(tasks),
        "open_task_count": 0,
        "today_task_count": 0,
        "mainline_goal_id": mainline_goal_id,
        "focus_project_id": focus_project["id"] if focus_project else None,
    }

    for goal in goals:
        goal_projects = projects_by_goal.get(goal["id"], [])
        stats = {
            "projects": len(goal_projects),
            "total": sum(project["stats"]["total"] for project in goal_projects),
            "pending": sum(project["stats"]["pending"] for project in goal_projects),
            "doing": sum(project["stats"]["doing"] for project in goal_projects),
            "done": sum(project["stats"]["done"] for project in goal_projects),
            "today": sum(project["stats"]["today"] for project in goal_projects),
            "open": sum(project["stats"]["open"] for project in goal_projects),
        }
        summary["open_task_count"] += stats["open"]
        summary["today_task_count"] += stats["today"]
        group = dict(goal)
        group.update({
            "status": _goal_inferred_status(stats),
            "status_source": "系统推导",
            "stats": stats,
            "project_count": stats["projects"],
            "task_total": stats["total"],
            "open_task_count": stats["open"],
            "today_task_count": stats["today"],
            "projects": goal_projects,
        })
        goal_groups.append(group)

    goal_groups.sort(key=lambda group: _goal_sort_key(group, mainline_goal_id), reverse=True)

    enriched_mainline = None
    if mainline_goal:
        enriched_mainline = next(
            (group for group in goal_groups if group["id"] == mainline_goal_id),
            dict(mainline_goal),
        )

    today_tasks = [task for task in tasks if task.get("is_today_progress")]
    today_tasks.sort(key=_task_sort_key, reverse=True)

    return {
        "mainline_goal": enriched_mainline,
        "week_projects": [
            project for project in project_views if project["stats"]["open"] > 0
        ],
        "today_tasks": today_tasks,
        "goal_groups": goal_groups,
        "project_focus": focus_project,
        "today_task_context": today_tasks,
        "dashboard_summary": summary,
    }


def get_dashboard(user_id):
    return _build_dashboard_context(user_id)


def _parse_tags(raw):
    try:
        tags = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(tags, list):
        return []
    return [t for t in tags if t in CAPABILITY_MODULES]


def _asset_row(row):
    data = _row_to_dict(row)
    if not data:
        return data
    data["capability_tags"] = _parse_tags(data.get("capability_tags"))
    title = data.get("title") or ""
    core = data.get("core_content") or ""
    data["asset_type"] = asset_schemas.normalize_asset_type(
        data.get("asset_type"), title, core
    )
    fields = asset_schemas.parse_fields(data.get("fields"))
    if not fields:
        fields = asset_schemas.build_fields_from_legacy(
            data["asset_type"],
            data.get("trigger_context") or "",
            core,
        )
    data["fields"] = fields
    if not (data.get("summary") or "").strip():
        data["summary"] = asset_schemas.extract_summary(fields, core)
    if not (data.get("reusable_scenario") or "").strip():
        data["reusable_scenario"] = asset_schemas.extract_reusable_scenario(
            data["asset_type"], fields
        )
    if data.get("maturity") not in MATURITY_LEVELS:
        data["maturity"] = "草稿"
    data["reuse_count"] = int(data.get("reuse_count") or 0)
    if data.get("source_id") is None:
        data["source_id"] = data.get("source_review_id")
    if not data.get("source_type"):
        data["source_type"] = "review" if data.get("source_review_id") else ""
    if not (data.get("updated_at") or "").strip():
        data["updated_at"] = data.get("created_at")
    if data.get("asset_level") not in ASSET_LEVELS:
        data["asset_level"] = "资料"
    for field in ASSET_VALUE_FIELDS:
        if field != "asset_level":
            data[field] = data.get(field) or ""
    trigger, core_content = asset_schemas.sync_legacy_columns(data["asset_type"], fields)
    if trigger:
        data["trigger_context"] = trigger
    if core_content:
        data["core_content"] = core_content
    return data


def create_review(
    review_date,
    review_type,
    what_done,
    stuck,
    next_adjust,
    depositable,
    user_id,
):
    if review_type not in REVIEW_TYPES:
        raise ValueError("无效的复盘类型")
    review_date = (review_date or "").strip()
    if not review_date:
        raise ValueError("复盘日期不能为空")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    cur = conn.execute(
        """
        INSERT INTO reviews (
            user_id, review_date, type, what_done, stuck, next_adjust,
            depositable, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_id,
            review_date,
            review_type,
            (what_done or "").strip(),
            (stuck or "").strip(),
            (next_adjust or "").strip(),
            (depositable or "").strip(),
            _now(),
        ),
    )
    conn.commit()
    review_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM reviews WHERE id = ? AND user_id = ?",
        (review_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_reviews(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM reviews
        WHERE user_id = ?
        ORDER BY review_date DESC, created_at DESC
        """,
        (owner_id,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_review(review_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM reviews WHERE id = ? AND user_id = ?",
        (review_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def create_asset(
    title,
    asset_type,
    capability_tags=None,
    fields=None,
    summary="",
    reusable_scenario="",
    maturity="草稿",
    source_review_id=None,
    trigger_context=None,
    core_content=None,
    asset_level="资料",
    evidence="",
    external_expression="",
    transferable_scene="",
    productization_next_step="",
    source_type="",
    source_id=None,
    *,
    user_id,
):
    title = (title or "").strip()
    if not title:
        raise ValueError("标题不能为空")
    asset_type = asset_schemas.normalize_asset_type(
        asset_type, title, core_content or ""
    )
    if asset_type not in ASSET_TYPES:
        raise ValueError("无效的资产类型")
    if maturity not in MATURITY_LEVELS:
        maturity = "草稿"
    if asset_level not in ASSET_LEVELS:
        asset_level = "资料"

    parsed_fields = asset_schemas.parse_fields(fields)
    if not parsed_fields:
        parsed_fields = asset_schemas.build_fields_from_legacy(
            asset_type,
            trigger_context or "",
            core_content or "",
        )
    if not asset_schemas.asset_content_valid(
        asset_type, parsed_fields, core_content or ""
    ):
        raise ValueError("请填写资产内容字段")

    legacy_trigger, legacy_core = asset_schemas.sync_legacy_columns(
        asset_type, parsed_fields
    )
    if not legacy_trigger and trigger_context:
        legacy_trigger = (trigger_context or "").strip()
    if not legacy_core and core_content:
        legacy_core = (core_content or "").strip()

    summary = (summary or "").strip() or asset_schemas.extract_summary(
        parsed_fields, legacy_core
    )
    reusable_scenario = (reusable_scenario or "").strip() or asset_schemas.extract_reusable_scenario(
        asset_type, parsed_fields
    )

    tags = _parse_tags(json.dumps(capability_tags or []))
    source_type = (source_type or "").strip()
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    if source_review_id is not None:
        review = conn.execute(
            "SELECT id FROM reviews WHERE id = ? AND user_id = ?",
            (source_review_id, owner_id),
        ).fetchone()
        if not review:
            conn.close()
            raise ValueError("来源复盘不存在")
        source_type = "review"
        source_id = source_review_id
    elif source_id not in (None, ""):
        source_tables = {
            "review": "reviews",
            "feedback": "feedback_items",
            "experiment": "experiments",
            "opportunity": "opportunities",
        }
        if source_type not in source_tables:
            conn.close()
            raise ValueError("无效的资产来源类型")
        try:
            source_id = int(source_id)
        except (TypeError, ValueError):
            conn.close()
            raise ValueError("资产来源 id 无效")
        if not conn.execute(
            f"SELECT id FROM {source_tables[source_type]} WHERE id = ? AND user_id = ?",
            (source_id, owner_id),
        ).fetchone():
            conn.close()
            raise ValueError("资产来源对象不存在")
        if source_type == "review":
            source_review_id = source_id
    elif source_type:
        conn.close()
        raise ValueError("资产来源缺少 source_id")

    now = _now()
    cur = conn.execute(
        """
        INSERT INTO assets (
            user_id, title, trigger_context, core_content, asset_type,
            capability_tags, source_review_id, created_at,
            summary, fields, reusable_scenario, maturity, reuse_count,
            source_type, source_id, updated_at, asset_level, evidence,
            external_expression, transferable_scene, productization_next_step
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_id,
            title,
            legacy_trigger,
            legacy_core,
            asset_type,
            json.dumps(tags, ensure_ascii=False),
            source_review_id,
            now,
            summary,
            asset_schemas.serialize_fields(parsed_fields),
            reusable_scenario,
            maturity,
            0,
            source_type,
            source_id,
            now,
            asset_level,
            (evidence or "").strip(),
            (external_expression or "").strip(),
            (transferable_scene or "").strip(),
            (productization_next_step or "").strip(),
        ),
    )
    conn.commit()
    asset_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM assets WHERE id = ? AND user_id = ?", (asset_id, owner_id)
    ).fetchone()
    conn.close()
    return _asset_row(row)


def create_asset_from_feedback(feedback_id, user_id):
    feedback = get_feedback_item(feedback_id, user_id)
    if not feedback:
        raise ValueError("反馈不存在")

    content = _clean_text(feedback.get("content"))
    title = _clean_text(feedback.get("title"))
    evidence = _clean_text(feedback.get("evidence"))
    next_action = _clean_text(feedback.get("next_action"))
    base_content = content or title
    external_text = (
        f"基于一次真实反馈，我识别到：{base_content}。"
        "该反馈说明该方向具备进一步验证和案例沉淀价值。"
    )
    productization_next_step = (
        next_action or "继续补充结果数据、适用场景和可复用方法。"
    )
    fields = {
        "资产说明": base_content,
        "适用场景": _clean_text(feedback.get("source")),
        "核心内容": base_content,
        "使用方法": productization_next_step,
        "可复用价值": evidence or _clean_text(feedback.get("level")),
    }

    return create_asset(
        f"{title}案例资产",
        "案例复盘",
        capability_tags=[],
        fields=fields,
        summary=content,
        reusable_scenario="",
        maturity="可用",
        core_content=base_content,
        asset_level="案例",
        evidence=evidence,
        external_expression=external_text,
        transferable_scene="",
        productization_next_step=productization_next_step,
        source_type="feedback",
        source_id=feedback["id"],
        user_id=user_id,
    )


def get_asset(asset_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM assets WHERE id = ? AND user_id = ?", (asset_id, owner_id)
    ).fetchone()
    conn.close()
    return _asset_row(row)


def list_assets(user_id, tag=None, asset_type=None):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM assets
        WHERE user_id = ?
        ORDER BY updated_at DESC, created_at DESC
        """,
        (owner_id,),
    ).fetchall()
    conn.close()
    assets = [_asset_row(r) for r in rows]
    if asset_type:
        normalized = asset_schemas.normalize_asset_type(asset_type)
        if normalized not in ASSET_TYPES:
            raise ValueError("无效的资产类型")
        assets = [a for a in assets if a["asset_type"] == normalized]
    if tag:
        if tag not in CAPABILITY_MODULES:
            raise ValueError("无效的能力标签")
        assets = [a for a in assets if tag in a["capability_tags"]]
    return assets


def update_asset(asset_id, *, user_id, **kwargs):
    allowed_fields = {
        "title",
        "asset_type",
        "capability_tags",
        "maturity",
        "summary",
        "reusable_scenario",
        "fields",
        "trigger_context",
        "core_content",
        "asset_level",
        "evidence",
        "external_expression",
        "transferable_scene",
        "productization_next_step",
    }
    kwargs = {key: value for key, value in kwargs.items() if key in allowed_fields}
    if not kwargs:
        raise ValueError("没有可更新的资产字段")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM assets WHERE id = ? AND user_id = ?", (asset_id, owner_id)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("资产不存在")
    current = _asset_row(row)

    title = kwargs.get("title", current["title"])
    title = (title or "").strip()
    if not title:
        conn.close()
        raise ValueError("标题不能为空")

    asset_type = kwargs.get("asset_type", current["asset_type"])
    asset_type = asset_schemas.normalize_asset_type(
        asset_type, title, kwargs.get("core_content", current.get("core_content", ""))
    )
    if asset_type not in ASSET_TYPES:
        conn.close()
        raise ValueError("无效的资产类型")

    parsed_fields = asset_schemas.parse_fields(
        kwargs.get("fields", current.get("fields"))
    )
    if kwargs.get("trigger_context") is not None or kwargs.get("core_content") is not None:
        legacy_fields = asset_schemas.build_fields_from_legacy(
            asset_type,
            kwargs.get("trigger_context", current.get("trigger_context", "")),
            kwargs.get("core_content", current.get("core_content", "")),
        )
        for key, value in legacy_fields.items():
            if value and not (parsed_fields.get(key) or "").strip():
                parsed_fields[key] = value

    if not asset_schemas.asset_content_valid(
        asset_type,
        parsed_fields,
        kwargs.get("core_content", current.get("core_content", "")),
    ):
        conn.close()
        raise ValueError("请填写资产内容字段")

    legacy_trigger, legacy_core = asset_schemas.sync_legacy_columns(
        asset_type, parsed_fields
    )
    summary = kwargs.get("summary", current.get("summary", ""))
    summary = (summary or "").strip() or asset_schemas.extract_summary(
        parsed_fields, legacy_core
    )
    reusable_scenario = kwargs.get(
        "reusable_scenario", current.get("reusable_scenario", "")
    )
    reusable_scenario = (reusable_scenario or "").strip() or asset_schemas.extract_reusable_scenario(
        asset_type, parsed_fields
    )
    maturity = kwargs.get("maturity", current.get("maturity", "草稿"))
    if maturity not in MATURITY_LEVELS:
        maturity = current.get("maturity", "草稿")
    asset_level = kwargs.get("asset_level", current.get("asset_level", "资料"))
    if asset_level not in ASSET_LEVELS:
        asset_level = current.get("asset_level", "资料")

    capability_tags = kwargs.get("capability_tags", current.get("capability_tags"))
    tags = _parse_tags(json.dumps(capability_tags or []))

    updates = {
        "title": title,
        "asset_type": asset_type,
        "trigger_context": legacy_trigger,
        "core_content": legacy_core,
        "summary": summary,
        "fields": asset_schemas.serialize_fields(parsed_fields),
        "reusable_scenario": reusable_scenario,
        "maturity": maturity,
        "capability_tags": json.dumps(tags, ensure_ascii=False),
        "updated_at": _now(),
        "asset_level": asset_level,
        "evidence": _clean_text(kwargs.get("evidence", current.get("evidence", ""))),
        "external_expression": _clean_text(kwargs.get("external_expression", current.get("external_expression", ""))),
        "transferable_scene": _clean_text(kwargs.get("transferable_scene", current.get("transferable_scene", ""))),
        "productization_next_step": _clean_text(kwargs.get("productization_next_step", current.get("productization_next_step", ""))),
    }

    set_clause = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE assets SET {set_clause} WHERE id = ? AND user_id = ?",
        (*updates.values(), asset_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM assets WHERE id = ? AND user_id = ?", (asset_id, owner_id)
    ).fetchone()
    conn.close()
    return _asset_row(row)


def increment_asset_reuse(asset_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT id FROM assets WHERE id = ? AND user_id = ?", (asset_id, owner_id)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("资产不存在")
    conn.execute(
        """
        UPDATE assets
        SET reuse_count = reuse_count + 1, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (_now(), asset_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM assets WHERE id = ? AND user_id = ?", (asset_id, owner_id)
    ).fetchone()
    conn.close()
    return _asset_row(row)


def create_capability_entry(
    module, entry_date, content, source_project, level_type, user_id
):
    if module not in CAPABILITY_MODULES:
        raise ValueError("无效的能力模块")
    if level_type not in LEVEL_TYPES:
        raise ValueError("无效的层级判断")
    entry_date = (entry_date or "").strip()
    content = (content or "").strip()
    if not entry_date:
        raise ValueError("日期不能为空")
    if not content:
        raise ValueError("内容不能为空")

    source_project = (source_project or "").strip() or None

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    cur = conn.execute(
        """
        INSERT INTO capability_entries (
            user_id, module, entry_date, content, source_project, level_type,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (owner_id, module, entry_date, content, source_project, level_type, _now()),
    )
    conn.commit()
    entry_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM capability_entries WHERE id = ? AND user_id = ?",
        (entry_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_capability_entries(user_id, module=None):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    if module is not None:
        if module not in CAPABILITY_MODULES:
            conn.close()
            raise ValueError("无效的能力模块")
        rows = conn.execute(
            """
            SELECT * FROM capability_entries
            WHERE user_id = ? AND module = ?
            ORDER BY entry_date DESC, created_at DESC
            """,
            (owner_id, module),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM capability_entries
            WHERE user_id = ?
            ORDER BY entry_date DESC, created_at DESC
            """,
            (owner_id,),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _practice_step_row(row):
    data = _row_to_dict(row)
    if not data:
        return data
    data["step_order"] = int(data.get("step_order") or 0)
    return data


def _normalize_practice_step_order(conn, module, user_id):
    rows = conn.execute(
        """
        SELECT id, step_order FROM capability_practice_steps
        WHERE user_id = ? AND module = ?
        ORDER BY step_order ASC, id ASC
        """,
        (user_id, module),
    ).fetchall()
    now = _now()
    for index, row in enumerate(rows, start=1):
        if row["step_order"] == index:
            continue
        conn.execute(
            """
            UPDATE capability_practice_steps
            SET step_order = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (index, now, row["id"], user_id),
        )


def list_capability_practice_paths(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM capability_practice_steps
        WHERE user_id = ?
        ORDER BY module ASC, step_order ASC, id ASC
        """,
        (owner_id,),
    ).fetchall()
    conn.close()
    paths = {module: [] for module in CAPABILITY_MODULES}
    for row in rows:
        step = _practice_step_row(row)
        if step["module"] in paths:
            paths[step["module"]].append(step)
    return paths


def get_capability_practice_path(module, user_id):
    if module not in CAPABILITY_MODULES:
        raise ValueError("无效的能力模块")
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM capability_practice_steps
        WHERE user_id = ? AND module = ?
        ORDER BY step_order ASC, id ASC
        """,
        (owner_id, module),
    ).fetchall()
    conn.close()
    return [_practice_step_row(row) for row in rows]


def create_capability_practice_step(
    module, title, description="", detail="", step_order=None, *, user_id
):
    if module not in CAPABILITY_MODULES:
        raise ValueError("无效的能力模块")
    title = (title or "").strip()
    if not title:
        raise ValueError("步骤名称不能为空")
    description = (description or "").strip()
    detail = (detail or "").strip()

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    if step_order is None:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(step_order), 0) + 1 AS next_order
            FROM capability_practice_steps
            WHERE user_id = ? AND module = ?
            """,
            (owner_id, module),
        ).fetchone()
        step_order = int(row["next_order"])
    else:
        try:
            step_order = max(1, int(step_order))
        except (TypeError, ValueError):
            conn.close()
            raise ValueError("步骤排序必须是正整数")
        conn.execute(
            """
            UPDATE capability_practice_steps
            SET step_order = step_order + 1
            WHERE user_id = ? AND module = ? AND step_order >= ?
            """,
            (owner_id, module, step_order),
        )

    now = _now()
    cur = conn.execute(
        """
        INSERT INTO capability_practice_steps (
            user_id, module, step_order, title, description, detail,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (owner_id, module, step_order, title, description, detail, now, now),
    )
    _normalize_practice_step_order(conn, module, owner_id)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ? AND user_id = ?",
        (cur.lastrowid, owner_id),
    ).fetchone()
    conn.close()
    return _practice_step_row(row)


def update_capability_practice_step(step_id, *, user_id, **kwargs):
    allowed = {"title", "description", "detail", "step_order"}
    updates = {key: value for key, value in kwargs.items() if key in allowed}
    if not updates:
        raise ValueError("没有可更新的训练步骤字段")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ? AND user_id = ?",
        (step_id, owner_id),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("训练步骤不存在")
    current = _practice_step_row(row)

    title = updates.get("title", current["title"])
    title = (title or "").strip()
    if not title:
        conn.close()
        raise ValueError("步骤名称不能为空")

    description = updates.get("description", current["description"])
    detail = updates.get("detail", current["detail"])
    step_order = updates.get("step_order", current["step_order"])
    try:
        step_order = max(1, int(step_order))
    except (TypeError, ValueError):
        conn.close()
        raise ValueError("步骤排序必须是正整数")
    current_order = current["step_order"]
    if step_order < current_order:
        conn.execute(
            """
            UPDATE capability_practice_steps
            SET step_order = step_order + 1
            WHERE user_id = ? AND module = ? AND id != ?
              AND step_order >= ? AND step_order < ?
            """,
            (owner_id, current["module"], step_id, step_order, current_order),
        )
    elif step_order > current_order:
        conn.execute(
            """
            UPDATE capability_practice_steps
            SET step_order = step_order - 1
            WHERE user_id = ? AND module = ? AND id != ?
              AND step_order <= ? AND step_order > ?
            """,
            (owner_id, current["module"], step_id, step_order, current_order),
        )

    conn.execute(
        """
        UPDATE capability_practice_steps
        SET title = ?, description = ?, detail = ?, step_order = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            title,
            (description or "").strip(),
            (detail or "").strip(),
            step_order,
            _now(),
            step_id,
            owner_id,
        ),
    )
    _normalize_practice_step_order(conn, current["module"], owner_id)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ? AND user_id = ?",
        (step_id, owner_id),
    ).fetchone()
    conn.close()
    return _practice_step_row(row)


def delete_capability_practice_step(step_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ? AND user_id = ?",
        (step_id, owner_id),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("训练步骤不存在")
    module = row["module"]
    conn.execute(
        "DELETE FROM capability_practice_steps WHERE id = ? AND user_id = ?",
        (step_id, owner_id),
    )
    _normalize_practice_step_order(conn, module, owner_id)
    conn.commit()
    conn.close()
    return {"id": step_id, "deleted": True, "module": module}


def _display_maturity(maturity):
    if maturity in MATURE_MATURITY_LEVELS:
        return "成熟"
    if maturity == "可用":
        return "可用"
    return "草稿"


def _asset_summary_item(asset):
    return {
        "id": asset.get("id"),
        "title": asset.get("title", ""),
        "asset_type": asset.get("asset_type", ""),
        "maturity": asset.get("maturity", "草稿"),
        "maturity_label": _display_maturity(asset.get("maturity")),
        "reuse_count": int(asset.get("reuse_count") or 0),
        "updated_at": asset.get("updated_at") or asset.get("created_at") or "",
        "created_at": asset.get("created_at") or "",
        "summary": asset.get("summary", ""),
        "reusable_scenario": asset.get("reusable_scenario", ""),
    }


def _capability_status(asset_count, usable_asset_count, reuse_total):
    if usable_asset_count >= 2 and reuse_total > 0:
        return "有优势"
    if asset_count <= 1:
        return "薄弱"
    return "积累中"


def _capability_status_reason(asset_count, usable_asset_count, reuse_total):
    if asset_count <= 1:
        return "关联资产很少"
    if usable_asset_count >= 2 and reuse_total > 0:
        return "已有可用资产和复用记录"
    if usable_asset_count == 0:
        return "已有资产但成熟度不足"
    return "已有资产沉淀，复用仍需验证"


def _capability_next_action(module, asset_count, usable_asset_count, reuse_total, entry_count):
    recommended_type = RECOMMENDED_CAPABILITY_ASSET_TYPES.get(module, "通用资产")
    if asset_count == 0:
        return f"先沉淀 1 个{recommended_type}，把最近一次训练转成可复用资产。"
    if entry_count >= 2 and asset_count <= 1:
        return f"把高频训练记录整理成{recommended_type}，补齐能力资产底座。"
    if asset_count >= 3 and reuse_total == 0:
        return "选择 1-2 个可用资产进入真实项目复用，记录复用次数和调整点。"
    if usable_asset_count == 0:
        return "优先补齐资产的使用场景、判断标准和适用边界，推进到可用。"
    if usable_asset_count >= 2 and reuse_total > 0:
        return f"把高复用资产标准化为{recommended_type}或模板，形成稳定调用流程。"
    return f"围绕当前资产补一次应用层训练，并沉淀 1 个{recommended_type}。"


def _module_priority(module_summary):
    entry_count = module_summary["entry_count"]
    asset_count = module_summary["asset_count"]
    usable_count = module_summary["usable_asset_count"]
    reuse_total = module_summary["reuse_total"]
    status = module_summary["status"]
    if entry_count >= 2 and asset_count <= 1:
        return (0, -entry_count, asset_count)
    if asset_count >= 3 and reuse_total == 0:
        return (1, -asset_count, -usable_count)
    if status == "薄弱":
        return (2, asset_count, -entry_count)
    if usable_count == 0 and asset_count > 0:
        return (3, -asset_count, -entry_count)
    return (4, -asset_count, -reuse_total)


def get_capability_summary(user_id):
    assets = list_assets(user_id)
    entries = list_capability_entries(user_id)
    practice_paths = list_capability_practice_paths(user_id)
    entries_by_module = {module: [] for module in CAPABILITY_MODULES}
    for entry in entries:
        module = entry.get("module")
        if module in entries_by_module:
            entries_by_module[module].append(entry)

    modules = []
    assigned_asset_total = 0
    for module in CAPABILITY_MODULES:
        module_assets = [
            asset
            for asset in assets
            if module in (asset.get("capability_tags") or [])
        ]
        assigned_asset_total += len(module_assets)
        asset_count = len(module_assets)
        usable_asset_count = sum(
            1 for asset in module_assets if asset.get("maturity") in USABLE_MATURITY_LEVELS
        )
        mature_asset_count = sum(
            1 for asset in module_assets if asset.get("maturity") in MATURE_MATURITY_LEVELS
        )
        reuse_total = sum(int(asset.get("reuse_count") or 0) for asset in module_assets)
        recent_asset_updated_at = (
            (module_assets[0].get("updated_at") or module_assets[0].get("created_at") or "")
            if module_assets
            else ""
        )

        type_counts = Counter(asset.get("asset_type") or "通用资产" for asset in module_assets)
        maturity_counts = Counter(
            _display_maturity(asset.get("maturity")) for asset in module_assets
        )
        module_entries = entries_by_module[module]
        level_counts = Counter(entry.get("level_type") or "" for entry in module_entries)
        status = _capability_status(asset_count, usable_asset_count, reuse_total)
        recommended_type = RECOMMENDED_CAPABILITY_ASSET_TYPES.get(module, "通用资产")
        high_reuse_assets = sorted(
            [asset for asset in module_assets if int(asset.get("reuse_count") or 0) > 0],
            key=lambda asset: (
                -int(asset.get("reuse_count") or 0),
                asset.get("updated_at") or asset.get("created_at") or "",
            ),
        )

        modules.append(
            {
                "module": module,
                "layer": CAPABILITY_LAYERS[module],
                "asset_count": asset_count,
                "usable_asset_count": usable_asset_count,
                "mature_asset_count": mature_asset_count,
                "reuse_total": reuse_total,
                "recent_asset_updated_at": recent_asset_updated_at,
                "status": status,
                "status_reason": _capability_status_reason(
                    asset_count, usable_asset_count, reuse_total
                ),
                "recommended_asset_type": recommended_type,
                "next_action": _capability_next_action(
                    module, asset_count, usable_asset_count, reuse_total, len(module_entries)
                ),
                "asset_type_distribution": [
                    {"name": name, "count": count}
                    for name, count in type_counts.most_common()
                ],
                "maturity_distribution": [
                    {"name": name, "count": maturity_counts.get(name, 0)}
                    for name in DISPLAY_MATURITY_BUCKETS
                ],
                "recent_assets": [
                    _asset_summary_item(asset) for asset in module_assets[:3]
                ],
                "high_reuse_assets": [
                    _asset_summary_item(asset) for asset in high_reuse_assets[:3]
                ],
                "recent_entries": module_entries[:3],
                "entry_count": len(module_entries),
                "entry_level_counts": {
                    "能力层": level_counts.get("能力层", 0),
                    "应用层": level_counts.get("应用层", 0),
                    "total": len(module_entries),
                },
                "practice_steps": [
                    {
                        "id": step["id"],
                        "step_order": step["step_order"],
                        "title": step["title"],
                        "description": step["description"],
                    }
                    for step in practice_paths.get(module, [])
                ],
            }
        )

    record_asset_gaps = [
        item
        for item in modules
        if item["entry_count"] >= 2 and item["asset_count"] <= 1
    ]
    low_reuse_modules = [
        item
        for item in modules
        if item["asset_count"] >= 3 and item["reuse_total"] == 0
    ]
    next_focus_modules = sorted(modules, key=_module_priority)[:3]

    return {
        "overview": {
            "total_assets": len(assets),
            "tagged_assets": sum(1 for asset in assets if asset.get("capability_tags")),
            "assigned_asset_total": assigned_asset_total,
            "total_entries": len(entries),
            "advantage_modules": [
                item["module"] for item in modules if item["status"] == "有优势"
            ],
            "weak_modules": [
                item["module"] for item in modules if item["status"] == "薄弱"
            ],
            "record_asset_gaps": [
                {
                    "module": item["module"],
                    "entry_count": item["entry_count"],
                    "asset_count": item["asset_count"],
                }
                for item in record_asset_gaps
            ],
            "low_reuse_modules": [
                {
                    "module": item["module"],
                    "asset_count": item["asset_count"],
                    "usable_asset_count": item["usable_asset_count"],
                    "reuse_total": item["reuse_total"],
                }
                for item in low_reuse_modules
            ],
            "next_focus_modules": [
                {
                    "module": item["module"],
                    "status": item["status"],
                    "next_action": item["next_action"],
                    "recommended_asset_type": item["recommended_asset_type"],
                }
                for item in next_focus_modules
            ],
        },
        "modules": modules,
        "maturity_display": {
            "raw_levels": list(MATURITY_LEVELS),
            "display_buckets": list(DISPLAY_MATURITY_BUCKETS),
            "usable_levels": list(USABLE_MATURITY_LEVELS),
            "mature_levels": list(MATURE_MATURITY_LEVELS),
        },
    }


class DeleteError(Exception):
    pass


class DataImportError(Exception):
    def __init__(self, message, stats=None):
        super().__init__(message)
        self.stats = stats


class ExportError(Exception):
    pass


SUPPORTED_IMPORT_VERSIONS = ("1.0", "2.0")
IMPORT_TABLES = (
    "goals",
    "projects",
    "tasks",
    "reviews",
    "capability_entries",
    "capability_practice_steps",
    "opportunities",
    "experiments",
    "assets",
    "feedback_items",
    "deliberations",
    "positioning_anchor",
    "positioning_calibration",
    "positioning_goal_action",
    "inbox_entries",
    "inbox_suggestions",
)
REQUIRED_IMPORT_TABLES = (
    "goals",
    "projects",
    "tasks",
    "reviews",
    "assets",
    "capability_entries",
    "opportunities",
    "experiments",
    "feedback_items",
)
LEGACY_IMPORT_TABLES = (
    "goals",
    "projects",
    "tasks",
    "reviews",
    "assets",
    "capability_entries",
)

_TABLE_FIELDS = {
    "goals": ("id", "name", "type", "created_at", "status"),
    "projects": (
        "id",
        "goal_id",
        "name",
        "priority",
        "created_at",
        *PROJECT_AUDIT_FIELDS,
    ),
    "tasks": (
        "id",
        "project_id",
        "name",
        "status",
        "priority",
        "created_at",
        "today_progress",
        "today_progress_date",
    ),
    "reviews": (
        "id",
        "review_date",
        "type",
        "what_done",
        "stuck",
        "next_adjust",
        "depositable",
        "created_at",
    ),
    "assets": (
        "id",
        "title",
        "trigger_context",
        "core_content",
        "asset_type",
        "capability_tags",
        "source_review_id",
        "created_at",
        "summary",
        "fields",
        "reusable_scenario",
        "maturity",
        "reuse_count",
        "source_type",
        "source_id",
        "updated_at",
        *ASSET_VALUE_FIELDS,
    ),
    "capability_entries": (
        "id",
        "module",
        "entry_date",
        "content",
        "source_project",
        "level_type",
        "created_at",
    ),
    "capability_practice_steps": (
        "id",
        "module",
        "step_order",
        "title",
        "description",
        "detail",
        "created_at",
        "updated_at",
    ),
    "opportunities": (
        "id",
        "name",
        *OPPORTUNITY_TEXT_FIELDS,
        *VALUE_SCORE_FIELDS,
        "total_score",
        "status",
        "created_at",
        "updated_at",
    ),
    "experiments": (
        "id",
        "opportunity_id",
        "name",
        "hypothesis",
        "experiment_type",
        "minimum_action",
        "test_target",
        "feedback_source",
        "validation_period",
        "success_criteria",
        "failure_criteria",
        "progress",
        "real_feedback",
        "data_result",
        "next_decision",
        "review_conclusion",
        "status",
        "created_at",
        "updated_at",
    ),
    "feedback_items": (
        "id",
        "related_type",
        "related_id",
        "title",
        "source",
        "level",
        "content",
        "evidence",
        "next_action",
        "created_at",
        "updated_at",
    ),
    "deliberations": (
        "id",
        *DELIBERATION_INITIAL_FIELDS,
        "ai_analysis",
        *DELIBERATION_DECISION_FIELDS,
        *DELIBERATION_REVIEW_FIELDS,
        "status",
        "created_at",
        "updated_at",
    ),
    "positioning_anchor": (
        "id",
        "first_principle",
        "identity_core",
        "flywheel_def",
        "current_stage",
        "north_star",
        "updated_at",
    ),
    "positioning_calibration": (
        "id",
        "calibrated_at",
        "cycle",
        "primary_contradiction",
        "doing_but_shouldnt",
        "should_but_not_doing",
        "alignment_review",
        "conclusion",
        "created_at",
    ),
    "positioning_goal_action": (
        "id",
        "calibration_id",
        "action_type",
        "target_goal_id",
        "payload",
        "reason",
        "status",
        "created_at",
    ),
    "inbox_entries": (
        "id",
        "raw_text",
        "source_type",
        "status",
        "created_at",
    ),
    "inbox_suggestions": (
        "id",
        "inbox_entry_id",
        "target_type",
        "title",
        "content",
        "confidence",
        "reason",
        "suggested_payload",
        "status",
        "created_at",
    ),
}


def _clear_soft_references(conn, table, entity_id, user_id):
    """Clear same-owner polymorphic references before deleting their target."""
    cleared = {}
    related_type = {
        "opportunities": "opportunity",
        "experiments": "experiment",
        "projects": "project",
        "assets": "asset",
        "reviews": "review",
    }.get(table)
    if related_type:
        cursor = conn.execute(
            """
            UPDATE feedback_items
            SET related_type = '', related_id = NULL, updated_at = ?
            WHERE user_id = ? AND related_type = ? AND related_id = ?
            """,
            (_now(), user_id, related_type, entity_id),
        )
        cleared["feedback_items"] = cursor.rowcount

    if table in ("projects", "opportunities"):
        deliberation_type = "project" if table == "projects" else "opportunity"
        cursor = conn.execute(
            """
            UPDATE deliberations
            SET related_type = '', related_id = NULL, updated_at = ?
            WHERE user_id = ? AND related_type = ? AND related_id = ?
            """,
            (_now(), user_id, deliberation_type, entity_id),
        )
        cleared["deliberations"] = cursor.rowcount

    source_type = {
        "reviews": "review",
        "feedback_items": "feedback",
        "experiments": "experiment",
        "opportunities": "opportunity",
    }.get(table)
    if source_type:
        if table == "reviews":
            cursor = conn.execute(
                """
                UPDATE assets
                SET source_review_id = NULL, source_type = '', source_id = NULL,
                    updated_at = ?
                WHERE user_id = ? AND (
                    source_review_id = ? OR (source_type = 'review' AND source_id = ?)
                )
                """,
                (_now(), user_id, entity_id, entity_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE assets
                SET source_type = '', source_id = NULL, updated_at = ?
                WHERE user_id = ? AND source_type = ? AND source_id = ?
                """,
                (_now(), user_id, source_type, entity_id),
            )
        cleared["assets"] = cursor.rowcount

    if table == "goals":
        cursor = conn.execute(
            """
            UPDATE positioning_goal_action
            SET target_goal_id = NULL
            WHERE user_id = ? AND target_goal_id = ?
            """,
            (user_id, entity_id),
        )
        cleared["positioning_goal_action"] = cursor.rowcount
    return {key: value for key, value in cleared.items() if value}


def _delete_entity(table, entity_id, entity_label, user_id):
    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        existing = conn.execute(
            f"SELECT id FROM {table} WHERE id = ? AND user_id = ?",
            (entity_id, owner_id),
        ).fetchone()
        if not existing:
            raise ValueError(f"{entity_label}不存在")

        cleared = _clear_soft_references(conn, table, entity_id, owner_id)
        conn.execute(
            f"DELETE FROM {table} WHERE id = ? AND user_id = ?",
            (entity_id, owner_id),
        )
        conn.commit()
        return {"id": entity_id, "deleted": True, "cleared": cleared}
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            f"无法删除{entity_label}：存在关联数据，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_goal(goal_id, user_id):
    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        existing = conn.execute(
            "SELECT id FROM goals WHERE id = ? AND user_id = ?", (goal_id, owner_id)
        ).fetchone()
        if not existing:
            raise ValueError("目标不存在")

        project_rows = conn.execute(
            "SELECT id FROM projects WHERE goal_id = ? AND user_id = ?",
            (goal_id, owner_id),
        ).fetchall()
        project_count = len(project_rows)
        task_count = conn.execute(
            """
            SELECT COUNT(*) FROM tasks
            WHERE project_id IN (
                SELECT id FROM projects WHERE goal_id = ? AND user_id = ?
            )
            AND user_id = ?
            """,
            (goal_id, owner_id, owner_id),
        ).fetchone()[0]

        cleared = _clear_soft_references(conn, "goals", goal_id, owner_id)
        for project in project_rows:
            child_cleared = _clear_soft_references(
                conn, "projects", project["id"], owner_id
            )
            for table, count in child_cleared.items():
                cleared[table] = cleared.get(table, 0) + count
        conn.execute(
            "DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, owner_id)
        )
        conn.commit()
        return {
            "id": goal_id,
            "deleted": True,
            "cascaded": {"projects": project_count, "tasks": task_count},
            "cleared": cleared,
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            "无法删除目标：存在关联数据约束，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_project(project_id, user_id):
    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        existing = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, owner_id),
        ).fetchone()
        if not existing:
            raise ValueError("项目不存在")

        task_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE project_id = ? AND user_id = ?",
            (project_id, owner_id),
        ).fetchone()[0]

        cleared = _clear_soft_references(conn, "projects", project_id, owner_id)
        conn.execute(
            "DELETE FROM projects WHERE id = ? AND user_id = ?",
            (project_id, owner_id),
        )
        conn.commit()
        return {
            "id": project_id,
            "deleted": True,
            "cascaded": {"tasks": task_count},
            "cleared": cleared,
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            "无法删除项目：存在关联数据约束，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_task(task_id, user_id):
    return _delete_entity("tasks", task_id, "任务", user_id)


def delete_review(review_id, user_id):
    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        existing = conn.execute(
            "SELECT id FROM reviews WHERE id = ? AND user_id = ?",
            (review_id, owner_id),
        ).fetchone()
        if not existing:
            raise ValueError("复盘不存在")

        asset_count = conn.execute(
            """
            SELECT COUNT(*) FROM assets
            WHERE source_review_id = ? AND user_id = ?
            """,
            (review_id, owner_id),
        ).fetchone()[0]

        cleared = _clear_soft_references(conn, "reviews", review_id, owner_id)
        conn.execute(
            "DELETE FROM reviews WHERE id = ? AND user_id = ?",
            (review_id, owner_id),
        )
        conn.commit()
        return {
            "id": review_id,
            "deleted": True,
            "cleared_asset_links": asset_count,
            "cleared": cleared,
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            "无法删除复盘：存在关联数据约束，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_asset(asset_id, user_id):
    return _delete_entity("assets", asset_id, "资产", user_id)


def delete_capability_entry(entry_id, user_id):
    return _delete_entity("capability_entries", entry_id, "能力记录", user_id)


_OPTIONAL_IMPORT_FIELDS = {
    "today_progress_date",
    "source_review_id",
    "source_project",
    "summary",
    "fields",
    "reusable_scenario",
    "maturity",
    "reuse_count",
    "source_type",
    "source_id",
    "updated_at",
    "opportunity_id",
    "related_type",
    "related_id",
    "target_goal_id",
    "description",
    "detail",
    "payload",
    "suggested_payload",
    "confidence",
    "reason",
    *PROJECT_AUDIT_FIELDS,
    *ASSET_VALUE_FIELDS,
    *OPPORTUNITY_TEXT_FIELDS,
    *EXPERIMENT_TEXT_FIELDS,
}


def _parse_import_json_object(value, label):
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} 格式无效") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} 格式无效")
    return value


def _strip_import_user_ids(value):
    if isinstance(value, dict):
        return {
            key: _strip_import_user_ids(item)
            for key, item in value.items()
            if key != "user_id"
        }
    if isinstance(value, list):
        return [_strip_import_user_ids(item) for item in value]
    return value


def _normalize_import_record(table, raw):
    if not isinstance(raw, dict):
        raise ValueError("记录必须是对象")
    fields = _TABLE_FIELDS[table]
    record = {}
    for key in fields:
        if key not in raw:
            if key == "today_progress":
                record[key] = 0
            elif key == "priority":
                record[key] = "medium"
            elif key in VALUE_SCORE_FIELDS or key == "total_score":
                record[key] = 0
            elif key == "status":
                record[key] = {
                    "goals": "active",
                    "opportunities": "待审计",
                    "experiments": "设计中",
                    "positioning_goal_action": "pending",
                    "inbox_entries": "draft",
                    "inbox_suggestions": "pending",
                }.get(table, "")
            elif key == "experiment_type":
                record[key] = "结果型MVP"
            elif key == "source" and table == "feedback_items":
                record[key] = "自我判断"
            elif key == "level":
                record[key] = "L0 只是想法"
            elif key == "asset_level":
                record[key] = "资料"
            elif key == "source_type":
                record[key] = "manual" if table == "inbox_entries" else ""
            elif key in {"source_id", "target_goal_id"}:
                record[key] = None
            elif key in {"payload", "suggested_payload"}:
                record[key] = {}
            elif key == "confidence":
                record[key] = 0.0
            elif key == "cycle" and table == "positioning_calibration":
                record[key] = "触发式"
            elif (
                key in PROJECT_AUDIT_FIELDS
                or key in ASSET_VALUE_FIELDS
                or key in OPPORTUNITY_TEXT_FIELDS
                or key in EXPERIMENT_TEXT_FIELDS
                or key in {
                    "related_type",
                    "content",
                    "evidence",
                    "next_action",
                    "description",
                    "detail",
                    "reason",
                    "first_principle",
                    "identity_core",
                    "flywheel_def",
                    "current_stage",
                    "north_star",
                    "primary_contradiction",
                    "doing_but_shouldnt",
                    "should_but_not_doing",
                    "alignment_review",
                    "conclusion",
                }
            ):
                record[key] = ""
            elif key in _OPTIONAL_IMPORT_FIELDS:
                record[key] = None
            else:
                raise ValueError(f"缺少字段 {key}")
        else:
            record[key] = raw[key]

    if "updated_at" in record and not record.get("updated_at"):
        record["updated_at"] = record.get("created_at") or _now()

    if table == "assets":
        tags = record["capability_tags"]
        if isinstance(tags, list):
            tags = _parse_tags(json.dumps(tags))
            record["capability_tags"] = json.dumps(tags, ensure_ascii=False)
        elif isinstance(tags, str):
            record["capability_tags"] = json.dumps(
                _parse_tags(tags), ensure_ascii=False
            )
        else:
            raise ValueError("capability_tags 格式无效")

        record["asset_type"] = asset_schemas.normalize_asset_type(
            record.get("asset_type"),
            record.get("title", ""),
            record.get("core_content", ""),
        )
        parsed_fields = asset_schemas.parse_fields(record.get("fields"))
        if not parsed_fields:
            parsed_fields = asset_schemas.build_fields_from_legacy(
                record["asset_type"],
                record.get("trigger_context") or "",
                record.get("core_content") or "",
            )
        record["fields"] = asset_schemas.serialize_fields(parsed_fields)
        legacy_trigger, legacy_core = asset_schemas.sync_legacy_columns(
            record["asset_type"], parsed_fields
        )
        record["trigger_context"] = legacy_trigger or record.get("trigger_context") or ""
        record["core_content"] = legacy_core or record.get("core_content") or ""
        record["summary"] = (record.get("summary") or "").strip() or asset_schemas.extract_summary(
            parsed_fields, record["core_content"]
        )
        record["reusable_scenario"] = (
            (record.get("reusable_scenario") or "").strip()
            or asset_schemas.extract_reusable_scenario(record["asset_type"], parsed_fields)
        )
        if record.get("maturity") not in MATURITY_LEVELS:
            record["maturity"] = "可用"
        record["reuse_count"] = int(record.get("reuse_count") or 0)
        if not record.get("source_type") and record.get("source_review_id"):
            record["source_type"] = "review"
        if record.get("source_id") in ("", None) and record.get("source_review_id"):
            record["source_id"] = record["source_review_id"]
        if not record.get("updated_at"):
            record["updated_at"] = record.get("created_at")

    if table == "goals" and record["type"] not in GOAL_TYPES:
        raise ValueError("无效的目标类型")
    if table in {"projects", "tasks"}:
        record["priority"] = _normalize_priority(record.get("priority"), strict=True)
    if table == "projects":
        scores = _value_scores_from_payload(record)
        for field, value in scores.items():
            record[field] = value
    if table == "tasks" and record["status"] not in TASK_STATUSES:
        raise ValueError("无效的任务状态")
    if table == "reviews" and record["type"] not in REVIEW_TYPES:
        raise ValueError("无效的复盘类型")
    if table == "assets" and record["asset_type"] not in ASSET_TYPES:
        raise ValueError("无效的资产类型")
    if table == "assets" and record.get("asset_level") not in ASSET_LEVELS:
        record["asset_level"] = "资料"
    if table == "capability_entries":
        if record["module"] not in CAPABILITY_MODULES:
            raise ValueError("无效的能力模块")
        if record["level_type"] not in LEVEL_TYPES:
            raise ValueError("无效的层级判断")
    if table == "capability_practice_steps":
        if record["module"] not in CAPABILITY_MODULES:
            raise ValueError("无效的能力模块")
        try:
            record["step_order"] = int(record["step_order"])
        except (TypeError, ValueError) as exc:
            raise ValueError("训练步骤排序必须是正整数") from exc
        if record["step_order"] <= 0:
            raise ValueError("训练步骤排序必须是正整数")
        if not _as_text(record.get("title")):
            raise ValueError("训练步骤名称不能为空")
    if table == "opportunities":
        if record["status"] not in OPPORTUNITY_STATUSES:
            record["status"] = "待审计"
        scores = _value_scores_from_payload(record)
        for field, value in scores.items():
            record[field] = value
    if table == "experiments":
        if record["experiment_type"] not in EXPERIMENT_TYPES:
            record["experiment_type"] = "结果型MVP"
        if record["status"] not in EXPERIMENT_STATUSES:
            record["status"] = "设计中"
    if table == "feedback_items":
        if record["source"] not in FEEDBACK_SOURCES:
            record["source"] = "自我判断"
        if record["level"] not in FEEDBACK_LEVELS:
            record["level"] = "L0 只是想法"
        if record["related_type"] and record["related_type"] not in FEEDBACK_RELATED_TYPES:
            raise ValueError("无效的反馈关联类型")
    if table == "deliberations":
        if record["status"] not in DELIBERATION_STATUSES:
            raise ValueError("无效的推演状态")
        if record["related_type"] not in ("", *DELIBERATION_RELATED_TYPES):
            raise ValueError("无效的推演关联类型")
        raw_analysis = record.get("ai_analysis")
        if isinstance(raw_analysis, str):
            try:
                raw_analysis = json.loads(raw_analysis or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError("AI 分析结果格式无效") from exc
        if not isinstance(raw_analysis, dict):
            raise ValueError("AI 分析结果格式无效")
        record["ai_analysis"] = json.dumps(raw_analysis, ensure_ascii=False)
    if table == "positioning_calibration":
        if record["cycle"] not in POSITIONING_CYCLES:
            raise ValueError("无效的校准周期")
        if not _as_text(record.get("calibrated_at")):
            raise ValueError("校准日期不能为空")
    if table == "positioning_goal_action":
        if record["action_type"] not in POSITIONING_ACTION_TYPES:
            raise ValueError("无效的目标变更类型")
        if record["status"] not in POSITIONING_ACTION_STATUSES:
            raise ValueError("无效的目标变更状态")
        action_payload = _strip_import_user_ids(
            _parse_import_json_object(record.get("payload"), "目标变更 payload")
        )
        record["payload"] = json.dumps(action_payload, ensure_ascii=False)
        if not _as_text(record.get("reason")):
            raise ValueError("变更理由不能为空")
    if table == "inbox_entries":
        if not _as_text(record.get("raw_text")):
            raise ValueError("Inbox 内容不能为空")
        if record.get("source_type") != "manual":
            raise ValueError("无效的 Inbox source_type")
        if record.get("status") not in INBOX_ENTRY_STATUSES:
            raise ValueError("无效的 Inbox 状态")
    if table == "inbox_suggestions":
        if record.get("target_type") not in INBOX_TARGET_TYPES:
            raise ValueError("无效的 Inbox 建议类型")
        if record.get("status") not in INBOX_SUGGESTION_STATUSES:
            raise ValueError("无效的 Inbox 建议状态")
        try:
            confidence = float(record.get("confidence") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Inbox 建议 confidence 无效") from exc
        record["confidence"] = max(0.0, min(1.0, confidence))
        suggestion_payload = _strip_import_user_ids(
            _parse_import_json_object(
                record.get("suggested_payload"), "Inbox suggested_payload"
            )
        )
        record["suggested_payload"] = json.dumps(
            suggestion_payload, ensure_ascii=False
        )

    return record


def _records_equal(table, existing_row, incoming):
    fields = _TABLE_FIELDS[table]
    for key in fields:
        existing_val = existing_row[key]
        incoming_val = incoming[key]
        if key == "capability_tags" and table == "assets":
            existing_val = _parse_tags(existing_val)
            incoming_val = _parse_tags(incoming_val)
        elif (table, key) in {
            ("assets", "fields"),
            ("deliberations", "ai_analysis"),
            ("positioning_goal_action", "payload"),
            ("inbox_suggestions", "suggested_payload"),
        }:
            try:
                existing_val = json.loads(existing_val or "{}")
            except (TypeError, json.JSONDecodeError):
                existing_val = {}
            try:
                incoming_val = json.loads(incoming_val or "{}")
            except (TypeError, json.JSONDecodeError):
                incoming_val = {}
        if existing_val != incoming_val:
            return False
    return True


_IMPORT_ASSET_SOURCE_TABLES = {
    "review": "reviews",
    "feedback": "feedback_items",
    "experiment": "experiments",
    "opportunity": "opportunities",
}
_IMPORT_FEEDBACK_TARGET_TABLES = {
    "opportunity": "opportunities",
    "experiment": "experiments",
    "project": "projects",
    "asset": "assets",
    "review": "reviews",
}


def _coerce_import_id(value, label="id"):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} 必须是正整数")
    return value


def _map_import_reference(
    conn, id_maps, table, value, user_id, label, *, required=False
):
    if value in (None, ""):
        if required:
            raise ValueError(f"{label} 不能为空")
        return None, None
    if isinstance(value, bool):
        raise ValueError(f"{label} 必须是正整数")
    try:
        source_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是正整数") from exc
    if source_id <= 0:
        raise ValueError(f"{label} 必须是正整数")

    if source_id in id_maps[table]:
        destination_id = id_maps[table][source_id]
        return destination_id, (table, destination_id)
    owned = conn.execute(
        f'SELECT id FROM "{table}" WHERE id = ? AND user_id = ?',
        (source_id, user_id),
    ).fetchone()
    if owned:
        return source_id, (table, source_id)
    raise ValueError(f"{label} 不存在")


def _map_suggestion_payload_references(
    conn, record, id_maps, user_id, dependencies
):
    payload = _strip_import_user_ids(
        _parse_import_json_object(
            record.get("suggested_payload"), "Inbox suggested_payload"
        )
    )
    payload.pop("target_id", None)
    target_type = record.get("target_type")

    def map_field(field, table, label):
        if payload.get(field) in (None, ""):
            return
        mapped, dependency = _map_import_reference(
            conn, id_maps, table, payload[field], user_id, label
        )
        payload[field] = mapped
        if dependency:
            dependencies.add(dependency)

    if target_type == "project":
        map_field("goal_id", "goals", "Inbox 建议关联目标")
    elif target_type == "task":
        map_field("project_id", "projects", "Inbox 建议关联项目")
    elif target_type == "asset":
        map_field("source_review_id", "reviews", "Inbox 建议来源复盘")
        source_id = payload.get("source_id")
        source_type = _as_text(payload.get("source_type"))
        if source_id not in (None, ""):
            if source_type not in _IMPORT_ASSET_SOURCE_TABLES:
                raise ValueError("Inbox 建议资产来源类型无效")
            map_field(
                "source_id",
                _IMPORT_ASSET_SOURCE_TABLES[source_type],
                "Inbox 建议资产来源对象",
            )
    elif target_type == "experiment":
        map_field("opportunity_id", "opportunities", "Inbox 建议关联机会")
    elif target_type == "feedback":
        related_type = _as_text(payload.get("related_type"))
        related_id = payload.get("related_id")
        if not related_type and related_id not in (None, ""):
            raise ValueError("Inbox 建议缺少反馈关联类型")
        if related_type and related_id not in (None, ""):
            if related_type not in _IMPORT_FEEDBACK_TARGET_TABLES:
                raise ValueError("Inbox 建议反馈关联类型无效")
            map_field(
                "related_id",
                _IMPORT_FEEDBACK_TARGET_TABLES[related_type],
                "Inbox 建议反馈关联对象",
            )

    record["suggested_payload"] = json.dumps(payload, ensure_ascii=False)


def _rewrite_import_relationships(conn, table, incoming, id_maps, user_id):
    record = dict(incoming)
    dependencies = set()

    def map_value(field, parent_table, label, *, required=False):
        mapped, dependency = _map_import_reference(
            conn,
            id_maps,
            parent_table,
            record.get(field),
            user_id,
            label,
            required=required,
        )
        record[field] = mapped
        if dependency:
            dependencies.add(dependency)

    if table == "projects":
        map_value("goal_id", "goals", "关联目标", required=True)
    elif table == "tasks":
        map_value("project_id", "projects", "关联项目", required=True)
    elif table == "experiments":
        map_value("opportunity_id", "opportunities", "关联机会")
    elif table == "assets":
        map_value("source_review_id", "reviews", "来源复盘")
        source_type = _as_text(record.get("source_type"))
        source_id = record.get("source_id")
        if source_id not in (None, ""):
            if source_type not in _IMPORT_ASSET_SOURCE_TABLES:
                raise ValueError("无效的资产来源类型")
            mapped, dependency = _map_import_reference(
                conn,
                id_maps,
                _IMPORT_ASSET_SOURCE_TABLES[source_type],
                source_id,
                user_id,
                "资产来源对象",
            )
            record["source_id"] = mapped
            dependencies.add(dependency)
            if source_type == "review":
                if record.get("source_review_id") not in (None, mapped):
                    raise ValueError("资产来源复盘不一致")
                record["source_review_id"] = mapped
        elif source_type:
            raise ValueError("资产来源缺少 source_id")
    elif table == "feedback_items":
        related_type = _as_text(record.get("related_type"))
        related_id = record.get("related_id")
        if not related_type:
            if related_id not in (None, ""):
                raise ValueError("未设置反馈关联类型时 related_id 必须为空")
            record["related_id"] = None
        elif related_id not in (None, ""):
            map_value(
                "related_id",
                _IMPORT_FEEDBACK_TARGET_TABLES[related_type],
                "反馈关联对象",
            )
    elif table == "deliberations":
        related_type = _as_text(record.get("related_type"))
        related_id = record.get("related_id")
        if not related_type:
            if related_id not in (None, ""):
                raise ValueError("未设置推演关联类型时 related_id 必须为空")
            record["related_id"] = None
        else:
            parent_table = (
                "projects" if related_type == "project" else "opportunities"
            )
            map_value("related_id", parent_table, "推演关联对象", required=True)
    elif table == "positioning_goal_action":
        map_value(
            "calibration_id",
            "positioning_calibration",
            "定位校准记录",
            required=True,
        )
        action_type = record.get("action_type")
        if action_type == "新建目标":
            if record.get("target_goal_id") not in (None, ""):
                raise ValueError("新建目标不应指定 target_goal_id")
            record["target_goal_id"] = None
        else:
            map_value(
                "target_goal_id",
                "goals",
                "定位目标",
                required=True,
            )
    elif table == "inbox_suggestions":
        map_value(
            "inbox_entry_id",
            "inbox_entries",
            "Inbox 记录",
            required=True,
        )
        _map_suggestion_payload_references(
            conn, record, id_maps, user_id, dependencies
        )

    return record, dependencies


def _build_import_plan(conn, payload, user_id):
    owner_id = _resolve_owner_id(conn, user_id)
    occupied = {}
    owned = {}
    next_ids = {}
    for table in IMPORT_TABLES:
        occupied[table] = {
            row["id"]
            for row in conn.execute(f'SELECT id FROM "{table}"').fetchall()
        }
        owned[table] = {
            row["id"]
            for row in conn.execute(
                f'SELECT id FROM "{table}" WHERE user_id = ?', (owner_id,)
            ).fetchall()
        }
        next_ids[table] = max(occupied[table], default=0) + 1

    id_maps = {table: {} for table in IMPORT_TABLES}
    source_ids = {table: set() for table in IMPORT_TABLES}
    destination_ids = {table: set() for table in IMPORT_TABLES}
    normalized_items = []
    errors = []

    def add_error(label, message):
        errors.append((label, message or "记录无效"))

    for table in IMPORT_TABLES:
        existing_anchor_id = None
        if table == "positioning_anchor" and owned[table]:
            existing_anchor_id = next(iter(owned[table]))
        for index, raw in enumerate(payload.get(table, [])):
            label = f"{table}[{index}]"
            try:
                record = _normalize_import_record(table, raw)
                source_id = _coerce_import_id(record.get("id"))
                if source_id in source_ids[table]:
                    raise ValueError(f"重复 id={source_id}")
                source_ids[table].add(source_id)

                if existing_anchor_id is not None:
                    destination_id = existing_anchor_id
                elif source_id in owned[table]:
                    destination_id = source_id
                elif source_id not in occupied[table]:
                    destination_id = source_id
                else:
                    destination_id = next_ids[table]
                    while destination_id in occupied[table]:
                        destination_id += 1
                    next_ids[table] = destination_id + 1

                if destination_id in destination_ids[table]:
                    raise ValueError("多条记录映射到同一目标 id")
                destination_ids[table].add(destination_id)
                occupied[table].add(destination_id)
                id_maps[table][source_id] = destination_id
                record["id"] = destination_id
                normalized_items.append({
                    "table": table,
                    "index": index,
                    "label": label,
                    "source_id": source_id,
                    "destination_id": destination_id,
                    "record": record,
                })
            except (ValueError, TypeError) as exc:
                add_error(label, str(exc))

    preliminary = []
    for item in normalized_items:
        try:
            record, dependencies = _rewrite_import_relationships(
                conn, item["table"], item["record"], id_maps, owner_id
            )
            preliminary.append({**item, "record": record, "dependencies": dependencies})
        except (ValueError, TypeError) as exc:
            add_error(item["label"], str(exc))

    valid = list(preliminary)
    while True:
        planned = {table: set() for table in IMPORT_TABLES}
        for item in valid:
            planned[item["table"]].add(item["destination_id"])
        kept = []
        removed = []
        for item in valid:
            missing = [
                (table, entity_id)
                for table, entity_id in item["dependencies"]
                if entity_id not in owned[table] and entity_id not in planned[table]
            ]
            if missing:
                removed.append(item)
            else:
                kept.append(item)
        if not removed:
            break
        for item in removed:
            add_error(item["label"], "关联对象未能通过导入校验")
        valid = kept

    plan = []
    for item in valid:
        table = item["table"]
        destination_id = item["destination_id"]
        existing = conn.execute(
            f'SELECT * FROM "{table}" WHERE id = ? AND user_id = ?',
            (destination_id, owner_id),
        ).fetchone()
        if existing and _records_equal(table, existing, item["record"]):
            action = "skip"
        elif existing:
            action = "update"
        else:
            action = "insert"
        plan.append({**item, "action": action})

    return {
        "owner_id": owner_id,
        "rows": plan,
        "errors": errors,
        "remapped": sum(
            item["source_id"] != item["destination_id"] for item in plan
        ),
    }


def _new_import_stats():
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "imported": 0,
        "remapped": 0,
    }


IMPORT_ROLLBACK_MESSAGE = "导入失败，所有变更已回滚，数据库未被修改"


def _finalize_import_stats(stats):
    stats["imported"] = stats["created"] + stats["updated"]
    return stats


def _import_failure_stats(stats=None, errors=None):
    err_list = list(stats.get("errors", [])) if stats else []
    if errors:
        err_list = list(errors)
    failed = stats.get("failed", 0) if stats else 0
    if failed <= 0:
        failed = max(len(err_list), 1) if err_list else 1
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": failed,
        "errors": err_list,
        "imported": 0,
        "remapped": 0,
        "rolled_back": True,
        "message": IMPORT_ROLLBACK_MESSAGE,
    }


def _apply_import_plan_row(conn, item, user_id):
    action = item["action"]
    if action == "skip":
        return

    table = item["table"]
    record = item["record"]
    row_id = item["destination_id"]
    fields = _TABLE_FIELDS[table]
    if action == "update":
        update_fields = [field for field in fields if field != "id"]
        set_clause = ", ".join(f'"{field}" = ?' for field in update_fields)
        cursor = conn.execute(
            f'UPDATE "{table}" SET {set_clause} WHERE id = ? AND user_id = ?',
            (*(record[field] for field in update_fields), row_id, user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("导入目标不存在")
        return

    columns = ", ".join(f'"{field}"' for field in ("user_id", *fields))
    placeholders = ", ".join("?" for _ in range(len(fields) + 1))
    conn.execute(
        f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
        (user_id, *(record[field] for field in fields)),
    )


def _validate_import_payload(payload):
    if not isinstance(payload, dict):
        raise DataImportError("导入数据必须是 JSON 对象")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise DataImportError("缺少 meta 字段")
    version = meta.get("version")
    if version not in SUPPORTED_IMPORT_VERSIONS:
        raise DataImportError(
            f"不支持的备份版本：{version!r}，当前兼容 {', '.join(SUPPORTED_IMPORT_VERSIONS)}"
        )

    required_tables = (
        REQUIRED_IMPORT_TABLES if version == "2.0" else LEGACY_IMPORT_TABLES
    )
    for table in required_tables:
        if table not in payload:
            raise DataImportError(f"缺少数据表：{table}")
        if not isinstance(payload[table], list):
            raise DataImportError(f"{table} 必须是数组")
    for table in IMPORT_TABLES:
        if table in payload and not isinstance(payload[table], list):
            raise DataImportError(f"{table} 必须是数组")


def _refresh_sqlite_sequences(conn):
    for table in IMPORT_TABLES:
        row = conn.execute(f"SELECT MAX(id) AS max_id FROM {table}").fetchone()
        max_id = row["max_id"] if row and row["max_id"] is not None else 0
        seq = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
        ).fetchone()
        if seq:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                (max_id, table),
            )
        elif max_id > 0:
            conn.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
                (table, max_id),
            )


def preview_import_data(payload, user_id):
    _validate_import_payload(payload)
    conn = get_connection()
    try:
        plan = _build_import_plan(conn, payload, user_id)
        actions = Counter(item["action"] for item in plan["rows"])
        return {
            "will_import": actions["insert"],
            "will_update": actions["update"],
            "will_skip": actions["skip"],
            "will_fail": len(plan["errors"]),
            "errors": [
                f"{label}: {message}"
                for label, message in plan["errors"][:20]
            ],
            "remapped": plan["remapped"],
        }
    finally:
        conn.close()


def import_all_data(payload, user_id):
    try:
        _validate_import_payload(payload)
    except DataImportError as exc:
        raise DataImportError(
            str(exc),
            exc.stats or _import_failure_stats(errors=[str(exc)]),
        ) from exc

    stats = _new_import_stats()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        plan = _build_import_plan(conn, payload, user_id)
        owner_id = plan["owner_id"]
        if plan["errors"]:
            stats["failed"] = len(plan["errors"])
            stats["errors"] = [
                f"{label}: {message}"
                for label, message in plan["errors"][:20]
            ]
            conn.rollback()
            failure = _import_failure_stats(stats)
            summary = (
                f"导入失败：{failure['failed']} 条记录有误，"
                "已回滚，原有数据未改动"
            )
            raise DataImportError(summary, failure)

        stats["remapped"] = plan["remapped"]
        for item in plan["rows"]:
            try:
                _apply_import_plan_row(conn, item, owner_id)
                stats[
                    {"insert": "created", "update": "updated", "skip": "skipped"}[
                        item["action"]
                    ]
                ] += 1
            except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
                stats["failed"] += 1
                if len(stats["errors"]) < 20:
                    stats["errors"].append(
                        f"{item['label']}: {str(exc) or '记录无效'}"
                    )
                break

        if stats["failed"]:
            conn.rollback()
            failure = _import_failure_stats(stats)
            raise DataImportError(
                f"导入失败：{failure['failed']} 条记录有误，已回滚，原有数据未改动",
                failure,
            )

        _normalize_mainline_goals(conn, owner_id)
        for module in CAPABILITY_MODULES:
            _normalize_practice_step_order(conn, module, owner_id)
        _refresh_sqlite_sequences(conn)
        conn.commit()
        return _finalize_import_stats(stats)
    except DataImportError:
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise DataImportError(
            "数据库导入失败，已回滚",
            _import_failure_stats(errors=[str(exc)]),
        ) from exc
    finally:
        conn.close()


def backup_filename():
    return datetime.now().strftime("backup_%Y%m%d_%H%M%S.json")


def _export_business_row(table, row):
    data = {field: row[field] for field in _TABLE_FIELDS[table]}
    if table == "assets":
        data["capability_tags"] = _parse_tags(data.get("capability_tags"))
        data["fields"] = asset_schemas.parse_fields(data.get("fields"))
    elif table == "deliberations":
        try:
            data["ai_analysis"] = json.loads(data.get("ai_analysis") or "{}")
        except (TypeError, json.JSONDecodeError):
            data["ai_analysis"] = {}
    elif table == "positioning_goal_action":
        data["payload"] = _strip_import_user_ids(
            _parse_positioning_payload(data.get("payload"))
        )
    elif table == "inbox_suggestions":
        data["suggested_payload"] = _strip_import_user_ids(
            _parse_suggested_payload(data.get("suggested_payload"))
        )
    return data


def export_all_data(user_id):
    conn = get_connection()
    try:
        owner_id = _resolve_owner_id(conn, user_id)
        payload = {
            "meta": {
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "2.0",
                "tables": list(IMPORT_TABLES),
            },
        }
        for table in IMPORT_TABLES:
            rows = conn.execute(
                f'SELECT * FROM "{table}" WHERE user_id = ? ORDER BY id ASC',
                (owner_id,),
            ).fetchall()
            payload[table] = [
                _export_business_row(table, row) for row in rows
            ]
        return payload
    except sqlite3.Error as exc:
        raise ExportError(
            "数据库读取失败，请关闭占用数据库的程序后重试"
        ) from exc
    except Exception as exc:
        raise ExportError("导出数据时发生错误，请稍后重试") from exc
    finally:
        conn.close()


def _opportunity_row(row):
    data = _row_to_dict(row)
    if data:
        for field in VALUE_SCORE_FIELDS:
            data[field] = _score(data.get(field))
        data["total_score"] = sum(data[field] for field in VALUE_SCORE_FIELDS)
        if data.get("status") not in OPPORTUNITY_STATUSES:
            data["status"] = "待审计"
    return data


def list_opportunities(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM opportunities
        WHERE user_id = ?
        ORDER BY total_score DESC, updated_at DESC, created_at DESC
        """,
        (owner_id,),
    ).fetchall()
    conn.close()
    return [_opportunity_row(row) for row in rows]


def get_opportunity(opportunity_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM opportunities WHERE id = ? AND user_id = ?",
        (opportunity_id, owner_id),
    ).fetchone()
    conn.close()
    return _opportunity_row(row)


def create_opportunity(payload, user_id):
    payload = payload or {}
    name = _clean_text(payload.get("name"))
    if not name:
        raise ValueError("机会名称不能为空")
    status = payload.get("status") or "待审计"
    if status not in OPPORTUNITY_STATUSES:
        status = "待审计"
    scores = _value_scores_from_payload(payload)
    now = _now()
    record = {
        "name": name,
        "status": status,
        "created_at": now,
        "updated_at": now,
        **{field: _clean_text(payload.get(field)) for field in OPPORTUNITY_TEXT_FIELDS},
        **scores,
    }
    fields = tuple(record.keys())
    placeholders = ", ".join("?" for _ in fields)
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    cur = conn.execute(
        f"INSERT INTO opportunities (user_id, {', '.join(fields)}) "
        f"VALUES (?, {placeholders})",
        (owner_id, *(record[field] for field in fields)),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM opportunities WHERE id = ? AND user_id = ?",
        (cur.lastrowid, owner_id),
    ).fetchone()
    conn.close()
    return _opportunity_row(row)


def update_opportunity(opportunity_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT * FROM opportunities WHERE id = ? AND user_id = ?",
        (opportunity_id, owner_id),
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("机会不存在")
    updates = {}
    if "name" in payload:
        name = _clean_text(payload.get("name"))
        if not name:
            conn.close()
            raise ValueError("机会名称不能为空")
        updates["name"] = name
    if "status" in payload:
        status = payload.get("status")
        if status not in OPPORTUNITY_STATUSES:
            conn.close()
            raise ValueError("无效的机会状态")
        updates["status"] = status
    for field in OPPORTUNITY_TEXT_FIELDS:
        if field in payload:
            updates[field] = _clean_text(payload.get(field))
    if any(field in payload for field in VALUE_SCORE_FIELDS):
        updates.update(_value_scores_from_payload(payload, existing))
    if not updates:
        conn.close()
        raise ValueError("没有可更新的机会字段")
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE opportunities SET {set_clause} WHERE id = ? AND user_id = ?",
        (*updates.values(), opportunity_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM opportunities WHERE id = ? AND user_id = ?",
        (opportunity_id, owner_id),
    ).fetchone()
    conn.close()
    return _opportunity_row(row)


def delete_opportunity(opportunity_id, user_id):
    return _delete_entity("opportunities", opportunity_id, "机会", user_id)


def _experiment_row(row):
    data = _row_to_dict(row)
    if data:
        if data.get("experiment_type") not in EXPERIMENT_TYPES:
            data["experiment_type"] = "结果型MVP"
        if data.get("status") not in EXPERIMENT_STATUSES:
            data["status"] = "设计中"
    return data


def _normalize_opportunity_id(conn, value, user_id):
    if value in (None, ""):
        return None
    try:
        opportunity_id = int(value)
    except (TypeError, ValueError):
        raise ValueError("关联机会无效")
    owner_id = _resolve_owner_id(conn, user_id)
    if not conn.execute(
        "SELECT id FROM opportunities WHERE id = ? AND user_id = ?",
        (opportunity_id, owner_id),
    ).fetchone():
        raise ValueError("关联机会不存在")
    return opportunity_id


def list_experiments(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT e.*, o.name AS opportunity_name
        FROM experiments e
        LEFT JOIN opportunities o
          ON o.id = e.opportunity_id AND o.user_id = e.user_id
        WHERE e.user_id = ?
        ORDER BY e.updated_at DESC, e.created_at DESC
        """,
        (owner_id,),
    ).fetchall()
    conn.close()
    return [_experiment_row(row) for row in rows]


def get_experiment(experiment_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        """
        SELECT e.*, o.name AS opportunity_name
        FROM experiments e
        LEFT JOIN opportunities o
          ON o.id = e.opportunity_id AND o.user_id = e.user_id
        WHERE e.id = ? AND e.user_id = ?
        """,
        (experiment_id, owner_id),
    ).fetchone()
    conn.close()
    return _experiment_row(row)


def create_experiment(payload, user_id):
    payload = payload or {}
    name = _clean_text(payload.get("name"))
    if not name:
        raise ValueError("实验名称不能为空")
    experiment_type = payload.get("experiment_type") or "结果型MVP"
    if experiment_type not in EXPERIMENT_TYPES:
        raise ValueError("无效的实验类型")
    status = payload.get("status") or "设计中"
    if status not in EXPERIMENT_STATUSES:
        status = "设计中"
    now = _now()
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    opportunity_id = _normalize_opportunity_id(
        conn,
        payload.get("opportunity_id", payload.get("source_opportunity_id")),
        owner_id,
    )
    if payload.get("require_opportunity") and opportunity_id is None:
        conn.close()
        raise ValueError("从机会创建实验时必须关联 opportunity_id")
    record = {
        "opportunity_id": opportunity_id,
        "name": name,
        "experiment_type": experiment_type,
        "status": status,
        "created_at": now,
        "updated_at": now,
        **{field: _clean_text(payload.get(field)) for field in EXPERIMENT_TEXT_FIELDS},
    }
    fields = tuple(record.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO experiments (user_id, {', '.join(fields)}) "
        f"VALUES (?, {placeholders})",
        (owner_id, *(record[field] for field in fields)),
    )
    if opportunity_id:
        conn.execute(
            """
            UPDATE opportunities SET status = '已进入MVP', updated_at = ?
            WHERE id = ? AND user_id = ? AND status IN ('待审计', '值得测试')
            """,
            (now, opportunity_id, owner_id),
        )
    conn.commit()
    row = conn.execute(
        """
        SELECT e.*, o.name AS opportunity_name
        FROM experiments e
        LEFT JOIN opportunities o
          ON o.id = e.opportunity_id AND o.user_id = e.user_id
        WHERE e.id = ? AND e.user_id = ?
        """,
        (cur.lastrowid, owner_id),
    ).fetchone()
    conn.close()
    return _experiment_row(row)


def update_experiment(experiment_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT * FROM experiments WHERE id = ? AND user_id = ?",
        (experiment_id, owner_id),
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("实验不存在")
    updates = {}
    if "name" in payload:
        name = _clean_text(payload.get("name"))
        if not name:
            conn.close()
            raise ValueError("实验名称不能为空")
        updates["name"] = name
    if "opportunity_id" in payload:
        updates["opportunity_id"] = _normalize_opportunity_id(
            conn, payload.get("opportunity_id"), owner_id
        )
    if "experiment_type" in payload:
        if payload.get("experiment_type") not in EXPERIMENT_TYPES:
            conn.close()
            raise ValueError("无效的实验类型")
        updates["experiment_type"] = payload.get("experiment_type")
    if "status" in payload:
        if payload.get("status") not in EXPERIMENT_STATUSES:
            conn.close()
            raise ValueError("无效的实验状态")
        updates["status"] = payload.get("status")
    for field in EXPERIMENT_TEXT_FIELDS:
        if field in payload:
            updates[field] = _clean_text(payload.get(field))
    if not updates:
        conn.close()
        raise ValueError("没有可更新的实验字段")
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE experiments SET {set_clause} WHERE id = ? AND user_id = ?",
        (*updates.values(), experiment_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT e.*, o.name AS opportunity_name
        FROM experiments e
        LEFT JOIN opportunities o
          ON o.id = e.opportunity_id AND o.user_id = e.user_id
        WHERE e.id = ? AND e.user_id = ?
        """,
        (experiment_id, owner_id),
    ).fetchone()
    conn.close()
    return _experiment_row(row)


def delete_experiment(experiment_id, user_id):
    return _delete_entity("experiments", experiment_id, "实验", user_id)


def _feedback_row(row):
    data = _row_to_dict(row)
    if data:
        if data.get("source") not in FEEDBACK_SOURCES:
            data["source"] = "自我判断"
        if data.get("level") not in FEEDBACK_LEVELS:
            data["level"] = "L0 只是想法"
    return data


def list_feedback_items(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM feedback_items
        WHERE user_id = ?
        ORDER BY updated_at DESC, created_at DESC
        """,
        (owner_id,),
    ).fetchall()
    conn.close()
    return [_feedback_row(row) for row in rows]


def get_feedback_item(feedback_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM feedback_items WHERE id = ? AND user_id = ?",
        (feedback_id, owner_id),
    ).fetchone()
    conn.close()
    return _feedback_row(row)


def _normalize_feedback_relation(related_type, related_id):
    related_type = _clean_text(related_type)
    if not related_type:
        return "", None
    if related_type not in FEEDBACK_RELATED_TYPES:
        raise ValueError("无效的反馈关联类型")
    if related_id in (None, ""):
        return related_type, None
    try:
        return related_type, int(related_id)
    except (TypeError, ValueError):
        raise ValueError("反馈关联 id 无效")


def create_feedback_item(payload, user_id):
    payload = payload or {}
    title = _clean_text(payload.get("title"))
    if not title:
        raise ValueError("反馈标题不能为空")
    source = payload.get("source") or "自我判断"
    if source not in FEEDBACK_SOURCES:
        source = "自我判断"
    level = payload.get("level") or "L0 只是想法"
    if level not in FEEDBACK_LEVELS:
        level = "L0 只是想法"
    related_type, related_id = _normalize_feedback_relation(
        payload.get("related_type"), payload.get("related_id")
    )
    now = _now()
    record = {
        "related_type": related_type,
        "related_id": related_id,
        "title": title,
        "source": source,
        "level": level,
        "content": _clean_text(payload.get("content")),
        "evidence": _clean_text(payload.get("evidence")),
        "next_action": _clean_text(payload.get("next_action")),
        "created_at": now,
        "updated_at": now,
    }
    fields = tuple(record.keys())
    placeholders = ", ".join("?" for _ in fields)
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    if related_id is not None:
        target_table = {
            "opportunity": "opportunities",
            "experiment": "experiments",
            "project": "projects",
            "asset": "assets",
            "review": "reviews",
        }[related_type]
        if not conn.execute(
            f'SELECT id FROM "{target_table}" WHERE id = ? AND user_id = ?',
            (related_id, owner_id),
        ).fetchone():
            conn.close()
            raise ValueError("反馈关联对象不存在")
    cur = conn.execute(
        f"INSERT INTO feedback_items (user_id, {', '.join(fields)}) "
        f"VALUES (?, {placeholders})",
        (owner_id, *(record[field] for field in fields)),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM feedback_items WHERE id = ? AND user_id = ?",
        (cur.lastrowid, owner_id),
    ).fetchone()
    conn.close()
    return _feedback_row(row)


def update_feedback_item(feedback_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT * FROM feedback_items WHERE id = ? AND user_id = ?",
        (feedback_id, owner_id),
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("反馈不存在")
    updates = {}
    if "title" in payload:
        title = _clean_text(payload.get("title"))
        if not title:
            conn.close()
            raise ValueError("反馈标题不能为空")
        updates["title"] = title
    if "source" in payload:
        if payload.get("source") not in FEEDBACK_SOURCES:
            conn.close()
            raise ValueError("无效的反馈来源")
        updates["source"] = payload.get("source")
    if "level" in payload:
        if payload.get("level") not in FEEDBACK_LEVELS:
            conn.close()
            raise ValueError("无效的反馈等级")
        updates["level"] = payload.get("level")
    if "related_type" in payload or "related_id" in payload:
        related_type, related_id = _normalize_feedback_relation(
            payload.get("related_type", existing["related_type"]),
            payload.get("related_id", existing["related_id"]),
        )
        updates["related_type"] = related_type
        updates["related_id"] = related_id
        if related_id is not None:
            target_table = {
                "opportunity": "opportunities",
                "experiment": "experiments",
                "project": "projects",
                "asset": "assets",
                "review": "reviews",
            }[related_type]
            if not conn.execute(
                f'SELECT id FROM "{target_table}" WHERE id = ? AND user_id = ?',
                (related_id, owner_id),
            ).fetchone():
                conn.close()
                raise ValueError("反馈关联对象不存在")
    for field in ("content", "evidence", "next_action"):
        if field in payload:
            updates[field] = _clean_text(payload.get(field))
    if not updates:
        conn.close()
        raise ValueError("没有可更新的反馈字段")
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE feedback_items SET {set_clause} WHERE id = ? AND user_id = ?",
        (*updates.values(), feedback_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM feedback_items WHERE id = ? AND user_id = ?",
        (feedback_id, owner_id),
    ).fetchone()
    conn.close()
    return _feedback_row(row)


def delete_feedback_item(feedback_id, user_id):
    return _delete_entity("feedback_items", feedback_id, "反馈", user_id)


def _brief_item(item, fields):
    if not item:
        return None
    return {field: item.get(field) for field in fields if field in item}


def _brief_opportunity(item):
    return _brief_item(
        item,
        ("id", "name", "status", "source", "total_score", "next_action"),
    )


def _brief_experiment(item):
    return _brief_item(
        item,
        (
            "id",
            "opportunity_id",
            "opportunity_name",
            "name",
            "status",
            "experiment_type",
            "next_decision",
        ),
    )


def _brief_feedback(item):
    return _brief_item(
        item,
        (
            "id",
            "related_type",
            "related_id",
            "title",
            "source",
            "level",
            "next_action",
        ),
    )


def _brief_asset(item):
    return _brief_item(
        item,
        (
            "id",
            "title",
            "asset_type",
            "asset_level",
            "source_type",
            "source_id",
            "maturity",
        ),
    )


def _feedback_for_related(related_type, related_id, user_id):
    return [
        item for item in list_feedback_items(user_id)
        if item.get("related_type") == related_type and item.get("related_id") == related_id
    ]


def _assets_for_source(source_type, source_ids, user_id):
    ids = {int(source_id) for source_id in source_ids if source_id is not None}
    if not ids:
        return []
    return [
        item for item in list_assets(user_id)
        if item.get("source_type") == source_type and item.get("source_id") in ids
    ]


def _source_object(source_type, source_id, user_id):
    if source_id in (None, ""):
        return None
    try:
        source_id = int(source_id)
    except (TypeError, ValueError):
        return None
    if source_type == "feedback":
        return _brief_feedback(get_feedback_item(source_id, user_id))
    if source_type == "opportunity":
        return _brief_opportunity(get_opportunity(source_id, user_id))
    if source_type == "experiment":
        return _brief_experiment(get_experiment(source_id, user_id))
    if source_type == "review":
        return _brief_item(
            get_review(source_id, user_id),
            ("id", "review_date", "type", "depositable"),
        )
    return None


def get_opportunity_links(opportunity_id, user_id):
    opportunity = get_opportunity(opportunity_id, user_id)
    if not opportunity:
        raise ValueError("机会不存在")
    experiments = [
        item for item in list_experiments(user_id)
        if item.get("opportunity_id") == opportunity_id
    ]
    experiment_ids = {item["id"] for item in experiments}
    feedback = [
        item for item in list_feedback_items(user_id)
        if (
            item.get("related_type") == "opportunity"
            and item.get("related_id") == opportunity_id
        )
        or (
            item.get("related_type") == "experiment"
            and item.get("related_id") in experiment_ids
        )
    ]
    feedback_ids = {item["id"] for item in feedback}
    assets = [
        item for item in list_assets(user_id)
        if (
            item.get("source_type") == "opportunity"
            and item.get("source_id") == opportunity_id
        )
        or (
            item.get("source_type") == "feedback"
            and item.get("source_id") in feedback_ids
        )
        or (
            item.get("source_type") == "experiment"
            and item.get("source_id") in experiment_ids
        )
    ]
    return {
        "opportunity": _brief_opportunity(opportunity),
        "experiments": [_brief_experiment(item) for item in experiments],
        "feedback": [_brief_feedback(item) for item in feedback],
        "assets": [_brief_asset(item) for item in assets],
        "counts": {
            "experiments": len(experiments),
            "feedback": len(feedback),
            "assets": len(assets),
        },
    }


def get_experiment_links(experiment_id, user_id):
    experiment = get_experiment(experiment_id, user_id)
    if not experiment:
        raise ValueError("实验不存在")
    opportunity = (
        get_opportunity(experiment.get("opportunity_id"), user_id)
        if experiment.get("opportunity_id")
        else None
    )
    feedback = _feedback_for_related("experiment", experiment_id, user_id)
    feedback_ids = {item["id"] for item in feedback}
    assets = [
        item for item in list_assets(user_id)
        if (
            item.get("source_type") == "experiment"
            and item.get("source_id") == experiment_id
        )
        or (
            item.get("source_type") == "feedback"
            and item.get("source_id") in feedback_ids
        )
    ]
    return {
        "experiment": _brief_experiment(experiment),
        "opportunity": _brief_opportunity(opportunity),
        "feedback": [_brief_feedback(item) for item in feedback],
        "assets": [_brief_asset(item) for item in assets],
        "counts": {
            "feedback": len(feedback),
            "assets": len(assets),
        },
    }


def get_feedback_links(feedback_id, user_id):
    feedback = get_feedback_item(feedback_id, user_id)
    if not feedback:
        raise ValueError("反馈不存在")
    related_type = feedback.get("related_type") or ""
    related_id = feedback.get("related_id")
    related = None
    upstream = {}
    if related_type == "opportunity":
        related = _brief_opportunity(get_opportunity(related_id, user_id))
        upstream["opportunity"] = related
    elif related_type == "experiment":
        experiment = get_experiment(related_id, user_id)
        related = _brief_experiment(experiment)
        upstream["experiment"] = related
        if experiment and experiment.get("opportunity_id"):
            upstream["opportunity"] = _brief_opportunity(
                get_opportunity(experiment.get("opportunity_id"), user_id)
            )
    elif related_type == "project":
        related = _brief_item(
            get_project(related_id, user_id),
            ("id", "name", "status", "priority"),
        )
        upstream["project"] = related
    elif related_type == "asset":
        related = _brief_asset(get_asset(related_id, user_id))
        upstream["asset"] = related
    assets = _assets_for_source("feedback", [feedback_id], user_id)
    return {
        "feedback": _brief_feedback(feedback),
        "related_type": related_type,
        "related": related,
        "upstream": upstream,
        "assets": [_brief_asset(item) for item in assets],
        "counts": {"assets": len(assets)},
    }


def get_asset_links(asset_id, user_id):
    asset = get_asset(asset_id, user_id)
    if not asset:
        raise ValueError("资产不存在")
    source_type = asset.get("source_type") or ""
    source_id = asset.get("source_id")
    source = _source_object(source_type, source_id, user_id)
    upstream = {}
    if source_type == "feedback" and source_id:
        feedback = get_feedback_item(source_id, user_id)
        upstream["feedback"] = _brief_feedback(feedback)
        if feedback:
            related_type = feedback.get("related_type") or ""
            related_id = feedback.get("related_id")
            if related_type == "experiment":
                experiment = get_experiment(related_id, user_id)
                upstream["experiment"] = _brief_experiment(experiment)
                if experiment and experiment.get("opportunity_id"):
                    upstream["opportunity"] = _brief_opportunity(
                        get_opportunity(experiment.get("opportunity_id"), user_id)
                    )
            elif related_type == "opportunity":
                upstream["opportunity"] = _brief_opportunity(
                    get_opportunity(related_id, user_id)
                )
    elif source_type == "experiment" and source_id:
        experiment = get_experiment(source_id, user_id)
        upstream["experiment"] = _brief_experiment(experiment)
        if experiment and experiment.get("opportunity_id"):
            upstream["opportunity"] = _brief_opportunity(
                get_opportunity(experiment.get("opportunity_id"), user_id)
            )
    elif source_type == "opportunity" and source_id:
        upstream["opportunity"] = _brief_opportunity(
            get_opportunity(source_id, user_id)
        )
    return {
        "asset": _brief_asset(asset),
        "source_type": source_type,
        "source": source,
        "upstream": upstream,
    }


def _value_chain_sort_key(item):
    if not item:
        return ("", "", 0)
    return (
        item.get("updated_at") or "",
        item.get("created_at") or "",
        int(item.get("id") or 0),
    )


def _latest_value_item(items):
    if not items:
        return None
    return max(items, key=_value_chain_sort_key)


def _chain_opportunity_item(item):
    return {
        "id": item.get("id"),
        "title": item.get("name"),
        "status": item.get("status"),
        "score": item.get("total_score") or 0,
        "next_action": item.get("next_action") or "",
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
    }


def _chain_experiment_item(item):
    if not item:
        return None
    return {
        "id": item.get("id"),
        "title": item.get("name"),
        "status": item.get("status"),
        "experiment_type": item.get("experiment_type"),
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
    }


def _chain_feedback_item(item):
    if not item:
        return None
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "level": item.get("level"),
        "source": item.get("source"),
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
    }


def _chain_asset_item(item):
    if not item:
        return None
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "asset_level": item.get("asset_level"),
        "asset_type": item.get("asset_type"),
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
    }


def _strong_feedback(item):
    level = item.get("level") or ""
    return level.startswith("L4") or level.startswith("L5")


def _case_chain_asset(item):
    return item.get("asset_level") in ("案例", "产品", "筹码")


def _value_chain_stage(opportunity, latest_experiment, feedback, latest_asset):
    experiment_status = (latest_experiment or {}).get("status")
    if opportunity.get("status") == "暂停" or experiment_status in (
        "未验证",
        "暂停",
        "已暂停",
        "停止",
        "已停止",
    ):
        return "待停止观察", "链路已暂停或最新实验未验证，需要判断是否继续投入"
    if latest_asset or opportunity.get("status") == "已转项目":
        return "已完成", "已有案例资产或机会已转项目，可以进入复用或归档"
    has_strong_feedback = any(_strong_feedback(item) for item in feedback)
    if has_strong_feedback:
        return "待沉淀", "已有 L4/L5 强反馈，下一步应沉淀为案例资产"
    if experiment_status == "已验证":
        return "待沉淀", "最新实验已验证，但还没有案例资产"
    if experiment_status in ("设计中", "进行中"):
        return "进行中", "最新实验正在设计或执行"
    if latest_experiment and not feedback:
        return "待反馈", "已有实验，但还没有记录反馈"
    return "待验证", "还没有关联实验，需要启动最小验证"


def _value_chain_next_action(stage, opportunity, latest_experiment, latest_feedback):
    if opportunity.get("next_action"):
        return opportunity.get("next_action")
    if stage == "待验证":
        return "启动 7 天 MVP 或最小实验"
    if stage == "进行中":
        return (latest_experiment or {}).get("next_decision") or "推进实验并记录真实反馈"
    if stage == "待反馈":
        return "记录本轮实验反馈"
    if stage == "待沉淀":
        return (latest_feedback or {}).get("next_action") or "沉淀案例资产"
    if stage == "待停止观察":
        return "复盘停止原因，判断暂停、调整或归档"
    if stage == "已完成":
        return "确认是否归档该链路"
    return "确认下一步"


def _build_value_chains(opportunities, experiments, feedback, assets):
    chains = []
    for opportunity in opportunities:
        if opportunity.get("status") in ("已归档", "删除"):
            continue
        opportunity_id = opportunity.get("id")
        linked_experiments = [
            item for item in experiments
            if item.get("opportunity_id") == opportunity_id
        ]
        experiment_ids = {item.get("id") for item in linked_experiments}
        linked_feedback = [
            item for item in feedback
            if (
                item.get("related_type") == "opportunity"
                and item.get("related_id") == opportunity_id
            )
            or (
                item.get("related_type") == "experiment"
                and item.get("related_id") in experiment_ids
            )
        ]
        feedback_ids = {item.get("id") for item in linked_feedback}
        linked_assets = [
            item for item in assets
            if (
                item.get("source_type") == "opportunity"
                and item.get("source_id") == opportunity_id
            )
            or (
                item.get("source_type") == "experiment"
                and item.get("source_id") in experiment_ids
            )
            or (
                item.get("source_type") == "feedback"
                and item.get("source_id") in feedback_ids
            )
        ]
        latest_experiment = _latest_value_item(linked_experiments)
        latest_feedback = _latest_value_item(linked_feedback)
        case_assets = [item for item in linked_assets if _case_chain_asset(item)]
        latest_asset = _latest_value_item(case_assets)
        stage, stage_reason = _value_chain_stage(
            opportunity, latest_experiment, linked_feedback, latest_asset
        )
        counts = {
            "experiments": len(linked_experiments),
            "feedback": len(linked_feedback),
            "assets": len(linked_assets),
        }
        chains.append({
            "opportunity": _chain_opportunity_item(opportunity),
            "latest_experiment": _chain_experiment_item(latest_experiment),
            "latest_feedback": _chain_feedback_item(latest_feedback),
            "latest_asset": _chain_asset_item(latest_asset),
            "stage": stage,
            "stage_reason": stage_reason,
            "next_action": _value_chain_next_action(
                stage, opportunity, latest_experiment, latest_feedback
            ),
            "counts": counts,
            "has_more": any(count > 1 for count in counts.values()),
            "links_url": f"/api/opportunities/{opportunity_id}/links",
        })
    return sorted(
        chains,
        key=lambda item: _value_chain_sort_key(item.get("opportunity")),
        reverse=True,
    )


def get_value_dashboard(user_id):
    opportunities = [
        item for item in list_opportunities(user_id)
        if item.get("status") != "删除"
    ]
    experiments = list_experiments(user_id)
    feedback = list_feedback_items(user_id)
    assets = list_assets(user_id)
    projects = list_projects(user_id)
    experiment_opportunity_ids = {
        item.get("opportunity_id") for item in experiments if item.get("opportunity_id")
    }
    feedback_ids_with_assets = {
        item.get("source_id") for item in assets
        if item.get("source_type") == "feedback" and item.get("source_id")
    }
    feedback_experiment_ids = {
        item.get("related_id") for item in feedback
        if item.get("related_type") == "experiment" and item.get("related_id")
    }
    experiment_ids_with_case_assets = {
        item.get("source_id") for item in assets
        if item.get("source_type") == "experiment" and item.get("source_id")
    }
    experiment_ids_with_feedback_assets = {
        item.get("related_id") for item in feedback
        if item.get("id") in feedback_ids_with_assets
        and item.get("related_type") == "experiment"
        and item.get("related_id")
    }
    return {
        "chains": _build_value_chains(opportunities, experiments, feedback, assets),
        "high_score_opportunities": opportunities[:5],
        "running_experiments": [
            item for item in experiments if item.get("status") in ("设计中", "进行中")
        ][:5],
        "strong_feedback": [
            item for item in feedback
            if (item.get("level") or "").startswith("L4")
            or (item.get("level") or "").startswith("L5")
        ][:5],
        "case_assets": [
            item for item in assets
            if item.get("asset_level") in ("案例", "产品", "筹码")
        ][:5],
        "pending_validation": [
            item for item in opportunities
            if item.get("status") == "值得测试"
            or (
                int(item.get("total_score") or 0) >= 15
                and item.get("id") not in experiment_opportunity_ids
            )
        ][:5],
        "pending_deposit": [
            item for item in feedback
            if (
                (item.get("level") or "").startswith("L4")
                or (item.get("level") or "").startswith("L5")
            )
            and item.get("id") not in feedback_ids_with_assets
        ][:5],
        "completed_experiments_without_assets": [
            item for item in experiments
            if item.get("status") == "已验证"
            and item.get("id") not in experiment_ids_with_case_assets
            and item.get("id") not in experiment_ids_with_feedback_assets
        ][:5],
        "pending_stop_review": [
            item for item in opportunities
            if item.get("status") in ("暂停", "观察", "停止")
        ][:5]
        + [
            item for item in experiments
            if item.get("status") in ("已暂停", "未验证", "暂停", "停止")
            or (
                item.get("failure_criteria")
                and item.get("status") in ("设计中", "进行中")
            )
        ][:5]
        + [
            item for item in projects if item.get("stop_condition")
        ][:5],
    }


class InboxError(Exception):
    pass


def _parse_suggested_payload(raw):
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _suggestion_row(row):
    data = _row_to_dict(row)
    if data:
        data["suggested_payload"] = _parse_suggested_payload(
            data.get("suggested_payload")
        )
    return data


def create_inbox_entry(raw_text, source_type="manual", *, user_id):
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("输入文本不能为空")
    if source_type not in ("manual",):
        raise ValueError("无效的 source_type")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    cur = conn.execute(
        """
        INSERT INTO inbox_entries (
            user_id, raw_text, source_type, status, created_at
        ) VALUES (?, ?, ?, 'draft', ?)
        """,
        (owner_id, text, source_type, _now()),
    )
    conn.commit()
    entry_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM inbox_entries WHERE id = ? AND user_id = ?",
        (entry_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def update_inbox_entry_status(entry_id, status, user_id):
    if status not in INBOX_ENTRY_STATUSES:
        raise ValueError("无效的 inbox 状态")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT id FROM inbox_entries WHERE id = ? AND user_id = ?",
        (entry_id, owner_id),
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("inbox 记录不存在")

    conn.execute(
        "UPDATE inbox_entries SET status = ? WHERE id = ? AND user_id = ?",
        (status, entry_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM inbox_entries WHERE id = ? AND user_id = ?",
        (entry_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def get_inbox_entry(entry_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM inbox_entries WHERE id = ? AND user_id = ?",
        (entry_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_inbox_entries(user_id, limit=20):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT
            e.id,
            e.raw_text,
            e.source_type,
            e.status,
            e.created_at,
            COUNT(s.id) AS suggestion_count,
            COALESCE(SUM(CASE WHEN s.status = 'committed' THEN 1 ELSE 0 END), 0)
                AS committed_count,
            COALESCE(SUM(CASE WHEN s.status = 'pending' THEN 1 ELSE 0 END), 0)
                AS pending_count,
            COALESCE(SUM(CASE WHEN s.status = 'rejected' THEN 1 ELSE 0 END), 0)
                AS rejected_count
        FROM inbox_entries e
        LEFT JOIN inbox_suggestions s
          ON s.inbox_entry_id = e.id AND s.user_id = e.user_id
        WHERE e.user_id = ?
        GROUP BY e.id
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT ?
        """,
        (owner_id, limit),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = _row_to_dict(row)
        raw = item.get("raw_text") or ""
        item["raw_text_summary"] = raw[:120] + ("…" if len(raw) > 120 else "")
        result.append(item)
    return result


def create_inbox_suggestions(entry_id, items, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    entry = conn.execute(
        "SELECT id FROM inbox_entries WHERE id = ? AND user_id = ?",
        (entry_id, owner_id),
    ).fetchone()
    if not entry:
        conn.close()
        raise ValueError("inbox 记录不存在")
    created = []
    try:
        for item in items:
            target_type = item.get("target_type", "uncertain")
            if target_type not in INBOX_TARGET_TYPES:
                target_type = "uncertain"
            title = (item.get("title") or "").strip() or "未命名条目"
            content = (item.get("content") or "").strip()
            confidence = float(item.get("confidence", 0) or 0)
            confidence = max(0.0, min(1.0, confidence))
            reason = (item.get("reason") or "").strip()
            payload = item.get("suggested_payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            else:
                payload = dict(payload)
                payload.pop("user_id", None)
            cur = conn.execute(
                """
                INSERT INTO inbox_suggestions (
                    user_id, inbox_entry_id, target_type, title, content,
                    confidence, reason, suggested_payload, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    owner_id,
                    entry_id,
                    target_type,
                    title,
                    content,
                    confidence,
                    reason,
                    json.dumps(payload, ensure_ascii=False),
                    _now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM inbox_suggestions WHERE id = ? AND user_id = ?",
                (cur.lastrowid, owner_id),
            ).fetchone()
            created.append(_suggestion_row(row))
        conn.commit()
        return created
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_inbox_suggestions(entry_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM inbox_suggestions
        WHERE inbox_entry_id = ? AND user_id = ?
        ORDER BY id ASC
        """,
        (entry_id, owner_id),
    ).fetchall()
    conn.close()
    return [_suggestion_row(r) for r in rows]


def get_inbox_suggestion(suggestion_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM inbox_suggestions WHERE id = ? AND user_id = ?",
        (suggestion_id, owner_id),
    ).fetchone()
    conn.close()
    return _suggestion_row(row)


def reject_inbox_suggestion(suggestion_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM inbox_suggestions WHERE id = ? AND user_id = ?",
        (suggestion_id, owner_id),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("建议不存在")
    if row["status"] == "committed":
        conn.close()
        raise ValueError("已入库的建议无法拒绝")

    conn.execute(
        """
        UPDATE inbox_suggestions SET status = 'rejected'
        WHERE id = ? AND user_id = ?
        """,
        (suggestion_id, owner_id),
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM inbox_suggestions WHERE id = ? AND user_id = ?",
        (suggestion_id, owner_id),
    ).fetchone()
    conn.close()
    return _suggestion_row(updated)


def _map_goal_type(raw):
    if raw in GOAL_TYPES:
        return raw
    mapping = {
        "personal": "季度",
        "annual": "年度",
        "yearly": "年度",
        "quarterly": "季度",
        "monthly": "月度",
    }
    return mapping.get((raw or "").lower(), "季度")


def _map_task_status(raw):
    if raw in TASK_STATUSES:
        return raw
    mapping = {
        "todo": "待处理",
        "pending": "待处理",
        "doing": "进行中",
        "in_progress": "进行中",
        "done": "完成",
        "completed": "完成",
    }
    return mapping.get((raw or "").lower(), "待处理")


def _map_review_type(raw):
    if raw in REVIEW_TYPES:
        return raw
    mapping = {"inbox": "事件", "daily": "每日", "weekly": "每周"}
    return mapping.get((raw or "").lower(), "每日")


def _coerce_positive_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _normalize_asset_type_for_inbox(value, title="", content=""):
    raw = _as_text(value)
    alias = ASSET_TYPE_ALIASES.get(raw.lower())
    if alias:
        return alias
    return asset_schemas.normalize_asset_type(raw, title, content)


def _map_asset_maturity(raw, default="可用"):
    value = _as_text(raw)
    if value in MATURITY_LEVELS:
        return value
    return MATURITY_ALIASES.get(value.lower(), default)


def _map_opportunity_status(raw):
    value = _as_text(raw)
    return value if value in OPPORTUNITY_STATUSES else "待审计"


def _map_experiment_type(raw):
    value = _as_text(raw)
    return value if value in EXPERIMENT_TYPES else "结果型MVP"


def _map_experiment_status(raw):
    value = _as_text(raw)
    return value if value in EXPERIMENT_STATUSES else "设计中"


def _map_feedback_source(raw):
    value = _as_text(raw)
    return value if value in FEEDBACK_SOURCES else "自我判断"


def _map_feedback_level(raw):
    value = _as_text(raw)
    return value if value in FEEDBACK_LEVELS else "L0 只是想法"


def _clean_asset_fields_for_type(asset_type, raw_fields):
    fields = asset_schemas.parse_fields(raw_fields)
    if not fields:
        return {}
    allowed = {key for key, _ in asset_schemas.get_field_defs(asset_type)}
    return {
        key: _as_text(value)
        for key, value in fields.items()
        if key in allowed and _as_text(value)
    }


def _parse_override_payloads(override_list):
    result = {}
    if not override_list:
        return result
    for item in override_list:
        if not isinstance(item, dict):
            continue
        sid = item.get("suggestion_id")
        if sid is None:
            continue
        allowed = {}
        for key in INBOX_OVERRIDE_FIELDS:
            if key in item:
                allowed[key] = item[key]
        if allowed:
            result[int(sid)] = allowed
    return result


def _merge_suggestion_override(suggestion, override_map):
    sid = suggestion["id"]
    if sid not in override_map:
        return suggestion
    payload = dict(suggestion["suggested_payload"])
    merged = dict(suggestion)
    for key, value in override_map[sid].items():
        if key == "target_type":
            if value in INBOX_TARGET_TYPES:
                merged["target_type"] = value
        elif key in INBOX_OVERRIDE_FIELDS:
            payload[key] = value
    merged["suggested_payload"] = payload
    return merged


def _batch_project_local_refs(suggestions):
    refs = set()
    for suggestion in suggestions:
        if suggestion["target_type"] != "project":
            continue
        ref = (suggestion["suggested_payload"].get("local_ref") or "").strip()
        if ref:
            refs.add(ref)
    return refs


def _sort_suggestions_for_commit(suggestions):
    return sorted(
        suggestions,
        key=lambda item: (INBOX_COMMIT_ORDER.get(item["target_type"], 99), item["id"]),
    )


def _resolve_task_project_id(payload, ref_map):
    project_id = _coerce_positive_int(payload.get("project_id"))
    if project_id:
        return project_id
    parent_ref = (payload.get("parent_ref") or "").strip()
    if parent_ref and parent_ref in ref_map:
        return ref_map[parent_ref]
    return None


def _validate_suggestion_for_commit(
    conn, suggestion, user_id, batch_project_refs=None
):
    batch_project_refs = batch_project_refs or set()
    sid = suggestion["id"]
    target_type = suggestion["target_type"]
    title = suggestion.get("title") or ""
    content = suggestion.get("content") or ""
    payload = suggestion["suggested_payload"]
    owner_id = int(user_id)
    if int(suggestion["user_id"]) != owner_id:
        return f"建议 #{sid} 不存在"

    if target_type == "goal":
        name = (payload.get("name") or title).strip()
        if not name:
            return f"建议 #{sid}（目标）：缺少名称"
        return None

    if target_type == "project":
        name = (payload.get("name") or title).strip()
        goal_id = _coerce_positive_int(payload.get("goal_id"))
        if not name:
            return f"建议 #{sid}（项目）：缺少名称"
        if not goal_id:
            return (
                f"建议 #{sid}（项目「{name}」）：缺少有效 goal_id，"
                "请先在目标模块创建目标后再归档项目"
            )
        if not conn.execute(
            "SELECT id FROM goals WHERE id = ? AND user_id = ?",
            (goal_id, owner_id),
        ).fetchone():
            return f"建议 #{sid}（项目）：关联目标 #{goal_id} 不存在"
        return None

    if target_type == "task":
        name = (payload.get("name") or title).strip()
        project_id = _coerce_positive_int(payload.get("project_id"))
        parent_ref = (payload.get("parent_ref") or "").strip()
        if not name:
            return f"建议 #{sid}（任务）：缺少名称"
        if not project_id and parent_ref and parent_ref in batch_project_refs:
            return None
        if not project_id:
            raw = payload.get("project_id")
            if isinstance(raw, str) and raw.strip():
                return (
                    f"建议 #{sid}（任务「{name}」）：project_id 需为已存在项目的数字 ID，"
                    f"不能是项目名称（当前：{raw}）"
                )
            if parent_ref:
                return (
                    f"建议 #{sid}（任务「{name}」）：parent_ref「{parent_ref}」"
                    "未匹配到同批项目，请选择归属项目或勾选对应项目建议"
                )
            return (
                f"建议 #{sid}（任务「{name}」）：缺少有效 project_id，"
                "请选择归属项目或关联同批项目"
            )
        if not conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, owner_id),
        ).fetchone():
            return f"建议 #{sid}（任务）：关联项目 #{project_id} 不存在"
        return None

    if target_type == "review":
        review_date = _as_text(payload.get("review_date"), _today_local())
        what_done = _as_text(payload.get("what_done"), _as_text(content, _as_text(title)))
        if not review_date:
            return f"建议 #{sid}（复盘）：缺少复盘日期"
        if not what_done:
            return f"建议 #{sid}（复盘）：缺少复盘内容"
        return None

    if target_type == "asset":
        asset_title = (payload.get("title") or title).strip()
        asset_type = _normalize_asset_type_for_inbox(
            payload.get("asset_type") or "通用资产", asset_title, content
        )
        fields = _clean_asset_fields_for_type(asset_type, payload.get("fields"))
        if not fields:
            fields = asset_schemas.build_fields_from_legacy(
                asset_type,
                payload.get("trigger_context") or "",
                payload.get("core_content") or content,
            )
        if not asset_title or not asset_schemas.asset_content_valid(asset_type, fields, content):
            return f"建议 #{sid}（资产）：需要标题与内容"
        source_review_id = _coerce_positive_int(payload.get("source_review_id"))
        if payload.get("source_review_id") not in (None, "") and not source_review_id:
            return f"建议 #{sid}（资产）：source_review_id 需为数字 ID"
        if source_review_id and not conn.execute(
            "SELECT id FROM reviews WHERE id = ? AND user_id = ?",
            (source_review_id, owner_id),
        ).fetchone():
            return f"建议 #{sid}（资产）：来源复盘不存在"
        return None

    if target_type == "capability_entry":
        entry_content = (payload.get("content") or content).strip()
        if not entry_content:
            return f"建议 #{sid}（能力记录）：缺少内容"
        return None

    if target_type == "opportunity":
        name = _as_text(payload.get("name"), _as_text(title))
        if not name:
            return f"建议 #{sid}（机会）：缺少名称"
        return None

    if target_type == "experiment":
        name = _as_text(payload.get("name"), _as_text(title))
        opportunity_id = _coerce_positive_int(payload.get("opportunity_id"))
        if not name:
            return f"建议 #{sid}（实验）：缺少名称"
        if payload.get("opportunity_id") not in (None, "") and not opportunity_id:
            return f"建议 #{sid}（实验）：opportunity_id 需为数字 ID"
        if opportunity_id and not conn.execute(
            "SELECT id FROM opportunities WHERE id = ? AND user_id = ?",
            (opportunity_id, owner_id),
        ).fetchone():
            return f"建议 #{sid}（实验）：关联机会 #{opportunity_id} 不存在"
        return None

    if target_type == "feedback":
        feedback_title = _as_text(payload.get("title"), _as_text(title))
        related_type = _as_text(payload.get("related_type"))
        related_id = _coerce_positive_int(payload.get("related_id"))
        if not feedback_title:
            return f"建议 #{sid}（反馈）：缺少标题"
        if related_type and related_type not in FEEDBACK_RELATED_TYPES:
            return f"建议 #{sid}（反馈）：关联类型无效"
        if payload.get("related_id") not in (None, "") and not related_id:
            return f"建议 #{sid}（反馈）：related_id 需为数字 ID"
        if related_type and related_id:
            target_table = {
                "opportunity": "opportunities",
                "experiment": "experiments",
                "project": "projects",
                "asset": "assets",
                "review": "reviews",
            }[related_type]
            if not conn.execute(
                f'SELECT id FROM "{target_table}" WHERE id = ? AND user_id = ?',
                (related_id, owner_id),
            ).fetchone():
                return f"建议 #{sid}（反馈）：关联对象不存在或属于其他用户"
        return None

    return f"建议 #{sid} 类型为 {target_type}，不可入库"


def _commit_suggestion_in_tx(conn, suggestion, user_id, ref_map=None):
    ref_map = ref_map or {}
    target_type = suggestion["target_type"]
    title = suggestion["title"]
    content = suggestion["content"]
    payload = dict(suggestion["suggested_payload"])
    owner_id = int(user_id)
    if int(suggestion["user_id"]) != owner_id:
        raise ValueError("建议不存在")

    if target_type == "goal":
        name = (payload.get("name") or title).strip()
        if not name:
            raise ValueError("目标名称不能为空")
        goal_type = _map_goal_type(payload.get("type"))
        cur = conn.execute(
            """
            INSERT INTO goals (user_id, name, type, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (owner_id, name, goal_type, _now()),
        )
        if goal_type == "当前主线":
            _demote_other_mainline_goals(conn, cur.lastrowid, owner_id)
        return "goals", cur.lastrowid

    if target_type == "project":
        name = (payload.get("name") or title).strip()
        goal_id = _coerce_positive_int(payload.get("goal_id"))
        if not name:
            raise ValueError("项目名称不能为空")
        if not goal_id:
            raise ValueError("项目归档需要关联目标 goal_id")
        goal = conn.execute(
            "SELECT id FROM goals WHERE id = ? AND user_id = ?",
            (goal_id, owner_id),
        ).fetchone()
        if not goal:
            raise ValueError("关联目标不存在")
        cur = conn.execute(
            """
            INSERT INTO projects (user_id, goal_id, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (owner_id, goal_id, name, _now()),
        )
        return "projects", cur.lastrowid

    if target_type == "task":
        name = (payload.get("name") or title).strip()
        project_id = _resolve_task_project_id(payload, ref_map)
        status = _map_task_status(payload.get("status"))
        if not name:
            raise ValueError("任务名称不能为空")
        if not project_id:
            raise ValueError("任务归档需要关联项目 project_id")
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, owner_id),
        ).fetchone()
        if not project:
            raise ValueError("关联项目不存在")
        cur = conn.execute(
            """
            INSERT INTO tasks (user_id, project_id, name, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (owner_id, project_id, name, status, _now()),
        )
        return "tasks", cur.lastrowid

    if target_type == "review":
        review_date = _as_text(payload.get("review_date"), _today_local())
        review_type = _map_review_type(payload.get("type"))
        what_done = _as_text(payload.get("what_done"), _as_text(content, _as_text(title)))
        if not review_date:
            raise ValueError("复盘日期不能为空")
        cur = conn.execute(
            """
            INSERT INTO reviews (
                user_id, review_date, type, what_done, stuck, next_adjust,
                depositable, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                review_date,
                review_type,
                what_done,
                _as_text(payload.get("stuck")),
                _as_text(payload.get("next_adjust")),
                _as_text(payload.get("depositable"), _as_text(content)),
                _now(),
            ),
        )
        return "reviews", cur.lastrowid

    if target_type == "asset":
        asset_title = (payload.get("title") or title).strip()
        asset_type = _normalize_asset_type_for_inbox(
            payload.get("asset_type") or "通用资产", asset_title, content
        )
        parsed_fields = _clean_asset_fields_for_type(asset_type, payload.get("fields"))
        if not parsed_fields:
            parsed_fields = asset_schemas.build_fields_from_legacy(
                asset_type,
                payload.get("trigger_context") or "",
                payload.get("core_content") or content,
            )
        if not asset_title or not asset_schemas.asset_content_valid(
            asset_type, parsed_fields, content
        ):
            raise ValueError("资产需要标题与内容")
        legacy_trigger, legacy_core = asset_schemas.sync_legacy_columns(
            asset_type, parsed_fields
        )
        if not legacy_trigger and payload.get("trigger_context"):
            legacy_trigger = _as_text(payload.get("trigger_context"))
        if not legacy_core and payload.get("core_content"):
            legacy_core = _as_text(payload.get("core_content"))
        summary = _as_text(payload.get("summary")) or asset_schemas.extract_summary(
            parsed_fields, legacy_core
        )
        reusable = _as_text(payload.get("reusable_scenario")) or asset_schemas.extract_reusable_scenario(
            asset_type, parsed_fields
        )
        maturity = _map_asset_maturity(payload.get("maturity"), default="可用")
        tags = payload.get("capability_tags") or []
        if not isinstance(tags, list):
            tags = []
        tags = [t for t in tags if t in CAPABILITY_MODULES]
        source_review_id = payload.get("source_review_id")
        source_type = "review" if source_review_id else ""
        now = _now()
        cur = conn.execute(
            """
            INSERT INTO assets (
                user_id, title, trigger_context, core_content, asset_type,
                capability_tags, source_review_id, created_at,
                summary, fields, reusable_scenario, maturity, reuse_count,
                source_type, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                asset_title,
                legacy_trigger,
                legacy_core,
                asset_type,
                json.dumps(tags, ensure_ascii=False),
                source_review_id,
                now,
                summary,
                asset_schemas.serialize_fields(parsed_fields),
                reusable,
                maturity,
                0,
                source_type,
                now,
            ),
        )
        return "assets", cur.lastrowid

    if target_type == "capability_entry":
        module = payload.get("capability") or payload.get("module") or "AI驾驭力"
        if module not in CAPABILITY_MODULES:
            module = "AI驾驭力"
        entry_content = (payload.get("content") or content).strip()
        entry_date = (payload.get("entry_date") or _today_local()).strip()
        level_type = payload.get("level_type") or "能力层"
        if level_type not in LEVEL_TYPES:
            level_type = "能力层"
        if not entry_content:
            raise ValueError("能力记录内容不能为空")
        cur = conn.execute(
            """
            INSERT INTO capability_entries (
                user_id, module, entry_date, content, source_project,
                level_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                module,
                entry_date,
                entry_content,
                (payload.get("source_project") or "").strip(),
                level_type,
                _now(),
            ),
        )
        return "capability_entries", cur.lastrowid

    if target_type == "opportunity":
        now = _now()
        name = _as_text(payload.get("name"), _as_text(title))
        if not name:
            raise ValueError("机会名称不能为空")
        cur = conn.execute(
            """
            INSERT INTO opportunities (
                user_id, name, source, description, related_context, target_user,
                status, next_action, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                name,
                _as_text(payload.get("source")),
                _as_text(payload.get("description"), _as_text(content)),
                _as_text(payload.get("related_context")),
                _as_text(payload.get("target_user")),
                _map_opportunity_status(payload.get("status")),
                _as_text(payload.get("next_action")),
                now,
                now,
            ),
        )
        return "opportunities", cur.lastrowid

    if target_type == "experiment":
        now = _now()
        name = _as_text(payload.get("name"), _as_text(title))
        opportunity_id = _coerce_positive_int(payload.get("opportunity_id"))
        if not name:
            raise ValueError("实验名称不能为空")
        cur = conn.execute(
            """
            INSERT INTO experiments (
                user_id, opportunity_id, name, hypothesis, experiment_type,
                minimum_action, test_target, feedback_source,
                validation_period, success_criteria, failure_criteria,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                opportunity_id,
                name,
                _as_text(payload.get("hypothesis"), _as_text(content)),
                _map_experiment_type(payload.get("experiment_type")),
                _as_text(payload.get("minimum_action")),
                _as_text(payload.get("test_target")),
                _as_text(payload.get("feedback_source")),
                _as_text(payload.get("validation_period")),
                _as_text(payload.get("success_criteria")),
                _as_text(payload.get("failure_criteria")),
                _map_experiment_status(payload.get("status")),
                now,
                now,
            ),
        )
        return "experiments", cur.lastrowid

    if target_type == "feedback":
        now = _now()
        feedback_title = _as_text(payload.get("title"), _as_text(title))
        if not feedback_title:
            raise ValueError("反馈标题不能为空")
        related_type = _as_text(payload.get("related_type"))
        related_id = _coerce_positive_int(payload.get("related_id"))
        if related_type not in FEEDBACK_RELATED_TYPES:
            related_type = ""
            related_id = None
        cur = conn.execute(
            """
            INSERT INTO feedback_items (
                user_id, related_type, related_id, title, source, level,
                content, evidence, next_action, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                related_type,
                related_id,
                feedback_title,
                _map_feedback_source(payload.get("source")),
                _map_feedback_level(payload.get("level")),
                _as_text(payload.get("content"), _as_text(content)),
                _as_text(payload.get("evidence")),
                _as_text(payload.get("next_action")),
                now,
                now,
            ),
        )
        return "feedback_items", cur.lastrowid

    raise ValueError(f"类型 {target_type} 不可入库")


def commit_inbox_suggestions(suggestion_ids, user_id, override_payload=None):
    if not suggestion_ids:
        raise ValueError("未选择任何建议")

    unique_ids = []
    seen = set()
    for raw_id in suggestion_ids:
        sid = int(raw_id)
        if sid in seen:
            continue
        seen.add(sid)
        unique_ids.append(sid)

    created = {
        "goals": 0,
        "projects": 0,
        "tasks": 0,
        "reviews": 0,
        "assets": 0,
        "capability_entries": 0,
        "opportunities": 0,
        "experiments": 0,
        "feedback_items": 0,
    }
    skipped = 0
    errors = []

    override_map = _parse_override_payloads(override_payload)
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    candidates = []
    try:
        for suggestion_id in unique_ids:
            row = conn.execute(
                "SELECT * FROM inbox_suggestions WHERE id = ? AND user_id = ?",
                (suggestion_id, owner_id),
            ).fetchone()
            if not row:
                errors.append(f"建议 #{suggestion_id} 不存在")
                continue
            suggestion = _merge_suggestion_override(_suggestion_row(row), override_map)
            if suggestion["status"] == "committed":
                skipped += 1
                continue
            if suggestion["status"] != "pending":
                errors.append(f"建议 #{suggestion_id} 已处理，无法提交")
                continue
            if suggestion["target_type"] not in INBOX_COMMITTABLE_TYPES:
                errors.append(
                    f"建议 #{suggestion_id} 类型为 {suggestion['target_type']}，不可入库"
                )
                continue
            candidates.append(suggestion)

        batch_project_refs = _batch_project_local_refs(candidates)
        to_commit = []
        for suggestion in candidates:
            validation_error = _validate_suggestion_for_commit(
                conn, suggestion, owner_id, batch_project_refs
            )
            if validation_error:
                errors.append(validation_error)
                continue
            to_commit.append(suggestion)

        if not to_commit:
            return {"created": created, "skipped": skipped, "errors": errors}

        conn.execute("BEGIN")
        entry_ids = set()
        ref_map = {}
        for suggestion in _sort_suggestions_for_commit(to_commit):
            table_key, entity_id = _commit_suggestion_in_tx(
                conn, suggestion, owner_id, ref_map
            )
            created[table_key] += 1
            payload = suggestion["suggested_payload"]
            if suggestion["target_type"] == "project":
                local_ref = (payload.get("local_ref") or "").strip()
                if local_ref:
                    ref_map[local_ref] = entity_id
            conn.execute(
                """
                UPDATE inbox_suggestions SET status = 'committed'
                WHERE id = ? AND user_id = ?
                """,
                (suggestion["id"], owner_id),
            )
            entry_ids.add(suggestion["inbox_entry_id"])

        for entry_id in entry_ids:
            pending = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM inbox_suggestions
                WHERE inbox_entry_id = ? AND user_id = ? AND status = 'pending'
                """,
                (entry_id, owner_id),
            ).fetchone()["cnt"]
            if pending == 0:
                conn.execute(
                    """
                    UPDATE inbox_entries SET status = 'committed'
                    WHERE id = ? AND user_id = ?
                    """,
                    (entry_id, owner_id),
                )

        conn.commit()
        return {"created": created, "skipped": skipped, "errors": errors}
    except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
        conn.rollback()
        message = str(exc) or "归档失败"
        errors.append(message)
        raise InboxError(message, {"created": created, "skipped": skipped, "errors": errors}) from exc
    except sqlite3.Error as exc:
        conn.rollback()
        message = "数据库写入失败，已回滚"
        errors.append(message)
        raise InboxError(message, {"created": created, "skipped": skipped, "errors": errors}) from exc
    finally:
        conn.close()


class PositioningError(Exception):
    pass


def _parse_positioning_payload(raw):
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _positioning_action_row(row):
    data = _row_to_dict(row)
    if data:
        data["payload"] = _parse_positioning_payload(data.get("payload"))
    return data


def get_positioning_anchor(user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM positioning_anchor WHERE user_id = ? LIMIT 1",
        (owner_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def upsert_positioning_anchor(payload, user_id):
    payload = payload or {}
    field_names = (
        "first_principle",
        "identity_core",
        "flywheel_def",
        "current_stage",
        "north_star",
    )
    now = _now()
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT * FROM positioning_anchor WHERE user_id = ? LIMIT 1",
        (owner_id,),
    ).fetchone()
    if existing:
        fields = {}
        for name in field_names:
            if name in payload:
                fields[name] = _as_text(payload.get(name))
            else:
                fields[name] = existing[name] or ""
        conn.execute(
            """
            UPDATE positioning_anchor
            SET first_principle = ?, identity_core = ?, flywheel_def = ?,
                current_stage = ?, north_star = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                fields["first_principle"],
                fields["identity_core"],
                fields["flywheel_def"],
                fields["current_stage"],
                fields["north_star"],
                now,
                existing["id"],
                owner_id,
            ),
        )
        anchor_id = existing["id"]
    else:
        fields = {name: _as_text(payload.get(name)) for name in field_names}
        cur = conn.execute(
            """
            INSERT INTO positioning_anchor (
                user_id, first_principle, identity_core, flywheel_def,
                current_stage, north_star, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                fields["first_principle"],
                fields["identity_core"],
                fields["flywheel_def"],
                fields["current_stage"],
                fields["north_star"],
                now,
            ),
        )
        anchor_id = cur.lastrowid
    conn.commit()
    row = conn.execute(
        "SELECT * FROM positioning_anchor WHERE id = ? AND user_id = ?",
        (anchor_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def create_positioning_calibration(payload, user_id):
    payload = payload or {}
    calibrated_at = _as_text(payload.get("calibrated_at"))
    if not calibrated_at:
        raise ValueError("校准日期不能为空")
    cycle = _as_text(payload.get("cycle"), "触发式")
    if cycle not in POSITIONING_CYCLES:
        raise ValueError("无效的校准周期")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    cur = conn.execute(
        """
        INSERT INTO positioning_calibration (
            user_id, calibrated_at, cycle, primary_contradiction,
            doing_but_shouldnt, should_but_not_doing,
            alignment_review, conclusion, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_id,
            calibrated_at,
            cycle,
            _as_text(payload.get("primary_contradiction")),
            _as_text(payload.get("doing_but_shouldnt")),
            _as_text(payload.get("should_but_not_doing")),
            _as_text(payload.get("alignment_review")),
            _as_text(payload.get("conclusion")),
            _now(),
        ),
    )
    conn.commit()
    calibration_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM positioning_calibration WHERE id = ? AND user_id = ?",
        (calibration_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def update_positioning_calibration(calibration_id, payload, user_id):
    payload = payload or {}
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    existing = conn.execute(
        "SELECT * FROM positioning_calibration WHERE id = ? AND user_id = ?",
        (calibration_id, owner_id),
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("校准记录不存在")

    calibrated_at = (
        _as_text(payload.get("calibrated_at"))
        if "calibrated_at" in payload
        else existing["calibrated_at"]
    )
    if not calibrated_at:
        conn.close()
        raise ValueError("校准日期不能为空")

    cycle = (
        _as_text(payload.get("cycle"), existing["cycle"])
        if "cycle" in payload
        else existing["cycle"]
    )
    if cycle not in POSITIONING_CYCLES:
        conn.close()
        raise ValueError("无效的校准周期")

    conn.execute(
        """
        UPDATE positioning_calibration
        SET calibrated_at = ?, cycle = ?, primary_contradiction = ?,
            doing_but_shouldnt = ?, should_but_not_doing = ?,
            alignment_review = ?, conclusion = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            calibrated_at,
            cycle,
            _as_text(payload.get("primary_contradiction"))
            if "primary_contradiction" in payload
            else existing["primary_contradiction"],
            _as_text(payload.get("doing_but_shouldnt"))
            if "doing_but_shouldnt" in payload
            else existing["doing_but_shouldnt"],
            _as_text(payload.get("should_but_not_doing"))
            if "should_but_not_doing" in payload
            else existing["should_but_not_doing"],
            _as_text(payload.get("alignment_review"))
            if "alignment_review" in payload
            else existing["alignment_review"],
            _as_text(payload.get("conclusion"))
            if "conclusion" in payload
            else existing["conclusion"],
            calibration_id,
            owner_id,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM positioning_calibration WHERE id = ? AND user_id = ?",
        (calibration_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def delete_positioning_calibration(calibration_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT id FROM positioning_calibration WHERE id = ? AND user_id = ?",
        (calibration_id, owner_id),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("校准记录不存在")
    conn.execute(
        "DELETE FROM positioning_calibration WHERE id = ? AND user_id = ?",
        (calibration_id, owner_id),
    )
    conn.commit()
    conn.close()
    return True


def list_positioning_calibrations(user_id, limit=50):
    limit = max(1, min(int(limit or 50), 100))
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM positioning_calibration
        WHERE user_id = ?
        ORDER BY calibrated_at DESC, id DESC
        LIMIT ?
        """,
        (owner_id, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_positioning_calibration(calibration_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM positioning_calibration WHERE id = ? AND user_id = ?",
        (calibration_id, owner_id),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_positioning_goal_actions(calibration_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    rows = conn.execute(
        """
        SELECT * FROM positioning_goal_action
        WHERE calibration_id = ? AND user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (calibration_id, owner_id),
    ).fetchall()
    conn.close()
    return [_positioning_action_row(r) for r in rows]


def get_positioning_goal_action(action_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT * FROM positioning_goal_action WHERE id = ? AND user_id = ?",
        (action_id, owner_id),
    ).fetchone()
    conn.close()
    return _positioning_action_row(row)


def update_positioning_goal_action(action_id, payload, user_id):
    payload = payload or {}
    existing = get_positioning_goal_action(action_id, user_id)
    if not existing:
        raise ValueError("变更记录不存在")

    action_type = _as_text(payload.get("action_type")) or existing["action_type"]
    target_goal_id, action_payload = _validate_positioning_goal_action_fields(
        action_type,
        payload.get("target_goal_id")
        if "target_goal_id" in payload
        else existing.get("target_goal_id"),
        payload.get("payload")
        if "payload" in payload
        else existing.get("payload"),
        user_id,
    )

    reason = (
        _as_text(payload.get("reason"))
        if "reason" in payload
        else existing.get("reason") or ""
    )
    if not reason:
        raise ValueError("变更理由不能为空")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    conn.execute(
        """
        UPDATE positioning_goal_action
        SET action_type = ?, target_goal_id = ?, payload = ?, reason = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            action_type,
            target_goal_id,
            json.dumps(action_payload, ensure_ascii=False),
            reason,
            action_id,
            owner_id,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM positioning_goal_action WHERE id = ? AND user_id = ?",
        (action_id, owner_id),
    ).fetchone()
    conn.close()
    return _positioning_action_row(row)


def delete_positioning_goal_action(action_id, user_id):
    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT id FROM positioning_goal_action WHERE id = ? AND user_id = ?",
        (action_id, owner_id),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("变更记录不存在")
    conn.execute(
        "DELETE FROM positioning_goal_action WHERE id = ? AND user_id = ?",
        (action_id, owner_id),
    )
    conn.commit()
    conn.close()
    return True


def update_positioning_goal_action_status(action_id, status, user_id):
    status = _as_text(status)
    if status not in POSITIONING_ACTION_STATUSES:
        raise ValueError("无效的 status")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    row = conn.execute(
        "SELECT id FROM positioning_goal_action WHERE id = ? AND user_id = ?",
        (action_id, owner_id),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("变更记录不存在")

    conn.execute(
        """
        UPDATE positioning_goal_action SET status = ?
        WHERE id = ? AND user_id = ?
        """,
        (status, action_id, owner_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM positioning_goal_action WHERE id = ? AND user_id = ?",
        (action_id, owner_id),
    ).fetchone()
    conn.close()
    return _positioning_action_row(row)


def _validate_positioning_goal_action_fields(
    action_type, target_goal_id, action_payload, user_id
):
    if action_type not in POSITIONING_ACTION_TYPES:
        raise ValueError("无效的目标变更类型")

    if target_goal_id is not None and target_goal_id != "":
        try:
            target_goal_id = int(target_goal_id)
        except (TypeError, ValueError):
            raise ValueError("无效的目标 id")
        goal = get_goal(target_goal_id, user_id)
        if not goal:
            raise ValueError("目标不存在")
    else:
        target_goal_id = None

    if action_type == "新建目标" and target_goal_id is not None:
        raise ValueError("新建目标不应指定 target_goal_id")

    if action_type != "新建目标" and target_goal_id is None:
        raise ValueError("该变更类型必须指定 target_goal_id")

    action_payload = _parse_positioning_payload(action_payload)
    if action_type == "新建目标":
        name = _as_text(action_payload.get("name"))
        goal_type = _as_text(action_payload.get("type"))
        if not name:
            raise ValueError("新建目标必须提供 payload.name")
        if goal_type not in GOAL_TYPES:
            raise ValueError("无效的目标类型")
    elif action_type == "降级目标":
        goal_type = _as_text(action_payload.get("type"))
        if goal_type not in GOAL_TYPES:
            raise ValueError("降级目标必须提供 payload.type")

    return target_goal_id, action_payload


def create_positioning_goal_action(calibration_id, payload, user_id):
    payload = payload or {}
    calibration = get_positioning_calibration(calibration_id, user_id)
    if not calibration:
        raise ValueError("校准记录不存在")

    action_type = _as_text(payload.get("action_type"))
    target_goal_id, action_payload = _validate_positioning_goal_action_fields(
        action_type,
        payload.get("target_goal_id"),
        payload.get("payload"),
        user_id,
    )

    reason = _as_text(payload.get("reason"))
    if not reason:
        raise ValueError("变更理由不能为空")

    conn = get_connection()
    owner_id = _resolve_owner_id(conn, user_id)
    cur = conn.execute(
        """
        INSERT INTO positioning_goal_action (
            user_id, calibration_id, action_type, target_goal_id,
            payload, reason, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            owner_id,
            calibration_id,
            action_type,
            target_goal_id,
            json.dumps(action_payload, ensure_ascii=False),
            reason,
            _now(),
        ),
    )
    conn.commit()
    action_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM positioning_goal_action WHERE id = ? AND user_id = ?",
        (action_id, owner_id),
    ).fetchone()
    conn.close()
    return _positioning_action_row(row)
