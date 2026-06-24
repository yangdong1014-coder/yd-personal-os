import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

import asset_schemas

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "yd_os.db")
DB_PATH = os.environ.get("YD_OS_DB_PATH", _DEFAULT_DB_PATH)

GOAL_TYPES = ("年度", "季度", "月度", "当前主线")
TASK_STATUSES = ("待处理", "进行中", "完成")
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
)
INBOX_OVERRIDE_FIELDS = frozenset({"goal_id", "project_id"})
INBOX_COMMIT_ORDER = {
    "goal": 0,
    "project": 1,
    "review": 2,
    "asset": 3,
    "capability_entry": 4,
    "task": 5,
}
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


def _row_to_dict(row):
    return dict(row) if row else None


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


def _migrate_tasks_table(conn):
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    if "today_progress" not in columns:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN today_progress INTEGER NOT NULL DEFAULT 0"
        )
    if "today_progress_date" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN today_progress_date TEXT")


def init_db():
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待处理',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_date TEXT NOT NULL,
            type TEXT NOT NULL,
            what_done TEXT NOT NULL DEFAULT '',
            stuck TEXT NOT NULL DEFAULT '',
            next_adjust TEXT NOT NULL DEFAULT '',
            depositable TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            trigger_context TEXT NOT NULL DEFAULT '',
            core_content TEXT NOT NULL DEFAULT '',
            asset_type TEXT NOT NULL,
            capability_tags TEXT NOT NULL DEFAULT '[]',
            source_review_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_review_id) REFERENCES reviews(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS capability_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            content TEXT NOT NULL,
            source_project TEXT,
            level_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS capability_practice_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            step_order INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    _migrate_tasks_table(conn)
    _migrate_inbox_tables(conn)
    _migrate_assets_table(conn)
    _ensure_default_capability_practice_steps(conn)
    _normalize_mainline_goals(conn)
    conn.commit()
    conn.close()


def _migrate_inbox_tables(conn):
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
    columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
    additions = {
        "summary": "TEXT NOT NULL DEFAULT ''",
        "fields": "TEXT NOT NULL DEFAULT '{}'",
        "reusable_scenario": "TEXT NOT NULL DEFAULT ''",
        "maturity": "TEXT NOT NULL DEFAULT '草稿'",
        "reuse_count": "INTEGER NOT NULL DEFAULT 0",
        "source_type": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
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


def _demote_other_mainline_goals(conn, keep_goal_id):
    conn.execute(
        """
        UPDATE goals SET type = '季度'
        WHERE type = '当前主线' AND id != ?
        """,
        (keep_goal_id,),
        )


def _ensure_default_capability_practice_steps(conn):
    now = _now()
    for module in CAPABILITY_MODULES:
        existing = conn.execute(
            "SELECT COUNT(*) AS cnt FROM capability_practice_steps WHERE module = ?",
            (module,),
        ).fetchone()
        if existing and existing["cnt"]:
            continue
        for index, step in enumerate(DEFAULT_CAPABILITY_PRACTICE_STEPS[module], start=1):
            conn.execute(
                """
                INSERT INTO capability_practice_steps (
                    module, step_order, title, description, detail, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    module,
                    index,
                    step["title"],
                    step["description"],
                    step["detail"],
                    now,
                    now,
                ),
            )


def _normalize_mainline_goals(conn):
    rows = conn.execute(
        """
        SELECT id FROM goals
        WHERE type = '当前主线'
        ORDER BY created_at DESC
        """
    ).fetchall()
    if len(rows) <= 1:
        return
    keep_id = rows[0][0]
    _demote_other_mainline_goals(conn, keep_id)


def create_goal(name, goal_type):
    if goal_type not in GOAL_TYPES:
        raise ValueError("无效的目标类型")
    name = name.strip()
    if not name:
        raise ValueError("目标名称不能为空")

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO goals (name, type, created_at) VALUES (?, ?, ?)",
        (name, goal_type, _now()),
    )
    goal_id = cur.lastrowid
    if goal_type == "当前主线":
        _demote_other_mainline_goals(conn, goal_id)
    conn.commit()
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def update_goal(goal_id, payload):
    payload = payload or {}
    conn = get_connection()
    existing = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
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
        f"UPDATE goals SET {assignments} WHERE id = ?",
        (*updates.values(), goal_id),
    )
    if updates.get("type") == "当前主线":
        _demote_other_mainline_goals(conn, goal_id)
    conn.commit()
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_goals():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM goals ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_goal(goal_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def create_project(goal_id, name):
    name = name.strip()
    if not name:
        raise ValueError("项目名称不能为空")

    conn = get_connection()
    goal = conn.execute("SELECT id FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if not goal:
        conn.close()
        raise ValueError("目标不存在")

    cur = conn.execute(
        "INSERT INTO projects (goal_id, name, created_at) VALUES (?, ?, ?)",
        (goal_id, name, _now()),
    )
    conn.commit()
    project_id = cur.lastrowid
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def get_project(project_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT p.*, g.name AS goal_name, g.type AS goal_type
        FROM projects p
        JOIN goals g ON g.id = p.goal_id
        WHERE p.id = ?
        """,
        (project_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def update_project(project_id, payload):
    payload = payload or {}
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("项目不存在")

    if "name" not in payload:
        conn.close()
        raise ValueError("没有可更新的项目字段")

    name = (payload.get("name") or "").strip()
    if not name:
        conn.close()
        raise ValueError("项目名称不能为空")

    conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))
    conn.commit()
    row = conn.execute(
        """
        SELECT p.*, g.name AS goal_name, g.type AS goal_type
        FROM projects p
        JOIN goals g ON g.id = p.goal_id
        WHERE p.id = ?
        """,
        (project_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_projects(goal_id=None):
    conn = get_connection()
    if goal_id is not None:
        rows = conn.execute(
            """
            SELECT p.*, g.name AS goal_name
            FROM projects p
            JOIN goals g ON g.id = p.goal_id
            WHERE p.goal_id = ?
            ORDER BY p.created_at DESC
            """,
            (goal_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT p.*, g.name AS goal_name
            FROM projects p
            JOIN goals g ON g.id = p.goal_id
            ORDER BY p.created_at DESC
            """
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def create_task(project_id, name):
    name = name.strip()
    if not name:
        raise ValueError("任务名称不能为空")

    conn = get_connection()
    project = conn.execute(
        "SELECT id FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not project:
        conn.close()
        raise ValueError("项目不存在")

    cur = conn.execute(
        "INSERT INTO tasks (project_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        (project_id, name, "待处理", _now()),
    )
    conn.commit()
    task_id = cur.lastrowid
    row = conn.execute(
        """
        SELECT t.*, p.name AS project_name, g.name AS goal_name
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        JOIN goals g ON g.id = p.goal_id
        WHERE t.id = ?
        """,
        (task_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def _fetch_task(conn, task_id):
    return conn.execute(
        """
        SELECT t.*, p.name AS project_name, g.name AS goal_name
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        JOIN goals g ON g.id = p.goal_id
        WHERE t.id = ?
        """,
        (task_id,),
    ).fetchone()


def list_tasks(project_id=None):
    conn = get_connection()
    if project_id is not None:
        rows = conn.execute(
            """
            SELECT t.*, p.name AS project_name, g.name AS goal_name
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            JOIN goals g ON g.id = p.goal_id
            WHERE t.project_id = ?
            ORDER BY t.created_at DESC
            """,
            (project_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT t.*, p.name AS project_name, g.name AS goal_name
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            JOIN goals g ON g.id = p.goal_id
            ORDER BY t.created_at DESC
            """
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_task(task_id, payload):
    payload = payload or {}
    conn = get_connection()
    existing = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
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

    if not updates:
        conn.close()
        raise ValueError("没有可更新的任务字段")

    assignments = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE tasks SET {assignments} WHERE id = ?",
        (*updates.values(), task_id),
    )
    conn.commit()
    row = _fetch_task(conn, task_id)
    conn.close()
    return _row_to_dict(row)


def update_task_status(task_id, status):
    if status not in TASK_STATUSES:
        raise ValueError("无效的任务状态")

    conn = get_connection()
    existing = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not existing:
        conn.close()
        raise ValueError("任务不存在")

    conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
    conn.commit()
    row = _fetch_task(conn, task_id)
    conn.close()
    return _row_to_dict(row)


def update_task_today_progress(task_id, enabled):
    conn = get_connection()
    existing = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not existing:
        conn.close()
        raise ValueError("任务不存在")

    if enabled:
        conn.execute(
            """
            UPDATE tasks
            SET today_progress = 1, today_progress_date = ?
            WHERE id = ?
            """,
            (_today_local(), task_id),
        )
    else:
        conn.execute(
            """
            UPDATE tasks
            SET today_progress = 0, today_progress_date = NULL
            WHERE id = ?
            """,
            (task_id,),
        )
    conn.commit()
    row = _fetch_task(conn, task_id)
    conn.close()
    return _row_to_dict(row)


def get_mainline_goal():
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM goals
        WHERE type = '当前主线'
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_active_projects():
    today = _today_local()
    conn = get_connection()
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
        JOIN goals g ON g.id = p.goal_id
        JOIN tasks t ON t.project_id = p.id
        GROUP BY p.id
        HAVING active_task_count > 0
        ORDER BY
            has_today_progress DESC,
            has_doing_task DESC,
            active_task_count DESC,
            p.created_at DESC
        """,
        (today,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def list_today_progress_tasks():
    today = _today_local()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT t.*, p.name AS project_name, g.name AS goal_name
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        JOIN goals g ON g.id = p.goal_id
        WHERE t.today_progress = 1 AND t.today_progress_date = ?
        ORDER BY t.created_at DESC
        """,
        (today,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_dashboard():
    return {
        "mainline_goal": get_mainline_goal(),
        "week_projects": list_active_projects(),
        "today_tasks": list_today_progress_tasks(),
    }


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
    data["source_id"] = data.get("source_review_id")
    if not data.get("source_type"):
        data["source_type"] = "review" if data.get("source_review_id") else ""
    if not (data.get("updated_at") or "").strip():
        data["updated_at"] = data.get("created_at")
    trigger, core_content = asset_schemas.sync_legacy_columns(data["asset_type"], fields)
    if trigger:
        data["trigger_context"] = trigger
    if core_content:
        data["core_content"] = core_content
    return data


def create_review(review_date, review_type, what_done, stuck, next_adjust, depositable):
    if review_type not in REVIEW_TYPES:
        raise ValueError("无效的复盘类型")
    review_date = (review_date or "").strip()
    if not review_date:
        raise ValueError("复盘日期不能为空")

    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO reviews (
            review_date, type, what_done, stuck, next_adjust, depositable, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
    row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_reviews():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reviews ORDER BY review_date DESC, created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_review(review_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
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
    source_type = ""
    if source_review_id is not None:
        conn = get_connection()
        review = conn.execute(
            "SELECT id FROM reviews WHERE id = ?", (source_review_id,)
        ).fetchone()
        conn.close()
        if not review:
            raise ValueError("来源复盘不存在")
        source_type = "review"

    now = _now()
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO assets (
            title, trigger_context, core_content, asset_type,
            capability_tags, source_review_id, created_at,
            summary, fields, reusable_scenario, maturity, reuse_count,
            source_type, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
            now,
        ),
    )
    conn.commit()
    asset_id = cur.lastrowid
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    conn.close()
    return _asset_row(row)


def get_asset(asset_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    conn.close()
    return _asset_row(row)


def list_assets(tag=None, asset_type=None):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM assets ORDER BY updated_at DESC, created_at DESC"
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


def update_asset(asset_id, **kwargs):
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
    }
    kwargs = {key: value for key, value in kwargs.items() if key in allowed_fields}
    if not kwargs:
        raise ValueError("没有可更新的资产字段")

    conn = get_connection()
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
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
    }

    set_clause = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE assets SET {set_clause} WHERE id = ?",
        (*updates.values(), asset_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    conn.close()
    return _asset_row(row)


def increment_asset_reuse(asset_id):
    conn = get_connection()
    row = conn.execute("SELECT id FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("资产不存在")
    conn.execute(
        """
        UPDATE assets
        SET reuse_count = reuse_count + 1, updated_at = ?
        WHERE id = ?
        """,
        (_now(), asset_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    conn.close()
    return _asset_row(row)


def create_capability_entry(
    module, entry_date, content, source_project, level_type
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
    cur = conn.execute(
        """
        INSERT INTO capability_entries (
            module, entry_date, content, source_project, level_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (module, entry_date, content, source_project, level_type, _now()),
    )
    conn.commit()
    entry_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM capability_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_capability_entries(module=None):
    conn = get_connection()
    if module is not None:
        if module not in CAPABILITY_MODULES:
            conn.close()
            raise ValueError("无效的能力模块")
        rows = conn.execute(
            """
            SELECT * FROM capability_entries
            WHERE module = ?
            ORDER BY entry_date DESC, created_at DESC
            """,
            (module,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM capability_entries
            ORDER BY entry_date DESC, created_at DESC
            """
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _practice_step_row(row):
    data = _row_to_dict(row)
    if not data:
        return data
    data["step_order"] = int(data.get("step_order") or 0)
    return data


def _normalize_practice_step_order(conn, module):
    rows = conn.execute(
        """
        SELECT id FROM capability_practice_steps
        WHERE module = ?
        ORDER BY step_order ASC, id ASC
        """,
        (module,),
    ).fetchall()
    now = _now()
    for index, row in enumerate(rows, start=1):
        conn.execute(
            """
            UPDATE capability_practice_steps
            SET step_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (index, now, row["id"]),
        )


def list_capability_practice_paths():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM capability_practice_steps
        ORDER BY module ASC, step_order ASC, id ASC
        """
    ).fetchall()
    conn.close()
    paths = {module: [] for module in CAPABILITY_MODULES}
    for row in rows:
        step = _practice_step_row(row)
        if step["module"] in paths:
            paths[step["module"]].append(step)
    return paths


def get_capability_practice_path(module):
    if module not in CAPABILITY_MODULES:
        raise ValueError("无效的能力模块")
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM capability_practice_steps
        WHERE module = ?
        ORDER BY step_order ASC, id ASC
        """,
        (module,),
    ).fetchall()
    conn.close()
    return [_practice_step_row(row) for row in rows]


def create_capability_practice_step(
    module, title, description="", detail="", step_order=None
):
    if module not in CAPABILITY_MODULES:
        raise ValueError("无效的能力模块")
    title = (title or "").strip()
    if not title:
        raise ValueError("步骤名称不能为空")
    description = (description or "").strip()
    detail = (detail or "").strip()

    conn = get_connection()
    if step_order is None:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(step_order), 0) + 1 AS next_order
            FROM capability_practice_steps
            WHERE module = ?
            """,
            (module,),
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
            WHERE module = ? AND step_order >= ?
            """,
            (module, step_order),
        )

    now = _now()
    cur = conn.execute(
        """
        INSERT INTO capability_practice_steps (
            module, step_order, title, description, detail, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (module, step_order, title, description, detail, now, now),
    )
    _normalize_practice_step_order(conn, module)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return _practice_step_row(row)


def update_capability_practice_step(step_id, **kwargs):
    allowed = {"title", "description", "detail", "step_order"}
    updates = {key: value for key, value in kwargs.items() if key in allowed}
    if not updates:
        raise ValueError("没有可更新的训练步骤字段")

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ?",
        (step_id,),
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
            WHERE module = ? AND id != ? AND step_order >= ? AND step_order < ?
            """,
            (current["module"], step_id, step_order, current_order),
        )
    elif step_order > current_order:
        conn.execute(
            """
            UPDATE capability_practice_steps
            SET step_order = step_order - 1
            WHERE module = ? AND id != ? AND step_order <= ? AND step_order > ?
            """,
            (current["module"], step_id, step_order, current_order),
        )

    conn.execute(
        """
        UPDATE capability_practice_steps
        SET title = ?, description = ?, detail = ?, step_order = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            title,
            (description or "").strip(),
            (detail or "").strip(),
            step_order,
            _now(),
            step_id,
        ),
    )
    _normalize_practice_step_order(conn, current["module"])
    conn.commit()
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ?",
        (step_id,),
    ).fetchone()
    conn.close()
    return _practice_step_row(row)


def delete_capability_practice_step(step_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM capability_practice_steps WHERE id = ?",
        (step_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("训练步骤不存在")
    module = row["module"]
    conn.execute("DELETE FROM capability_practice_steps WHERE id = ?", (step_id,))
    _normalize_practice_step_order(conn, module)
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


def get_capability_summary():
    assets = list_assets()
    entries = list_capability_entries()
    practice_paths = list_capability_practice_paths()
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


SUPPORTED_IMPORT_VERSIONS = ("1.0",)
IMPORT_TABLES = (
    "goals",
    "projects",
    "tasks",
    "reviews",
    "assets",
    "capability_entries",
)

_TABLE_FIELDS = {
    "goals": ("id", "name", "type", "created_at"),
    "projects": ("id", "goal_id", "name", "created_at"),
    "tasks": (
        "id",
        "project_id",
        "name",
        "status",
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
        "updated_at",
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
}


def _delete_entity(table, entity_id, entity_label):
    conn = get_connection()
    try:
        existing = conn.execute(
            f"SELECT id FROM {table} WHERE id = ?", (entity_id,)
        ).fetchone()
        if not existing:
            raise ValueError(f"{entity_label}不存在")

        conn.execute(f"DELETE FROM {table} WHERE id = ?", (entity_id,))
        conn.commit()
        return {"id": entity_id, "deleted": True}
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            f"无法删除{entity_label}：存在关联数据，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_goal(goal_id):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if not existing:
            raise ValueError("目标不存在")

        project_count = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE goal_id = ?", (goal_id,)
        ).fetchone()[0]
        task_count = conn.execute(
            """
            SELECT COUNT(*) FROM tasks
            WHERE project_id IN (
                SELECT id FROM projects WHERE goal_id = ?
            )
            """,
            (goal_id,),
        ).fetchone()[0]

        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()
        return {
            "id": goal_id,
            "deleted": True,
            "cascaded": {"projects": project_count, "tasks": task_count},
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            "无法删除目标：存在关联数据约束，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_project(project_id):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not existing:
            raise ValueError("项目不存在")

        task_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        return {
            "id": project_id,
            "deleted": True,
            "cascaded": {"tasks": task_count},
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            "无法删除项目：存在关联数据约束，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_task(task_id):
    return _delete_entity("tasks", task_id, "任务")


def delete_review(review_id):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if not existing:
            raise ValueError("复盘不存在")

        asset_count = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE source_review_id = ?",
            (review_id,),
        ).fetchone()[0]

        conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        conn.commit()
        return {
            "id": review_id,
            "deleted": True,
            "cleared_asset_links": asset_count,
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DeleteError(
            "无法删除复盘：存在关联数据约束，请先处理依赖记录"
        ) from exc
    finally:
        conn.close()


def delete_asset(asset_id):
    return _delete_entity("assets", asset_id, "资产")


def delete_capability_entry(entry_id):
    return _delete_entity("capability_entries", entry_id, "能力记录")


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
    "updated_at",
}


def _normalize_import_record(table, raw):
    if not isinstance(raw, dict):
        raise ValueError("记录必须是对象")
    fields = _TABLE_FIELDS[table]
    record = {}
    for key in fields:
        if key not in raw:
            if key == "today_progress":
                record[key] = 0
            elif key in _OPTIONAL_IMPORT_FIELDS:
                record[key] = None
            else:
                raise ValueError(f"缺少字段 {key}")
        else:
            record[key] = raw[key]

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
        if not record.get("updated_at"):
            record["updated_at"] = record.get("created_at")

    if table == "goals" and record["type"] not in GOAL_TYPES:
        raise ValueError("无效的目标类型")
    if table == "tasks" and record["status"] not in TASK_STATUSES:
        raise ValueError("无效的任务状态")
    if table == "reviews" and record["type"] not in REVIEW_TYPES:
        raise ValueError("无效的复盘类型")
    if table == "assets" and record["asset_type"] not in ASSET_TYPES:
        raise ValueError("无效的资产类型")
    if table == "capability_entries":
        if record["module"] not in CAPABILITY_MODULES:
            raise ValueError("无效的能力模块")
        if record["level_type"] not in LEVEL_TYPES:
            raise ValueError("无效的层级判断")

    return record


def _records_equal(table, existing_row, incoming):
    fields = _TABLE_FIELDS[table]
    for key in fields:
        existing_val = existing_row[key]
        incoming_val = incoming[key]
        if key == "capability_tags" and table == "assets":
            existing_val = _parse_tags(existing_val)
            incoming_val = _parse_tags(incoming_val)
        if existing_val != incoming_val:
            return False
    return True


def _validate_import_foreign_keys(table, record, conn, pending):
    if table == "projects":
        goal_id = record["goal_id"]
        if goal_id not in pending["goals"] and not conn.execute(
            "SELECT id FROM goals WHERE id = ?", (goal_id,)
        ).fetchone():
            raise ValueError(f"目标 id={goal_id} 不存在")
    elif table == "tasks":
        project_id = record["project_id"]
        if project_id not in pending["projects"] and not conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone():
            raise ValueError(f"项目 id={project_id} 不存在")
    elif table == "assets":
        review_id = record.get("source_review_id")
        if review_id is not None and review_id not in pending["reviews"]:
            if not conn.execute(
                "SELECT id FROM reviews WHERE id = ?", (review_id,)
            ).fetchone():
                raise ValueError(f"复盘 id={review_id} 不存在")


def _resolve_import_action(conn, table, raw, pending=None):
    record = _normalize_import_record(table, raw)
    row_id = record["id"]
    if not isinstance(row_id, int):
        raise ValueError("id 必须是整数")

    existing = conn.execute(
        f"SELECT * FROM {table} WHERE id = ?", (row_id,)
    ).fetchone()

    if existing:
        if _records_equal(table, existing, record):
            return "skip", record
        return "update", record

    if pending is not None:
        _validate_import_foreign_keys(table, record, conn, pending)
        pending[table].add(row_id)
    return "insert", record


def _new_import_stats():
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "imported": 0,
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
        "rolled_back": True,
        "message": IMPORT_ROLLBACK_MESSAGE,
    }


def _import_row(conn, table, raw, stats):
    action, record = _resolve_import_action(conn, table, raw)
    row_id = record["id"]

    if action == "skip":
        stats["skipped"] += 1
        return
    if action == "update":
        fields = _TABLE_FIELDS[table]
        set_clause = ", ".join(f"{f} = ?" for f in fields if f != "id")
        values = [record[f] for f in fields if f != "id"]
        conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE id = ?",
            (*values, row_id),
        )
        stats["updated"] += 1
        return

    fields = _TABLE_FIELDS[table]
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(record[f] for f in fields),
    )
    stats["created"] += 1


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

    for table in IMPORT_TABLES:
        if table not in payload:
            raise DataImportError(f"缺少数据表：{table}")
        if not isinstance(payload[table], list):
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


def preview_import_data(payload):
    _validate_import_payload(payload)

    stats = {
        "will_import": 0,
        "will_update": 0,
        "will_skip": 0,
        "will_fail": 0,
        "errors": [],
    }
    pending = {table: set() for table in IMPORT_TABLES}
    conn = get_connection()
    try:
        for table in IMPORT_TABLES:
            for index, raw in enumerate(payload[table]):
                label = f"{table}[{index}]"
                try:
                    action, _record = _resolve_import_action(
                        conn, table, raw, pending
                    )
                    if action == "skip":
                        stats["will_skip"] += 1
                    elif action == "insert":
                        stats["will_import"] += 1
                    elif action == "update":
                        stats["will_update"] += 1
                except (ValueError, TypeError) as exc:
                    stats["will_fail"] += 1
                    message = str(exc) or "记录无效"
                    if len(stats["errors"]) < 20:
                        stats["errors"].append(f"{label}: {message}")
        return stats
    finally:
        conn.close()


def import_all_data(payload):
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
        conn.execute("BEGIN")
        for table in IMPORT_TABLES:
            for index, raw in enumerate(payload[table]):
                label = f"{table}[{index}]"
                try:
                    _import_row(conn, table, raw, stats)
                except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
                    stats["failed"] += 1
                    message = str(exc) or "记录无效"
                    if len(stats["errors"]) < 20:
                        stats["errors"].append(f"{label}: {message}")

        if stats["failed"] > 0:
            conn.rollback()
            failure = _import_failure_stats(stats)
            summary = (
                f"导入失败：{failure['failed']} 条记录有误，"
                "已回滚，原有数据未改动"
            )
            raise DataImportError(summary, failure)

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


def export_all_data():
    try:
        return {
            "meta": {
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "1.0",
                "tables": [
                    "goals",
                    "projects",
                    "tasks",
                    "reviews",
                    "assets",
                    "capability_entries",
                ],
            },
            "goals": list_goals(),
            "projects": list_projects(),
            "tasks": list_tasks(),
            "reviews": list_reviews(),
            "assets": list_assets(),
            "capability_entries": list_capability_entries(),
        }
    except sqlite3.Error as exc:
        raise ExportError(
            "数据库读取失败，请关闭占用数据库的程序后重试"
        ) from exc
    except Exception as exc:
        raise ExportError("导出数据时发生错误，请稍后重试") from exc


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


def create_inbox_entry(raw_text, source_type="manual"):
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("输入文本不能为空")
    if source_type not in ("manual",):
        raise ValueError("无效的 source_type")

    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO inbox_entries (raw_text, source_type, status, created_at)
        VALUES (?, ?, 'draft', ?)
        """,
        (text, source_type, _now()),
    )
    conn.commit()
    entry_id = cur.lastrowid
    row = conn.execute(
        "SELECT * FROM inbox_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def update_inbox_entry_status(entry_id, status):
    if status not in INBOX_ENTRY_STATUSES:
        raise ValueError("无效的 inbox 状态")

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM inbox_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise ValueError("inbox 记录不存在")

    conn.execute(
        "UPDATE inbox_entries SET status = ? WHERE id = ?",
        (status, entry_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM inbox_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def get_inbox_entry(entry_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM inbox_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def list_inbox_entries(limit=20):
    conn = get_connection()
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
        LEFT JOIN inbox_suggestions s ON s.inbox_entry_id = e.id
        GROUP BY e.id
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = _row_to_dict(row)
        raw = item.get("raw_text") or ""
        item["raw_text_summary"] = raw[:120] + ("…" if len(raw) > 120 else "")
        result.append(item)
    return result


def create_inbox_suggestions(entry_id, items):
    if not get_inbox_entry(entry_id):
        raise ValueError("inbox 记录不存在")

    conn = get_connection()
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
            cur = conn.execute(
                """
                INSERT INTO inbox_suggestions (
                    inbox_entry_id, target_type, title, content,
                    confidence, reason, suggested_payload, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
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
                "SELECT * FROM inbox_suggestions WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
            created.append(_suggestion_row(row))
        conn.commit()
        return created
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_inbox_suggestions(entry_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM inbox_suggestions
        WHERE inbox_entry_id = ?
        ORDER BY id ASC
        """,
        (entry_id,),
    ).fetchall()
    conn.close()
    return [_suggestion_row(r) for r in rows]


def get_inbox_suggestion(suggestion_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM inbox_suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()
    conn.close()
    return _suggestion_row(row)


def reject_inbox_suggestion(suggestion_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM inbox_suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("建议不存在")
    if row["status"] == "committed":
        conn.close()
        raise ValueError("已入库的建议无法拒绝")

    conn.execute(
        "UPDATE inbox_suggestions SET status = 'rejected' WHERE id = ?",
        (suggestion_id,),
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM inbox_suggestions WHERE id = ?", (suggestion_id,)
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
    for key, value in override_map[sid].items():
        if key in INBOX_OVERRIDE_FIELDS:
            payload[key] = value
    merged = dict(suggestion)
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


def _validate_suggestion_for_commit(conn, suggestion, batch_project_refs=None):
    batch_project_refs = batch_project_refs or set()
    sid = suggestion["id"]
    target_type = suggestion["target_type"]
    title = suggestion.get("title") or ""
    content = suggestion.get("content") or ""
    payload = suggestion["suggested_payload"]

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
            "SELECT id FROM goals WHERE id = ?", (goal_id,)
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
            "SELECT id FROM projects WHERE id = ?", (project_id,)
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
        asset_type = asset_schemas.normalize_asset_type(
            payload.get("asset_type") or "通用资产", asset_title, content
        )
        fields = asset_schemas.parse_fields(payload.get("fields"))
        if not fields:
            fields = asset_schemas.build_fields_from_legacy(
                asset_type,
                payload.get("trigger_context") or "",
                payload.get("core_content") or content,
            )
        if not asset_title or not asset_schemas.asset_content_valid(asset_type, fields, content):
            return f"建议 #{sid}（资产）：需要标题与内容"
        return None

    if target_type == "capability_entry":
        entry_content = (payload.get("content") or content).strip()
        if not entry_content:
            return f"建议 #{sid}（能力记录）：缺少内容"
        return None

    return f"建议 #{sid} 类型为 {target_type}，不可入库"


def _commit_suggestion_in_tx(conn, suggestion, ref_map=None):
    ref_map = ref_map or {}
    target_type = suggestion["target_type"]
    title = suggestion["title"]
    content = suggestion["content"]
    payload = dict(suggestion["suggested_payload"])

    if target_type == "goal":
        name = (payload.get("name") or title).strip()
        if not name:
            raise ValueError("目标名称不能为空")
        goal_type = _map_goal_type(payload.get("type"))
        cur = conn.execute(
            "INSERT INTO goals (name, type, created_at) VALUES (?, ?, ?)",
            (name, goal_type, _now()),
        )
        if goal_type == "当前主线":
            _demote_other_mainline_goals(conn, cur.lastrowid)
        return "goals", cur.lastrowid

    if target_type == "project":
        name = (payload.get("name") or title).strip()
        goal_id = _coerce_positive_int(payload.get("goal_id"))
        if not name:
            raise ValueError("项目名称不能为空")
        if not goal_id:
            raise ValueError("项目归档需要关联目标 goal_id")
        goal = conn.execute(
            "SELECT id FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if not goal:
            raise ValueError("关联目标不存在")
        cur = conn.execute(
            "INSERT INTO projects (goal_id, name, created_at) VALUES (?, ?, ?)",
            (goal_id, name, _now()),
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
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not project:
            raise ValueError("关联项目不存在")
        cur = conn.execute(
            """
            INSERT INTO tasks (project_id, name, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, name, status, _now()),
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
                review_date, type, what_done, stuck, next_adjust, depositable, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
        asset_type = asset_schemas.normalize_asset_type(
            payload.get("asset_type") or "通用资产", asset_title, content
        )
        parsed_fields = asset_schemas.parse_fields(payload.get("fields"))
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
        summary = asset_schemas.extract_summary(parsed_fields, legacy_core)
        reusable = asset_schemas.extract_reusable_scenario(asset_type, parsed_fields)
        maturity = payload.get("maturity") or "可用"
        if maturity not in MATURITY_LEVELS:
            maturity = "可用"
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
                title, trigger_context, core_content, asset_type,
                capability_tags, source_review_id, created_at,
                summary, fields, reusable_scenario, maturity, reuse_count,
                source_type, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                module, entry_date, content, source_project, level_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                module,
                entry_date,
                entry_content,
                (payload.get("source_project") or "").strip(),
                level_type,
                _now(),
            ),
        )
        return "capability_entries", cur.lastrowid

    raise ValueError(f"类型 {target_type} 不可入库")


def commit_inbox_suggestions(suggestion_ids, override_payload=None):
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
    }
    skipped = 0
    errors = []

    override_map = _parse_override_payloads(override_payload)
    conn = get_connection()
    candidates = []
    try:
        for suggestion_id in unique_ids:
            row = conn.execute(
                "SELECT * FROM inbox_suggestions WHERE id = ?",
                (suggestion_id,),
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
                conn, suggestion, batch_project_refs
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
            table_key, entity_id = _commit_suggestion_in_tx(conn, suggestion, ref_map)
            created[table_key] += 1
            payload = suggestion["suggested_payload"]
            if suggestion["target_type"] == "project":
                local_ref = (payload.get("local_ref") or "").strip()
                if local_ref:
                    ref_map[local_ref] = entity_id
            conn.execute(
                "UPDATE inbox_suggestions SET status = 'committed' WHERE id = ?",
                (suggestion["id"],),
            )
            entry_ids.add(suggestion["inbox_entry_id"])

        for entry_id in entry_ids:
            pending = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM inbox_suggestions
                WHERE inbox_entry_id = ? AND status = 'pending'
                """,
                (entry_id,),
            ).fetchone()["cnt"]
            if pending == 0:
                conn.execute(
                    "UPDATE inbox_entries SET status = 'committed' WHERE id = ?",
                    (entry_id,),
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
