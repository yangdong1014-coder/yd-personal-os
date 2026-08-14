"""Offline, staged legacy v2.1.4 to v2.2 multi-user migration."""

import json
import hashlib
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash

import auth_service
import database


LEGACY_V214_COLUMNS = {
    "goals": ("id", "name", "type", "created_at", "status"),
    "projects": (
        "id", "goal_id", "name", "priority", "created_at",
        "core_hypothesis", "disconfirming_signal", "seven_day_mvp",
        "real_feedback", "result_data", "asset_deposit", "value_capture",
        "stop_condition", "value_tags", "importance_score",
        "feedback_speed_score", "revenue_score", "asset_score",
        "leverage_score", "total_score",
    ),
    "tasks": (
        "id", "project_id", "name", "status", "priority", "created_at",
        "today_progress", "today_progress_date",
    ),
    "reviews": (
        "id", "review_date", "type", "what_done", "stuck", "next_adjust",
        "depositable", "created_at",
    ),
    "assets": (
        "id", "title", "trigger_context", "core_content", "asset_type",
        "capability_tags", "source_review_id", "created_at", "summary",
        "fields", "reusable_scenario", "maturity", "reuse_count",
        "source_type", "source_id", "updated_at", "asset_level", "evidence",
        "external_expression", "transferable_scene",
        "productization_next_step",
    ),
    "capability_entries": (
        "id", "module", "entry_date", "content", "source_project",
        "level_type", "created_at",
    ),
    "capability_practice_steps": (
        "id", "module", "step_order", "title", "description", "detail",
        "created_at", "updated_at",
    ),
    "opportunities": (
        "id", "name", "source", "description", "related_context",
        "target_user", "affects_revenue", "affects_cost",
        "affects_efficiency", "affects_experience",
        "productization_potential", "transaction_potential", "seven_day_mvp",
        "case_asset_potential", "leverage_potential", "importance_score",
        "feedback_speed_score", "revenue_score", "asset_score",
        "leverage_score", "total_score", "status", "next_action",
        "created_at", "updated_at",
    ),
    "experiments": (
        "id", "opportunity_id", "name", "hypothesis", "experiment_type",
        "minimum_action", "test_target", "feedback_source",
        "validation_period", "success_criteria", "failure_criteria",
        "progress", "real_feedback", "data_result", "next_decision",
        "review_conclusion", "status", "created_at", "updated_at",
    ),
    "feedback_items": (
        "id", "related_type", "related_id", "title", "source", "level",
        "content", "evidence", "next_action", "created_at", "updated_at",
    ),
    "deliberations": (
        "id", "title", "problem", "context", "initial_judgment", "reasoning",
        "assumptions", "related_type", "related_id", "ai_analysis",
        "final_judgment", "decision", "decision_reasoning", "next_action",
        "actual_result", "judgment_accuracy", "judgment_error",
        "key_variable", "lesson", "principle", "status", "created_at",
        "updated_at",
    ),
    "positioning_anchor": (
        "id", "first_principle", "identity_core", "flywheel_def",
        "current_stage", "north_star", "updated_at",
    ),
    "positioning_calibration": (
        "id", "calibrated_at", "cycle", "primary_contradiction",
        "doing_but_shouldnt", "should_but_not_doing", "alignment_review",
        "conclusion", "created_at",
    ),
    "positioning_goal_action": (
        "id", "calibration_id", "action_type", "target_goal_id", "payload",
        "reason", "status", "created_at",
    ),
    "inbox_entries": (
        "id", "raw_text", "source_type", "status", "created_at",
    ),
    "inbox_suggestions": (
        "id", "inbox_entry_id", "target_type", "title", "content",
        "confidence", "reason", "suggested_payload", "status", "created_at",
    ),
}

SOFT_RELATION_TARGETS = {
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

HARD_RELATIONS = (
    ("projects.goal_id", "projects", "goal_id", "goals"),
    ("tasks.project_id", "tasks", "project_id", "projects"),
    ("assets.source_review_id", "assets", "source_review_id", "reviews"),
    ("experiments.opportunity_id", "experiments", "opportunity_id", "opportunities"),
    (
        "positioning_goal_action.calibration_id",
        "positioning_goal_action",
        "calibration_id",
        "positioning_calibration",
    ),
    (
        "inbox_suggestions.inbox_entry_id",
        "inbox_suggestions",
        "inbox_entry_id",
        "inbox_entries",
    ),
)


class MigrationError(RuntimeError):
    pass


class VerificationError(MigrationError):
    def __init__(self, issues, report=None):
        self.issues = list(issues)
        self.report = report or {}
        super().__init__("; ".join(self.issues))


def _quote(identifier):
    if identifier not in database.PERSONAL_DATA_TABLES and identifier not in {
        column
        for columns in LEGACY_V214_COLUMNS.values()
        for column in columns
    }:
        raise MigrationError(f"不允许的 SQLite 标识符：{identifier}")
    return '"' + identifier.replace('"', '""') + '"'


def _readonly_uri(path):
    return f"{Path(path).resolve().as_uri()}?mode=ro"


def _connect_readonly(path):
    conn = sqlite3.connect(_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect_writable(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")
    return conn


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_names(conn, schema="main"):
    return {
        row["name"]
        for row in conn.execute(
            f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'"
        ).fetchall()
        if not row["name"].startswith("sqlite_")
    }


def _table_columns(conn, table, schema="main"):
    return tuple(
        row["name"]
        for row in conn.execute(
            f"PRAGMA {schema}.table_info({_quote(table)})"
        ).fetchall()
    )


def _sequence_value(conn, table, schema="main"):
    row = conn.execute(
        f"SELECT seq FROM {schema}.sqlite_sequence WHERE name = ?", (table,)
    ).fetchone()
    return int(row["seq"]) if row is not None else None


def validate_legacy_source(conn):
    issues = []
    tables = _table_names(conn)
    missing = set(database.PERSONAL_DATA_TABLES) - tables
    if missing:
        issues.append("legacy 缺少业务表：" + ", ".join(sorted(missing)))
    if "users" in tables:
        issues.append("输入库包含 users，不是受支持的纯 v2.1.4 legacy 数据库")

    for table in database.PERSONAL_DATA_TABLES:
        if table not in tables:
            continue
        actual = _table_columns(conn, table)
        expected = LEGACY_V214_COLUMNS[table]
        if set(actual) != set(expected) or len(actual) != len(expected):
            issues.append(
                f"{table} 字段与 v2.1.4 不一致：actual={actual}, expected={expected}"
            )
        if "user_id" in actual:
            issues.append(f"{table} 已包含 user_id，不允许重复迁移")

    if "positioning_anchor" in tables:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM positioning_anchor").fetchone()[
            "cnt"
        ]
        if int(count) > 1:
            issues.append("legacy positioning_anchor 超过一行，无法无损升级为每用户单例")

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        issues.append(f"legacy integrity_check 失败：{integrity}")
    foreign_key_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_rows:
        issues.append(f"legacy foreign_key_check 返回 {len(foreign_key_rows)} 行")
    if issues:
        raise MigrationError("; ".join(issues))


def _insert_admin(conn, username, email, password):
    username = auth_service.normalize_username(username)
    email = auth_service.normalize_email(email)
    password = auth_service.validate_password(password)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO users (
            username, email, password_hash, role, is_active,
            must_change_password, auth_version, failed_login_count,
            locked_until, last_login_at, created_at, updated_at
        ) VALUES (?, ?, ?, 'admin', 1, 0, 1, 0, NULL, NULL, ?, ?)
        """,
        (username, email, generate_password_hash(password), now, now),
    )
    return int(cursor.lastrowid)


def _copy_table(source, staged, table, admin_id):
    source_columns = _table_columns(source, table)
    expected = LEGACY_V214_COLUMNS[table]
    if set(source_columns) != set(expected) or len(source_columns) != len(expected):
        raise MigrationError(f"{table} legacy 字段在复制前发生变化")
    staged_columns = _table_columns(staged, table)
    if set(staged_columns) != set(source_columns) | {"user_id"}:
        raise MigrationError(f"{table} staged 字段不能完整承载 legacy 数据")

    column_sql = ", ".join(_quote(column) for column in source_columns)
    cursor = source.execute(
        f"SELECT {column_sql} FROM {_quote(table)} ORDER BY id"
    )
    insert_columns = f"{column_sql}, user_id"
    placeholders = ", ".join("?" for _ in range(len(source_columns) + 1))
    copied = 0
    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        staged.executemany(
            f"INSERT INTO {_quote(table)} ({insert_columns}) VALUES ({placeholders})",
            (
                tuple(row[column] for column in source_columns) + (admin_id,)
                for row in rows
            ),
        )
        copied += len(rows)
    return copied


def _copy_sequences(source, staged):
    for table in database.PERSONAL_DATA_TABLES:
        source_seq = _sequence_value(source, table)
        staged_row = staged.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
        ).fetchone()
        if source_seq is None:
            if staged_row is not None:
                staged.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
        elif staged_row is None:
            staged.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
                (table, source_seq),
            )
        else:
            staged.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                (source_seq, table),
            )


def _cleanup_temporary_database(path):
    if path is None:
        return
    path = Path(path)
    for candidate in (path, Path(str(path) + "-journal"), Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def migrate_legacy_database(
    source_path,
    staged_path,
    *,
    admin_username,
    admin_email,
    admin_password,
    failure_hook=None,
):
    source_path = Path(source_path).resolve()
    staged_path = Path(staged_path).resolve()
    if source_path == staged_path:
        raise MigrationError("源库与 staged 目标不能是同一路径")
    if not source_path.is_file():
        raise MigrationError("legacy 源数据库不存在")
    if staged_path.exists():
        raise MigrationError("staged 目标已存在；为防止覆盖，迁移已停止")

    source_before = source_path.stat()
    source_hash = _sha256(source_path)
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{staged_path.name}.", suffix=".tmp", dir=staged_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    source = None
    staged = None
    try:
        source = _connect_readonly(source_path)
        source.execute("BEGIN")
        validate_legacy_source(source)

        staged = _connect_writable(temporary_path)
        database.initialize_v22_schema(staged)
        staged.commit()
        staged.execute("BEGIN IMMEDIATE")
        admin_id = _insert_admin(
            staged, admin_username, admin_email, admin_password
        )
        row_counts = {}
        for table in database.PERSONAL_DATA_TABLES:
            row_counts[table] = _copy_table(source, staged, table, admin_id)
            if failure_hook is not None:
                failure_hook(table, row_counts[table])
        _copy_sequences(source, staged)
        staged.commit()
        staged.close()
        staged = None
        source.close()
        source = None

        verification = verify_migration(source_path, temporary_path)
        source_after = source_path.stat()
        if (
            source_before.st_size != source_after.st_size
            or source_before.st_mtime_ns != source_after.st_mtime_ns
            or source_hash != _sha256(source_path)
        ):
            raise MigrationError("legacy 源数据库在迁移期间发生变化")

        linked = False
        try:
            os.link(temporary_path, staged_path)
            linked = True
            temporary_path.unlink()
        except Exception:
            if linked:
                staged_path.unlink(missing_ok=True)
            raise
        return {
            "ok": True,
            "source": str(source_path),
            "staged": str(staged_path),
            "admin_id": admin_id,
            "source_sha256": source_hash,
            "row_counts": row_counts,
            "verification": verification,
        }
    except Exception:
        if staged is not None:
            staged.rollback()
            staged.close()
        if source is not None:
            source.close()
        _cleanup_temporary_database(temporary_path)
        raise


def _except_count(conn, left_schema, right_schema, table, columns, admin_id, reverse=False):
    column_sql = ", ".join(_quote(column) for column in columns)
    if not reverse:
        sql = (
            f"SELECT {column_sql} FROM {left_schema}.{_quote(table)} "
            f"EXCEPT SELECT {column_sql} FROM {right_schema}.{_quote(table)} "
            "WHERE user_id = ?"
        )
    else:
        sql = (
            f"SELECT {column_sql} FROM {right_schema}.{_quote(table)} "
            "WHERE user_id = ? "
            f"EXCEPT SELECT {column_sql} FROM {left_schema}.{_quote(table)}"
        )
    return len(conn.execute(sql, (admin_id,)).fetchall())


def _count_query(conn, sql, params=()):
    return int(conn.execute(sql, params).fetchone()[0])


def _verify_hard_relations(conn):
    counts = {}
    issues = []
    for label, child, child_column, parent in HARD_RELATIONS:
        count = _count_query(
            conn,
            f"""
            SELECT COUNT(*) FROM {_quote(child)} child
            WHERE child.{child_column} IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM {_quote(parent)} parent
                WHERE parent.id = child.{child_column}
                  AND parent.user_id = child.user_id
              )
            """,
        )
        counts[label] = count
        if count:
            issues.append(f"硬关联孤儿/跨用户 {label}: {count}")
    return counts, issues


def _verify_soft_relations(conn, admin_id):
    issues = []
    counts = {}
    for table, targets in SOFT_RELATION_TARGETS.items():
        for related_type, target in targets.items():
            key = f"{table}.{related_type}"
            count = _count_query(
                conn,
                f"""
                SELECT COUNT(*) FROM main.{_quote(table)} child
                WHERE child.related_type = ? AND child.related_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM main.{_quote(target)} parent
                    WHERE parent.id = child.related_id
                      AND parent.user_id = child.user_id
                  )
                """,
                (related_type,),
            )
            counts[key] = count
            if count:
                issues.append(f"软关联孤儿 {key}: {count}")
        placeholders = ", ".join("?" for _ in targets)
        unknown_count = _count_query(
            conn,
            f"""
            SELECT COUNT(*) FROM {_quote(table)}
            WHERE related_id IS NOT NULL
              AND related_type NOT IN ({placeholders})
            """,
            tuple(targets),
        )
        unknown_key = f"{table}.unknown_type"
        counts[unknown_key] = unknown_count
        if unknown_count:
            issues.append(f"软关联类型无效 {unknown_key}: {unknown_count}")

    action_orphans = _count_query(
        conn,
        """
        SELECT COUNT(*) FROM positioning_goal_action action
        WHERE action.target_goal_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM goals goal
            WHERE goal.id = action.target_goal_id
              AND goal.user_id = action.user_id
          )
        """,
    )
    counts["positioning_goal_action.target_goal_id"] = action_orphans
    if action_orphans:
        issues.append(
            f"软关联孤儿 positioning_goal_action.target_goal_id: {action_orphans}"
        )

    asset_source_targets = {
        "review": "reviews",
        "feedback": "feedback_items",
        "experiment": "experiments",
        "opportunity": "opportunities",
    }
    for source_type, target in asset_source_targets.items():
        count = _count_query(
            conn,
            f"""
            SELECT COUNT(*) FROM assets asset
            WHERE asset.source_type = ? AND asset.source_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM {_quote(target)} parent
                WHERE parent.id = asset.source_id
                  AND parent.user_id = asset.user_id
              )
            """,
            (source_type,),
        )
        key = f"assets.source_id.{source_type}"
        counts[key] = count
        if count:
            issues.append(f"软关联孤儿 {key}: {count}")
    unknown_asset_sources = _count_query(
        conn,
        """
        SELECT COUNT(*) FROM assets
        WHERE source_id IS NOT NULL
          AND source_type NOT IN ('review', 'feedback', 'experiment', 'opportunity')
        """,
    )
    counts["assets.source_id.unknown_type"] = unknown_asset_sources
    if unknown_asset_sources:
        issues.append(
            f"软关联类型无效 assets.source_id: {unknown_asset_sources}"
        )

    suggestions = conn.execute(
        "SELECT id, user_id, suggested_payload FROM inbox_suggestions"
    ).fetchall()
    payload_orphans = 0
    payload_targets = {
        "goal_id": "goals",
        "project_id": "projects",
        "opportunity_id": "opportunities",
        "source_review_id": "reviews",
    }
    for suggestion in suggestions:
        try:
            payload = json.loads(suggestion["suggested_payload"] or "{}")
        except (TypeError, json.JSONDecodeError):
            payload_orphans += 1
            continue
        if not isinstance(payload, dict):
            payload_orphans += 1
            continue
        for field, target in payload_targets.items():
            value = payload.get(field)
            if value in (None, ""):
                continue
            try:
                target_id = int(value)
            except (TypeError, ValueError):
                payload_orphans += 1
                break
            if not conn.execute(
                f"SELECT 1 FROM {_quote(target)} WHERE id = ? AND user_id = ?",
                (target_id, suggestion["user_id"]),
            ).fetchone():
                payload_orphans += 1
                break
        else:
            related_type = payload.get("related_type")
            related_id = payload.get("related_id")
            related_targets = {
                "opportunity": "opportunities",
                "experiment": "experiments",
                "project": "projects",
                "asset": "assets",
                "review": "reviews",
            }
            if related_id not in (None, ""):
                if related_type not in related_targets:
                    payload_orphans += 1
                    continue
                try:
                    target_id = int(related_id)
                except (TypeError, ValueError):
                    payload_orphans += 1
                    continue
                if not conn.execute(
                    f"SELECT 1 FROM {_quote(related_targets[related_type])} "
                    "WHERE id = ? AND user_id = ?",
                    (target_id, suggestion["user_id"]),
                ).fetchone():
                    payload_orphans += 1
    counts["inbox_suggestions.suggested_payload"] = payload_orphans
    if payload_orphans:
        issues.append(f"软关联孤儿 inbox suggested_payload: {payload_orphans}")
    return counts, issues


def verify_migration(source_path, staged_path):
    source_path = Path(source_path).resolve()
    staged_path = Path(staged_path).resolve()
    if source_path == staged_path:
        raise VerificationError(["源库与 staged 库不能是同一路径"])
    if not source_path.is_file() or not staged_path.is_file():
        raise VerificationError(["源库或 staged 库不存在"])

    source = _connect_readonly(source_path)
    try:
        validate_legacy_source(source)
    except MigrationError as exc:
        raise VerificationError([str(exc)]) from exc
    finally:
        source.close()

    conn = _connect_readonly(staged_path)
    issues = []
    report = {
        "ok": False,
        "source": str(source_path),
        "staged": str(staged_path),
        "tables": {},
    }
    try:
        conn.execute("ATTACH DATABASE ? AS legacy", (_readonly_uri(source_path),))
        conn.execute("BEGIN")
        validate_legacy_source_attached = []
        legacy_tables = _table_names(conn, "legacy")
        missing = set(database.PERSONAL_DATA_TABLES) - legacy_tables
        if missing:
            validate_legacy_source_attached.append(
                "legacy 缺少业务表：" + ", ".join(sorted(missing))
            )
        issues.extend(validate_legacy_source_attached)

        users = conn.execute(
            "SELECT id, role, is_active FROM users ORDER BY id"
        ).fetchall()
        admins = [row for row in users if row["role"] == "admin"]
        active_admins = [
            row for row in admins if int(row["is_active"]) == 1
        ]
        if len(users) != 1 or len(admins) != 1 or len(active_admins) != 1:
            issues.append("staged users 必须且只能包含唯一启用的 admin")
            admin_id = int(admins[0]["id"]) if admins else -1
        else:
            admin_id = int(admins[0]["id"])
        report["users_total"] = len(users)
        report["active_admins"] = len(active_admins)
        report["admin_id"] = admin_id
        users_sequence = _sequence_value(conn, "users", "main")
        report["users_sequence"] = users_sequence
        if users_sequence != admin_id:
            issues.append("users sqlite_sequence 不正确")

        if int(conn.execute("PRAGMA user_version").fetchone()[0]) != database.SCHEMA_USER_VERSION:
            issues.append("staged PRAGMA user_version 不正确")

        for table in database.PERSONAL_DATA_TABLES:
            columns = LEGACY_V214_COLUMNS[table]
            old_count = _count_query(conn, f"SELECT COUNT(*) FROM legacy.{_quote(table)}")
            new_count = _count_query(
                conn,
                f"SELECT COUNT(*) FROM main.{_quote(table)} WHERE user_id = ?",
                (admin_id,),
            )
            null_count = _count_query(
                conn,
                f"SELECT COUNT(*) FROM main.{_quote(table)} WHERE user_id IS NULL",
            )
            other_owner_count = _count_query(
                conn,
                f"SELECT COUNT(*) FROM main.{_quote(table)} WHERE user_id != ?",
                (admin_id,),
            )
            old_minus_new = _except_count(
                conn, "legacy", "main", table, columns, admin_id
            )
            new_minus_old = _except_count(
                conn, "legacy", "main", table, columns, admin_id, reverse=True
            )
            missing_ids = _except_count(
                conn, "legacy", "main", table, ("id",), admin_id
            )
            source_seq = _sequence_value(conn, table, "legacy")
            staged_seq = _sequence_value(conn, table, "main")
            max_id = conn.execute(
                f"SELECT MAX(id) FROM main.{_quote(table)}"
            ).fetchone()[0]
            max_id = int(max_id or 0)
            table_report = {
                "legacy_count": old_count,
                "staged_admin_count": new_count,
                "null_user_id": null_count,
                "other_owner_count": other_owner_count,
                "legacy_except_staged": old_minus_new,
                "staged_except_legacy": new_minus_old,
                "missing_primary_keys": missing_ids,
                "legacy_sequence": source_seq,
                "staged_sequence": staged_seq,
                "max_id": max_id,
            }
            report["tables"][table] = table_report
            if old_count != new_count:
                issues.append(f"{table} row count 不一致")
            if null_count or other_owner_count:
                issues.append(f"{table} 所有权验证失败")
            if old_minus_new or new_minus_old or missing_ids:
                issues.append(f"{table} 双向 EXCEPT/主键验证失败")
            if source_seq != staged_seq or (staged_seq is not None and staged_seq < max_id):
                issues.append(f"{table} sqlite_sequence 不正确")

            staged_columns = {
                row["name"]: row
                for row in conn.execute(
                    f"PRAGMA main.table_info({_quote(table)})"
                ).fetchall()
            }
            user_column = staged_columns.get("user_id")
            if user_column is None or int(user_column["notnull"]) != 1:
                issues.append(f"{table}.user_id 不是 NOT NULL")
            foreign_keys = conn.execute(
                f"PRAGMA main.foreign_key_list({_quote(table)})"
            ).fetchall()
            if not any(
                row["from"] == "user_id" and row["table"] == "users"
                for row in foreign_keys
            ):
                issues.append(f"{table}.user_id 缺少 users 外键")
            indexes = conn.execute(
                f"PRAGMA main.index_list({_quote(table)})"
            ).fetchall()
            has_user_index = False
            for index in indexes:
                index_columns = conn.execute(
                    f'PRAGMA main.index_info("{index["name"]}")'
                ).fetchall()
                if index_columns and index_columns[0]["name"] == "user_id":
                    has_user_index = True
                    break
            if not has_user_index:
                issues.append(f"{table}.user_id 缺少前导索引")

        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        report["integrity_check"] = integrity
        report["foreign_key_check_rows"] = len(foreign_key_rows)
        if integrity != "ok":
            issues.append(f"staged integrity_check 失败：{integrity}")
        if foreign_key_rows:
            issues.append(f"staged foreign_key_check 返回 {len(foreign_key_rows)} 行")

        hard_counts, hard_issues = _verify_hard_relations(conn)
        report["hard_orphans"] = hard_counts
        issues.extend(hard_issues)
        soft_counts, soft_issues = _verify_soft_relations(conn, admin_id)
        report["soft_orphans"] = soft_counts
        issues.extend(soft_issues)
        report["issues"] = issues
        report["ok"] = not issues
        if issues:
            raise VerificationError(issues, report)
        return report
    finally:
        conn.close()
