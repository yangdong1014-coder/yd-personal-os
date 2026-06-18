import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "yd_os.db")

GOAL_TYPES = ("年度", "季度", "月度", "当前主线")
TASK_STATUSES = ("待处理", "进行中", "完成")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row):
    return dict(row) if row else None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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
        """
    )
    conn.commit()
    conn.close()


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
    conn.commit()
    goal_id = cur.lastrowid
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


def list_tasks():
    conn = get_connection()
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