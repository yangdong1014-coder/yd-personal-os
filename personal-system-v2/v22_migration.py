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

# Reuses exact 13-column contract matching database_artifacts.V22_USERS_COLUMNS
V22_USERS_COLUMNS = (
    "id",
    "username",
    "email",
    "password_hash",
    "role",
    "is_active",
    "must_change_password",
    "auth_version",
    "failed_login_count",
    "locked_until",
    "last_login_at",
    "created_at",
    "updated_at",
)


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


def _readonly_uri(path, immutable=True):
    uri = Path(path).resolve().as_uri()
    params = ["mode=ro"]
    if immutable:
        params.append("immutable=1")
    return f"{uri}?{'&'.join(params)}"


def _connect_readonly(path, immutable=True):
    conn = sqlite3.connect(_readonly_uri(path, immutable=immutable), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
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


ASSET_SOURCE_TARGETS = {
    "review": "reviews",
    "feedback": "feedback_items",
    "experiment": "experiments",
    "opportunity": "opportunities",
}


def _copy_table(source, staged, table, admin_id, repaired_orphans=None):
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
        tuples_to_insert = []
        for row in rows:
            row_dict = dict(row)
            if table == "assets":
                source_type = (row_dict.get("source_type") or "").strip()
                source_id = row_dict.get("source_id")
                if source_type in ASSET_SOURCE_TARGETS and source_id is not None and source_id != "":
                    target_table = ASSET_SOURCE_TARGETS[source_type]
                    exists = source.execute(
                        f"SELECT 1 FROM {_quote(target_table)} WHERE id = ?",
                        (source_id,),
                    ).fetchone()
                    if not exists:
                        row_dict["source_type"] = ""
                        row_dict["source_id"] = None
                        if repaired_orphans is not None:
                            repaired_orphans.append({
                                "table": "assets",
                                "record_id": int(row_dict["id"]),
                                "original_source_type": row["source_type"],
                                "original_source_id": row["source_id"],
                                "remediation": "cleared_to_null",
                                "reason": f"referenced_{source_type}_not_found",
                            })
            tuples_to_insert.append(
                tuple(row_dict[column] for column in source_columns) + (admin_id,)
            )
        staged.executemany(
            f"INSERT INTO {_quote(table)} ({insert_columns}) VALUES ({placeholders})",
            tuples_to_insert,
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
        repaired_orphans = []
        for table in database.PERSONAL_DATA_TABLES:
            row_counts[table] = _copy_table(
                source, staged, table, admin_id, repaired_orphans=repaired_orphans
            )
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
            "repaired_orphans": repaired_orphans,
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


def _verify_hard_relations(conn, staged_tables=None):
    counts = {}
    issues = []
    if staged_tables is None:
        staged_tables = _table_names(conn, "main")
    for label, child, child_column, parent in HARD_RELATIONS:
        if child not in staged_tables or parent not in staged_tables:
            counts[label] = 0
            continue
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


def _verify_soft_relations(conn, admin_id, staged_tables=None):
    issues = []
    counts = {}
    if staged_tables is None:
        staged_tables = _table_names(conn, "main")
    for table, targets in SOFT_RELATION_TARGETS.items():
        if table not in staged_tables:
            continue
        for related_type, target in targets.items():
            if target not in staged_tables:
                continue
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

    if "positioning_goal_action" in staged_tables and "goals" in staged_tables:
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
    if "assets" in staged_tables:
        for source_type, target in asset_source_targets.items():
            if target not in staged_tables:
                continue
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

    if "inbox_suggestions" in staged_tables:
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
                if target not in staged_tables or not conn.execute(
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
                    if related_type not in related_targets or related_targets[related_type] not in staged_tables:
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

    diagnostics = {
        "legacy_source": {},
        "tables": {},
        "except_checks": {},
        "sequence_checks": {},
        "hard_orphans": {},
    }

    # U-01 ~ U-04: Legacy SOURCE diagnostics only (NON-BLOCKING)
    source = _connect_readonly(source_path, immutable=True)
    try:
        src_tables = _table_names(source)
        diagnostics["legacy_source"]["has_users_table"] = ("users" in src_tables)  # U-01
        col_mismatches = {}
        tables_with_user_id = []
        for table in database.PERSONAL_DATA_TABLES:
            if table in src_tables:
                src_cols = _table_columns(source, table)
                expected_src_cols = LEGACY_V214_COLUMNS.get(table, ())
                if set(src_cols) != set(expected_src_cols) or len(src_cols) != len(expected_src_cols):
                    col_mismatches[table] = {"actual": src_cols, "expected": expected_src_cols}
                if "user_id" in src_cols:
                    tables_with_user_id.append(table)
        diagnostics["legacy_source"]["column_mismatches"] = col_mismatches  # U-02
        diagnostics["legacy_source"]["tables_with_user_id"] = tables_with_user_id  # U-03
        if "positioning_anchor" in src_tables:
            pa_cnt = source.execute("SELECT COUNT(*) FROM positioning_anchor").fetchone()[0]
            diagnostics["legacy_source"]["positioning_anchor_count"] = int(pa_cnt)  # U-04
    finally:
        source.close()

    conn = _connect_readonly(staged_path, immutable=True)
    issues = []
    report = {
        "ok": False,
        "source": str(source_path),
        "staged": str(staged_path),
        "tables": {},
        "diagnostics": diagnostics,
    }
    try:
        conn.execute("ATTACH DATABASE ? AS legacy", (_readonly_uri(source_path, immutable=True),))
        conn.execute("BEGIN")

        # F-19: Physical integrity check on staged DB (blocking)
        integrity = conn.execute("PRAGMA main.integrity_check").fetchone()[0]
        report["integrity_check"] = integrity
        if integrity != "ok":
            issues.append(f"staged integrity_check 失败：{integrity}")

        # F-20: SQLite FK consistency check on staged DB (blocking)
        foreign_key_rows = conn.execute("PRAGMA main.foreign_key_check").fetchall()
        report["foreign_key_check_rows"] = len(foreign_key_rows)
        if foreign_key_rows:
            issues.append(f"staged foreign_key_check 返回 {len(foreign_key_rows)} 行")

        # F-21: Schema user_version (blocking)
        user_version = int(conn.execute("PRAGMA main.user_version").fetchone()[0])
        report["user_version"] = user_version
        if user_version != database.SCHEMA_USER_VERSION:
            issues.append("staged PRAGMA user_version 不正确")

        # F-22: Exact Table Set: non-internal tables == set(PERSONAL_DATA_TABLES) | {"users"} (blocking)
        staged_tables = _table_names(conn, "main")
        expected_tables = set(database.PERSONAL_DATA_TABLES) | {"users"}
        missing_tables = expected_tables - staged_tables
        extra_tables = staged_tables - expected_tables
        report["staged_tables"] = sorted(staged_tables)
        report["missing_tables"] = sorted(missing_tables)
        report["extra_tables"] = sorted(extra_tables)
        if missing_tables:
            issues.append(
                "staged 缺少业务表/用户表：" + ", ".join(sorted(missing_tables))
            )
        if extra_tables:
            issues.append(
                "staged 存在多余未授权表：" + ", ".join(sorted(extra_tables))
            )

        # F-25: users exact 13-column contract (blocking)
        if "users" in staged_tables:
            users_info = conn.execute("PRAGMA main.table_info(users)").fetchall()
            users_columns = tuple(row["name"] for row in users_info)
            report["users_columns_count"] = len(users_columns)
            if users_columns != V22_USERS_COLUMNS:
                issues.append(
                    f"users 表字段契约不匹配：actual={users_columns}, expected={V22_USERS_COLUMNS}"
                )

            # F-26: Single-admin bootstrap invariant (blocking)
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

            # F-27: Users sequence invariant (blocking)
            users_sequence = _sequence_value(conn, "users", "main")
            report["users_sequence"] = users_sequence
            if users_sequence != admin_id:
                issues.append("users sqlite_sequence 不正确")
        else:
            admin_id = -1
            report["users_total"] = 0
            report["active_admins"] = 0
            report["admin_id"] = -1
            report["users_sequence"] = None

        legacy_tables = _table_names(conn, "legacy")

        for table in database.PERSONAL_DATA_TABLES:
            if table not in staged_tables:
                continue

            # F-23: Exact business column contract (blocking)
            table_info_rows = conn.execute(
                f"PRAGMA main.table_info({_quote(table)})"
            ).fetchall()
            staged_columns = {row["name"]: row for row in table_info_rows}
            actual_cols = set(staged_columns.keys())
            expected_cols = set(LEGACY_V214_COLUMNS[table]) | {"user_id"}
            if actual_cols != expected_cols or len(table_info_rows) != len(expected_cols):
                issues.append(
                    f"{table} 字段集合与权威契约不一致：actual={sorted(actual_cols)}, expected={sorted(expected_cols)}"
                )

            user_column = staged_columns.get("user_id")
            if user_column is None:
                issues.append(f"{table} 缺少 user_id 字段")
            else:
                col_type = (user_column["type"] or "").strip().upper()
                if col_type != "INTEGER":
                    issues.append(f"{table}.user_id 类型不是 INTEGER (actual={col_type})")
                if int(user_column["notnull"]) != 1:
                    issues.append(f"{table}.user_id 不是 NOT NULL")

            # F-24: Corrected authoritative FK existence check (blocking)
            foreign_keys = conn.execute(
                f"PRAGMA main.foreign_key_list({_quote(table)})"
            ).fetchall()
            has_user_fk = any(
                row["from"] == "user_id"
                and row["table"] == "users"
                and row["to"] == "id"
                for row in foreign_keys
            )
            if not has_user_fk:
                issues.append(f"{table}.user_id 缺少指向 users(id) 的外键")

            # Row counts & ownership
            columns = LEGACY_V214_COLUMNS[table]
            if table in legacy_tables:
                old_count = _count_query(conn, f"SELECT COUNT(*) FROM legacy.{_quote(table)}")
            else:
                old_count = 0
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

            if table == "assets" and table in legacy_tables:
                legacy_orphans = []
                for source_type, target in ASSET_SOURCE_TARGETS.items():
                    orphan_rows = conn.execute(
                        f"""
                        SELECT id, source_type, source_id FROM legacy.assets
                        WHERE source_type = ? AND source_id IS NOT NULL
                          AND NOT EXISTS (
                            SELECT 1 FROM legacy.{_quote(target)} parent
                            WHERE parent.id = legacy.assets.source_id
                          )
                        """,
                        (source_type,),
                    ).fetchall()
                    for r in orphan_rows:
                        legacy_orphans.append(r)

                if legacy_orphans:
                    orphan_ids = tuple(int(r["id"]) for r in legacy_orphans)
                    other_cols = tuple(
                        c for c in columns if c not in ("source_type", "source_id")
                    )
                    other_cols_sql = ", ".join(_quote(c) for c in other_cols)

                    for r in legacy_orphans:
                        staged_row = conn.execute(
                            f"SELECT source_type, source_id, {other_cols_sql} FROM main.assets WHERE id = ? AND user_id = ?",
                            (r["id"], admin_id),
                        ).fetchone()
                        legacy_row = conn.execute(
                            f"SELECT {other_cols_sql} FROM legacy.assets WHERE id = ?",
                            (r["id"],),
                        ).fetchone()
                        if (
                            staged_row is None
                            or (staged_row["source_type"] or "") != ""
                            or staged_row["source_id"] is not None
                            or tuple(staged_row[c] for c in other_cols)
                            != tuple(legacy_row[c] for c in other_cols)
                        ):
                            issues.append(f"assets 孤儿清洗验证失败 id={r['id']}")

                    placeholders = ", ".join("?" for _ in orphan_ids)
                    column_sql = ", ".join(_quote(c) for c in columns)
                    old_minus_new = _count_query(
                        conn,
                        f"""
                        SELECT COUNT(*) FROM (
                            SELECT {column_sql} FROM legacy.assets WHERE id NOT IN ({placeholders})
                            EXCEPT
                            SELECT {column_sql} FROM main.assets WHERE user_id = ? AND id NOT IN ({placeholders})
                        )
                        """,
                        orphan_ids + (admin_id,) + orphan_ids,
                    )
                    new_minus_old = _count_query(
                        conn,
                        f"""
                        SELECT COUNT(*) FROM (
                            SELECT {column_sql} FROM main.assets WHERE user_id = ? AND id NOT IN ({placeholders})
                            EXCEPT
                            SELECT {column_sql} FROM legacy.assets WHERE id NOT IN ({placeholders})
                        )
                        """,
                        (admin_id,) + orphan_ids + orphan_ids,
                    )
                    report["repaired_orphans"] = [
                        {
                            "table": "assets",
                            "record_id": int(r["id"]),
                            "original_source_type": r["source_type"],
                            "original_source_id": r["source_id"],
                            "remediation": "cleared_to_null",
                            "reason": f"referenced_{r['source_type']}_not_found",
                        }
                        for r in legacy_orphans
                    ]
                else:
                    old_minus_new = _except_count(
                        conn, "legacy", "main", table, columns, admin_id
                    )
                    new_minus_old = _except_count(
                        conn, "legacy", "main", table, columns, admin_id, reverse=True
                    )
            else:
                if table in legacy_tables:
                    old_minus_new = _except_count(
                        conn, "legacy", "main", table, columns, admin_id
                    )
                    new_minus_old = _except_count(
                        conn, "legacy", "main", table, columns, admin_id, reverse=True
                    )
                else:
                    old_minus_new = None
                    new_minus_old = None

            missing_ids = (
                _except_count(conn, "legacy", "main", table, ("id",), admin_id)
                if table in legacy_tables
                else None
            )
            source_seq = _sequence_value(conn, table, "legacy") if table in legacy_tables else None
            staged_seq = _sequence_value(conn, table, "main")
            max_id_row = conn.execute(
                f"SELECT MAX(id) FROM main.{_quote(table)}"
            ).fetchone()[0]
            max_id = int(max_id_row or 0)

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

            # F-29: Dual-DB row count preservation (blocking)
            if old_count != new_count:
                issues.append(f"{table} row count 不一致")

            # F-30: Tenant ownership closure (blocking)
            if null_count or other_owner_count:
                issues.append(f"{table} 所有权验证失败")

            # U-05: Bidirectional EXCEPT / missing IDs (DIAGNOSTIC ONLY - DO NOT append to issues)
            diagnostics["except_checks"][table] = {
                "legacy_except_staged": old_minus_new,
                "staged_except_legacy": new_minus_old,
                "missing_primary_keys": missing_ids,
            }

            # U-06: Business-table sequence consistency (DIAGNOSTIC ONLY - DO NOT append to issues)
            diagnostics["sequence_checks"][table] = {
                "legacy_sequence": source_seq,
                "staged_sequence": staged_seq,
                "max_id": max_id,
                "sequence_matches": (source_seq == staged_seq),
            }

            # U-08: Leading index requirement is REMOVED entirely!

        # F-28: Soft relation verification (blocking, dangling non-null only, no null_gap)
        soft_counts, soft_issues = _verify_soft_relations(
            conn, admin_id, staged_tables=staged_tables
        )
        report["soft_orphans"] = soft_counts
        issues.extend(soft_issues)

        # U-07: Explicit hard-relation orphan / cross-user SQL (DIAGNOSTIC ONLY - DO NOT append to issues)
        hard_counts, hard_issues = _verify_hard_relations(
            conn, staged_tables=staged_tables
        )
        report["hard_orphans"] = hard_counts
        diagnostics["hard_orphans"] = {
            "counts": hard_counts,
            "diagnostics": hard_issues,
        }

        report["issues"] = issues
        report["ok"] = not issues
        if issues:
            raise VerificationError(issues, report)
        return report
    finally:
        conn.close()


def _is_strictly_absent(path):
    path = Path(path)
    return not path.exists() and not path.is_symlink()


def audit_preflight(
    source_path,
    migration_path,
    *,
    staged_dest=None,
    manifest_path=None,
    instance_root=None,
    databases_root=None,
    expected_source_size=None,
    expected_source_sha256=None,
    expected_migration_size=None,
    expected_migration_sha256=None,
    strict_shadow_layout=False,
    stat_resolver=None,
):
    """Execute preflight safety audits (F-00a ~ F-00f, F-01 ~ F-18)."""
    source_path = Path(source_path).resolve()
    migration_path = Path(migration_path).resolve()
    pre_issues = []
    pre_snapshots = {}

    def _get_stat(p):
        if stat_resolver is not None:
            return stat_resolver(p)
        return p.stat()

    # F-00a ~ F-00f: Parent directory and instance layout safety
    if strict_shadow_layout or instance_root is not None or databases_root is not None:
        if databases_root is not None:
            db_root = Path(databases_root).resolve()
            if not db_root.is_dir() or db_root.is_symlink():
                pre_issues.append(f"F-00a 失败: 数据库根目录无效或为符号链接: {db_root}")
            elif os.name != "nt":
                import grp
                import pwd
                import stat as stat_mod
                try:
                    st = _get_stat(db_root)
                    owner = pwd.getpwuid(st.st_uid).pw_name
                    group = grp.getgrgid(st.st_gid).gr_name
                    if owner != "root" or group != "root":
                        pre_issues.append(f"F-00a 失败: {db_root} 属主不是 root:root (actual={owner}:{group})")
                    if bool(st.st_mode & 0o022):
                        pre_issues.append(f"F-00a 失败: {db_root} 包含组写或全局写权限")
                except Exception as exc:
                    pre_issues.append(f"F-00a 失败: 无法验证 {db_root} 权限: {exc}")

        if instance_root is not None:
            inst_root = Path(instance_root).resolve()
            dir_specs = [
                ("F-00b", inst_root, "root", "root", 0o755),
                ("F-00c", inst_root / "source", "root", "root", 0o700),
                ("F-00d", inst_root / "migration", "root", "root", 0o700),
                ("F-00e", inst_root / "manifests", "root", "psy", 0o750),
                ("F-00f", inst_root / "staged", "psy", "psy", 0o700),
            ]
            for fid, dpath, exp_u, exp_g, exp_mode in dir_specs:
                if not dpath.is_dir() or dpath.is_symlink():
                    pre_issues.append(f"{fid} 失败: 目录不存在或为符号链接: {dpath}")
                elif os.name != "nt":
                    import grp
                    import pwd
                    import stat as stat_mod
                    try:
                        st = _get_stat(dpath)
                        owner = pwd.getpwuid(st.st_uid).pw_name
                        group = grp.getgrgid(st.st_gid).gr_name
                        mode = stat_mod.S_IMODE(st.st_mode)
                        if owner != exp_u or group != exp_g:
                            pre_issues.append(f"{fid} 失败: {dpath.name} 属主应为 {exp_u}:{exp_g} (actual={owner}:{group})")
                        if mode != exp_mode:
                            pre_issues.append(f"{fid} 失败: {dpath.name} 权限应为 {oct(exp_mode)} (actual={oct(mode)})")
                    except Exception as exc:
                        pre_issues.append(f"{fid} 失败: 无法验证 {dpath} 权限: {exc}")

    # F-01 ~ F-08: Migration artifact leaf checks
    if not migration_path.is_file() or migration_path.is_symlink():
        pre_issues.append(f"F-01 失败: 迁移制品不是普通文件或为符号链接: {migration_path}")
    else:
        # F-02, F-03 (POSIX permissions if strict or on Linux)
        if (strict_shadow_layout or os.name != "nt") and os.name != "nt":
            import grp
            import pwd
            import stat as stat_mod
            try:
                m_st = _get_stat(migration_path)
                owner = pwd.getpwuid(m_st.st_uid).pw_name
                group = grp.getgrgid(m_st.st_gid).gr_name
                mode = stat_mod.S_IMODE(m_st.st_mode)
                if owner != "root" or group != "root" or mode != 0o600:
                    pre_issues.append(f"F-02 失败: 迁移制品属主权限应为 root:root 600 (actual={owner}:{group} {oct(mode)})")
                if bool(m_st.st_mode & 0o022):
                    pre_issues.append("F-03 失败: 迁移制品禁止组写与全局写")
            except Exception as exc:
                pre_issues.append(f"F-02/F-03 检查失败: {exc}")

        # F-04: 16-byte magic
        try:
            with migration_path.open("rb") as stream:
                magic = stream.read(16)
            if magic != b"SQLite format 3\0":
                pre_issues.append(f"F-04 失败: 迁移制品魔数不正确: {magic!r}")
        except Exception as exc:
            pre_issues.append(f"F-04 失败: 无法读取迁移制品魔数: {exc}")

        # F-05: Size baseline
        try:
            m_size = _get_stat(migration_path).st_size
            if expected_migration_size is not None and m_size != expected_migration_size:
                pre_issues.append(f"F-05 失败: 迁移制品大小不符: actual={m_size}, expected={expected_migration_size}")
        except Exception as exc:
            pre_issues.append(f"F-05 检查失败: {exc}")

        # F-06: SHA-256 baseline
        try:
            m_hash = _sha256(migration_path)
            if expected_migration_sha256 is not None and m_hash != expected_migration_sha256:
                pre_issues.append(f"F-06 失败: 迁移制品 SHA-256 不符: actual={m_hash}, expected={expected_migration_sha256}")
        except Exception as exc:
            pre_issues.append(f"F-06 检查失败: {exc}")

        # F-07: Physical identity snapshot
        try:
            m_st = _get_stat(migration_path)
            pre_snapshots["migration"] = {
                "stat": (m_st.st_dev, m_st.st_ino, m_st.st_size, getattr(m_st, "st_mtime_ns", int(m_st.st_mtime * 1e9))),
                "sha256": _sha256(migration_path),
            }
        except Exception as exc:
            pre_issues.append(f"F-07 失败: 无法记录迁移制品快照: {exc}")

    # F-08: PRE migration sidecars absent
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(migration_path) + suffix)
        if not _is_strictly_absent(sidecar):
            pre_issues.append(f"F-08 失败: 迁移目录副产物存在: {sidecar.name}")

    # F-09 ~ F-15: Source database leaf checks
    if not source_path.is_file() or source_path.is_symlink():
        pre_issues.append(f"F-09 失败: 源数据库不是普通文件或为符号链接: {source_path}")
    else:
        # F-10: POSIX permissions
        if (strict_shadow_layout or os.name != "nt") and os.name != "nt":
            import grp
            import pwd
            import stat as stat_mod
            try:
                s_st = _get_stat(source_path)
                owner = pwd.getpwuid(s_st.st_uid).pw_name
                group = grp.getgrgid(s_st.st_gid).gr_name
                mode = stat_mod.S_IMODE(s_st.st_mode)
                if owner != "root" or group != "root" or mode != 0o400:
                    pre_issues.append(f"F-10 失败: 源数据库属主权限应为 root:root 400 (actual={owner}:{group} {oct(mode)})")
            except Exception as exc:
                pre_issues.append(f"F-10 检查失败: {exc}")

        # F-11: 16-byte magic
        try:
            with source_path.open("rb") as stream:
                magic = stream.read(16)
            if magic != b"SQLite format 3\0":
                pre_issues.append(f"F-11 失败: 源数据库魔数不正确: {magic!r}")
        except Exception as exc:
            pre_issues.append(f"F-11 失败: 无法读取源数据库魔数: {exc}")

        # F-12: Size baseline
        try:
            s_size = _get_stat(source_path).st_size
            if expected_source_size is not None and s_size != expected_source_size:
                pre_issues.append(f"F-12 失败: 源数据库大小不符: actual={s_size}, expected={expected_source_size}")
        except Exception as exc:
            pre_issues.append(f"F-12 检查失败: {exc}")

        # F-13: SHA-256 baseline
        try:
            s_hash = _sha256(source_path)
            if expected_source_sha256 is not None and s_hash != expected_source_sha256:
                pre_issues.append(f"F-13 失败: 源数据库 SHA-256 不符: actual={s_hash}, expected={expected_source_sha256}")
        except Exception as exc:
            pre_issues.append(f"F-13 检查失败: {exc}")

        # F-14: Physical identity snapshot
        try:
            s_st = _get_stat(source_path)
            pre_snapshots["source"] = {
                "stat": (s_st.st_dev, s_st.st_ino, s_st.st_size, getattr(s_st, "st_mtime_ns", int(s_st.st_mtime * 1e9))),
                "sha256": _sha256(source_path),
            }
        except Exception as exc:
            pre_issues.append(f"F-14 失败: 无法记录源数据库快照: {exc}")

    # F-15: PRE source sidecars absent
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(source_path) + suffix)
        if not _is_strictly_absent(sidecar):
            pre_issues.append(f"F-15 失败: 源数据库副产物存在: {sidecar.name}")

    # F-16 ~ F-18: Staged and manifest absence checks
    if staged_dest is not None:
        s_dest = Path(staged_dest).resolve()
        if not _is_strictly_absent(s_dest):
            pre_issues.append(f"F-16 失败: STAGED_DB 严格不存在失败: {s_dest}")
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(s_dest) + suffix)
            if not _is_strictly_absent(sidecar):
                pre_issues.append(f"F-17 失败: STAGED 副产物存在: {sidecar.name}")

    if manifest_path is not None:
        m_path = Path(manifest_path).resolve()
        m_hash_path = Path(str(m_path) + ".sha256")
        if not _is_strictly_absent(m_path) or not _is_strictly_absent(m_hash_path):
            pre_issues.append(f"F-18 失败: Manifest 凭证严格不存在失败: {m_path}")

    pre_ok = (len(pre_issues) == 0)
    return pre_ok, pre_issues, pre_snapshots


def audit_postflight(source_path, migration_path, pre_snapshots, *, stat_resolver=None):
    """Execute guaranteed physical postflight zero-mutation audits (F-31 ~ F-36).

    Does NOT reconnect to SQLite databases. Checks filesystem properties only.
    """
    source_path = Path(source_path).resolve()
    migration_path = Path(migration_path).resolve()
    post_issues = []

    def _get_stat(p):
        if stat_resolver is not None:
            return stat_resolver(p)
        return p.stat()

    # F-31: POST source stat unchanged
    if "source" in pre_snapshots:
        try:
            s_st = _get_stat(source_path)
            curr_s_stat = (s_st.st_dev, s_st.st_ino, s_st.st_size, getattr(s_st, "st_mtime_ns", int(s_st.st_mtime * 1e9)))
            if curr_s_stat != pre_snapshots["source"]["stat"]:
                post_issues.append("F-31 失败: POST 源库物理身份发生变化")
        except Exception as exc:
            post_issues.append(f"F-31 失败: 无法获取 POST 源库 stat: {exc}")

        # F-32: POST source SHA-256 unchanged
        try:
            curr_s_hash = _sha256(source_path)
            if curr_s_hash != pre_snapshots["source"]["sha256"]:
                post_issues.append("F-32 失败: POST 源库 SHA-256 哈希发生变化")
        except Exception as exc:
            post_issues.append(f"F-32 失败: 无法获取 POST 源库哈希: {exc}")

    # F-33: POST source sidecars absent
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(source_path) + suffix)
        if not _is_strictly_absent(sidecar):
            post_issues.append(f"F-33 失败: POST 源库检测到副产物: {sidecar.name}")

    # F-34: POST migration stat unchanged
    if "migration" in pre_snapshots:
        try:
            m_st = _get_stat(migration_path)
            curr_m_stat = (m_st.st_dev, m_st.st_ino, m_st.st_size, getattr(m_st, "st_mtime_ns", int(m_st.st_mtime * 1e9)))
            if curr_m_stat != pre_snapshots["migration"]["stat"]:
                post_issues.append("F-34 失败: POST 迁移库物理身份发生变化")
        except Exception as exc:
            post_issues.append(f"F-34 失败: 无法获取 POST 迁移库 stat: {exc}")

        # F-35: POST migration SHA-256 unchanged
        try:
            curr_m_hash = _sha256(migration_path)
            if curr_m_hash != pre_snapshots["migration"]["sha256"]:
                post_issues.append("F-35 失败: POST 迁移库 SHA-256 哈希发生变化")
        except Exception as exc:
            post_issues.append(f"F-35 失败: 无法获取 POST 迁移库哈希: {exc}")

    # F-36: POST migration sidecars absent
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(migration_path) + suffix)
        if not _is_strictly_absent(sidecar):
            post_issues.append(f"F-36 失败: POST 迁移库检测到副产物: {sidecar.name}")

    post_ok = (len(post_issues) == 0)
    return post_ok, post_issues


def verify_authoritative_envelope(
    source_path,
    migration_path,
    *,
    staged_dest=None,
    manifest_path=None,
    instance_root=None,
    databases_root=None,
    expected_source_size=None,
    expected_source_sha256=None,
    expected_migration_size=None,
    expected_migration_sha256=None,
    strict_shadow_layout=False,
    stat_resolver=None,
    db_opener=None,
):
    """Execute complete authoritative verification envelope: PRE + SEMANTIC + POST.

    Implements mechanical combined verdict:
    pre_ok = path_safety_ok AND leaf_pre_ok AND staged_manifest_absence_ok
    connection_safety_ok = readonly_connection_established AND execution_safety_controls_ok
    semantic_ok = all F-19~F-30 authoritative blocking predicates pass
    post_ok = all required F-31~F-36 post audits pass
    overall_ok = pre_ok AND connection_safety_ok AND semantic_ok AND post_ok
    raw_ok = overall_ok
    raw_exit = 0 if overall_ok else 1
    """
    source_path = Path(source_path).resolve()
    migration_path = Path(migration_path).resolve()
    if staged_dest is not None:
        staged_dest = Path(staged_dest).resolve()
    if manifest_path is not None:
        manifest_path = Path(manifest_path).resolve()
    if instance_root is not None:
        instance_root = Path(instance_root).resolve()
    if databases_root is not None:
        databases_root = Path(databases_root).resolve()

    # Step 1: PRE Audit (F-00a ~ F-00f, F-01 ~ F-18)
    pre_ok, pre_issues, pre_snapshots = audit_preflight(
        source_path,
        migration_path,
        staged_dest=staged_dest,
        manifest_path=manifest_path,
        instance_root=instance_root,
        databases_root=databases_root,
        expected_source_size=expected_source_size,
        expected_source_sha256=expected_source_sha256,
        expected_migration_size=expected_migration_size,
        expected_migration_sha256=expected_migration_sha256,
        strict_shadow_layout=strict_shadow_layout,
        stat_resolver=stat_resolver,
    )

    if not pre_ok:
        # PRE failure before any DB open:
        # - raw failure
        # - DO NOT open DB
        # - DO NOT execute semantic core
        # - DO NOT open DB merely to perform POST audit
        return {
            "ok": False,
            "raw_ok": False,
            "raw_exit": 1,
            "pre_ok": False,
            "connection_safety_ok": False,
            "semantic_ok": False,
            "post_ok": False,
            "issues": pre_issues,
            "authoritative_issues": pre_issues,
            "pre_issues": pre_issues,
            "connection_safety_issues": [],
            "semantic_issues": [],
            "post_issues": [],
            "diagnostics": {},
            "report": None,
        }

    # Step 2: Connection & Semantic Core with guaranteed finally POST audit
    connection_safety_ok = False
    semantic_ok = False
    semantic_report = {}
    semantic_issues = []
    conn_safety_issues = []
    post_ok = False
    post_issues = []

    try:
        try:
            if db_opener is not None:
                semantic_report = db_opener(source_path, migration_path)
            else:
                semantic_report = verify_migration(source_path, migration_path)
            connection_safety_ok = True
            semantic_ok = semantic_report.get("ok", False)
            semantic_issues = semantic_report.get("issues", [])
        except VerificationError as exc:
            connection_safety_ok = True
            semantic_ok = False
            semantic_report = exc.report or {}
            semantic_issues = exc.issues
        except Exception as exc:
            connection_safety_ok = False
            semantic_ok = False
            conn_safety_issues.append(f"数据库只读安全连接建立失败: {exc}")
    finally:
        # Once DB open/connection attempt has begun, physical POST zero-mutation
        # audit must execute through guaranteed finally-style control flow.
        post_ok, post_issues = audit_postflight(
            source_path,
            migration_path,
            pre_snapshots,
            stat_resolver=stat_resolver,
        )

    # Step 3: Mechanical Combined Verdict
    overall_ok = bool(pre_ok and connection_safety_ok and semantic_ok and post_ok)
    all_issues = pre_issues + conn_safety_issues + semantic_issues + post_issues

    return {
        "ok": overall_ok,
        "raw_ok": overall_ok,
        "raw_exit": 0 if overall_ok else 1,
        "pre_ok": pre_ok,
        "connection_safety_ok": connection_safety_ok,
        "semantic_ok": semantic_ok,
        "post_ok": post_ok,
        "issues": all_issues,
        "authoritative_issues": all_issues,
        "pre_issues": pre_issues,
        "connection_safety_issues": conn_safety_issues,
        "semantic_issues": semantic_issues,
        "post_issues": post_issues,
        "diagnostics": semantic_report.get("diagnostics", {}),
        "report": semantic_report,
    }
