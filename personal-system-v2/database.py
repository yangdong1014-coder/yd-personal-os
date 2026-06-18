import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "yd_os.db")
DB_PATH = os.environ.get("YD_OS_DB_PATH", _DEFAULT_DB_PATH)

GOAL_TYPES = ("年度", "季度", "月度", "当前主线")
TASK_STATUSES = ("待处理", "进行中", "完成")
REVIEW_TYPES = ("每日", "每周", "项目", "事件")
ASSET_TYPES = ("知识卡片", "SOP", "提示词", "工作流", "案例复盘", "方法论")
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
        """
    )
    _migrate_tasks_table(conn)
    _normalize_mainline_goals(conn)
    conn.commit()
    conn.close()


def _demote_other_mainline_goals(conn, keep_goal_id):
    conn.execute(
        """
        UPDATE goals SET type = '季度'
        WHERE type = '当前主线' AND id != ?
        """,
        (keep_goal_id,),
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


def update_goal(goal_id, goal_type):
    if goal_type not in GOAL_TYPES:
        raise ValueError("无效的目标类型")

    conn = get_connection()
    existing = conn.execute("SELECT id FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if not existing:
        conn.close()
        raise ValueError("目标不存在")

    conn.execute("UPDATE goals SET type = ? WHERE id = ?", (goal_type, goal_id))
    if goal_type == "当前主线":
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


def list_week_active_projects():
    week_start = _week_start_local()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT p.*, g.name AS goal_name
        FROM projects p
        JOIN goals g ON g.id = p.goal_id
        WHERE EXISTS (
            SELECT 1 FROM tasks t
            WHERE t.project_id = p.id
            AND t.status IN ('待处理', '进行中')
        )
        AND (
            date(p.created_at) >= ?
            OR EXISTS (
                SELECT 1 FROM tasks t2
                WHERE t2.project_id = p.id
                AND date(t2.created_at) >= ?
            )
        )
        ORDER BY p.created_at DESC
        """,
        (week_start, week_start),
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
        "week_projects": list_week_active_projects(),
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
    if data:
        data["capability_tags"] = _parse_tags(data.get("capability_tags"))
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
    trigger_context,
    core_content,
    asset_type,
    capability_tags,
    source_review_id=None,
):
    if asset_type not in ASSET_TYPES:
        raise ValueError("无效的资产类型")
    title = (title or "").strip()
    if not title:
        raise ValueError("标题不能为空")

    tags = _parse_tags(json.dumps(capability_tags or []))
    if source_review_id is not None:
        conn = get_connection()
        review = conn.execute(
            "SELECT id FROM reviews WHERE id = ?", (source_review_id,)
        ).fetchone()
        conn.close()
        if not review:
            raise ValueError("来源复盘不存在")

    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO assets (
            title, trigger_context, core_content, asset_type,
            capability_tags, source_review_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            (trigger_context or "").strip(),
            (core_content or "").strip(),
            asset_type,
            json.dumps(tags, ensure_ascii=False),
            source_review_id,
            _now(),
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


def list_assets(tag=None):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM assets ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    assets = [_asset_row(r) for r in rows]
    if tag:
        if tag not in CAPABILITY_MODULES:
            raise ValueError("无效的能力标签")
        assets = [a for a in assets if tag in a["capability_tags"]]
    return assets


def update_asset(
    asset_id,
    title,
    trigger_context,
    core_content,
    asset_type=None,
    capability_tags=None,
):
    title = (title or "").strip()
    core_content = (core_content or "").strip()
    if not title:
        raise ValueError("标题不能为空")
    if not core_content:
        raise ValueError("核心内容不能为空")
    if asset_type is not None and asset_type not in ASSET_TYPES:
        raise ValueError("无效的资产类型")

    conn = get_connection()
    existing = conn.execute("SELECT id FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if not existing:
        conn.close()
        raise ValueError("知识卡片不存在")

    fields = {
        "title": title,
        "trigger_context": (trigger_context or "").strip(),
        "core_content": core_content,
    }
    if asset_type is not None:
        fields["asset_type"] = asset_type
    if capability_tags is not None:
        tags = _parse_tags(json.dumps(capability_tags or []))
        fields["capability_tags"] = json.dumps(tags, ensure_ascii=False)

    set_clause = ", ".join(f"{key} = ?" for key in fields)
    conn.execute(
        f"UPDATE assets SET {set_clause} WHERE id = ?",
        (*fields.values(), asset_id),
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
    return _delete_entity("assets", asset_id, "知识卡片")


def delete_capability_entry(entry_id):
    return _delete_entity("capability_entries", entry_id, "能力记录")


_OPTIONAL_IMPORT_FIELDS = {
    "today_progress_date",
    "source_review_id",
    "source_project",
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
        stats["imported"] += 1
        return

    fields = _TABLE_FIELDS[table]
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(record[f] for f in fields),
    )
    stats["imported"] += 1


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
    _validate_import_payload(payload)

    stats = {"imported": 0, "skipped": 0, "failed": 0, "errors": []}
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
            summary = (
                f"导入失败：{stats['failed']} 条记录有误，"
                "已回滚，原有数据未改动"
            )
            raise DataImportError(summary, stats)

        _refresh_sqlite_sequences(conn)
        conn.commit()
        return stats
    except DataImportError:
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise DataImportError("数据库导入失败，已回滚") from exc
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