"""Fail-closed production entry point for PSY v2.2.

This module never creates or migrates a database. It validates an explicitly
selected current v2.2 database before importing the WSGI application.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sqlite3
from pathlib import Path

import config
from v22_migration import _verify_soft_relations


class ProductionPreflightError(RuntimeError):
    """Raised when the runtime is not safe enough to serve production traffic."""


_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ProductionPreflightError("无法读取当前生产入口") from exc
    return digest.hexdigest()


def _validate_release_context() -> dict:
    """Require proof that the launcher selected this exact release."""
    required = {
        "PSY_ACTIVE_RELEASE_POINTER": "active release pointer",
        "PSY_EXPECTED_APP_VERSION": "expected application version",
        "PSY_EXPECTED_GIT_COMMIT": "expected Git commit",
        "PSY_RELEASE_DESCRIPTOR_SHA256": "release descriptor hash",
        "PSY_RELEASE_ID": "release id",
        "PSY_RELEASE_CODE_ROOT": "release code root",
        "PSY_RELEASE_ENTRYPOINT_SHA256": "release entrypoint hash",
        "PSY_RELEASE_CONFIG_PATH": "release config path",
        "PSY_RELEASE_CONFIG_SHA256": "release config hash",
        "PSY_RELEASE_DATABASE_PATH": "release database path",
    }
    values = {key: os.environ.get(key, "").strip() for key in required}
    missing = [label for key, label in required.items() if not values[key]]
    if missing:
        raise ProductionPreflightError(
            "生产运行必须由 active-release launcher 启动，缺少："
            + ", ".join(missing)
        )
    if not values["PSY_EXPECTED_APP_VERSION"].startswith("v2.2"):
        raise ProductionPreflightError("active release 不是获准的 v2.2 应用")
    if not _COMMIT_RE.fullmatch(values["PSY_EXPECTED_GIT_COMMIT"]):
        raise ProductionPreflightError("active release Git commit 格式无效")
    for key in (
        "PSY_RELEASE_DESCRIPTOR_SHA256",
        "PSY_RELEASE_ENTRYPOINT_SHA256",
        "PSY_RELEASE_CONFIG_SHA256",
    ):
        if not _HASH_RE.fullmatch(values[key]):
            raise ProductionPreflightError("active release hash 格式无效")

    code_root = Path(values["PSY_RELEASE_CODE_ROOT"])
    if not code_root.is_absolute():
        raise ProductionPreflightError("active release code root 必须是绝对路径")
    try:
        code_root = code_root.resolve(strict=True)
    except OSError as exc:
        raise ProductionPreflightError("active release code root 不可访问") from exc
    if not code_root.is_dir() or code_root != Path(__file__).resolve().parent:
        raise ProductionPreflightError("运行入口与 active release code root 不一致")
    entrypoint = Path(__file__).resolve()
    if _sha256_file(entrypoint) != values["PSY_RELEASE_ENTRYPOINT_SHA256"]:
        raise ProductionPreflightError("运行入口与 release descriptor 不一致")
    config_path = Path(values["PSY_RELEASE_CONFIG_PATH"])
    if not config_path.is_absolute():
        raise ProductionPreflightError("active release config path 必须是绝对路径")
    try:
        config_path = config_path.resolve(strict=True)
    except OSError as exc:
        raise ProductionPreflightError("active release config path 不可访问") from exc
    if _sha256_file(config_path) != values["PSY_RELEASE_CONFIG_SHA256"]:
        raise ProductionPreflightError("运行配置与 release descriptor 不一致")
    database_path = Path(os.environ.get("YD_OS_DB_PATH", "")).resolve()
    selected_database_path = Path(values["PSY_RELEASE_DATABASE_PATH"])
    if not selected_database_path.is_absolute():
        raise ProductionPreflightError("active release database path 必须是绝对路径")
    if database_path != selected_database_path.resolve():
        raise ProductionPreflightError("YD_OS_DB_PATH 与 active release 选择不一致")
    try:
        from release_switch import ReleaseSwitchError, resolve_active_release

        selected = resolve_active_release(
            values["PSY_ACTIVE_RELEASE_POINTER"],
            expected_git_commit=values["PSY_EXPECTED_GIT_COMMIT"],
            expected_application_version=values["PSY_EXPECTED_APP_VERSION"],
            verify_immutable_database=False,
        )
    except ReleaseSwitchError as exc:
        raise ProductionPreflightError("active release 复验失败") from exc
    if (
        selected["descriptor_sha256"]
        != values["PSY_RELEASE_DESCRIPTOR_SHA256"]
        or selected["release_id"] != values["PSY_RELEASE_ID"]
        or Path(selected["application"]["code_root"]) != code_root
        or Path(selected["application"]["entrypoint"]) != entrypoint
        or Path(selected["application"]["config_path"]) != config_path
        or Path(selected["database"]["path"]) != database_path
        or selected["application"]["entrypoint_sha256"]
        != values["PSY_RELEASE_ENTRYPOINT_SHA256"]
        or selected["application"]["config_sha256"]
        != values["PSY_RELEASE_CONFIG_SHA256"]
    ):
        raise ProductionPreflightError("active release 与 launcher 选择不一致")
    return {
        "release_id": values["PSY_RELEASE_ID"],
        "application_version": values["PSY_EXPECTED_APP_VERSION"],
        "git_commit": values["PSY_EXPECTED_GIT_COMMIT"],
        "descriptor_sha256": values["PSY_RELEASE_DESCRIPTOR_SHA256"],
    }


def _resolve_database_path() -> Path:
    raw = os.environ.get("YD_OS_DB_PATH", "").strip()
    if not raw:
        raise ProductionPreflightError(
            "生产运行必须显式设置 YD_OS_DB_PATH，禁止回落到默认数据库"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise ProductionPreflightError("生产 YD_OS_DB_PATH 必须是绝对路径")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProductionPreflightError("生产数据库不存在或不可访问") from exc
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ProductionPreflightError("生产数据库必须是非空普通文件")
    os.environ["YD_OS_DB_PATH"] = str(resolved)
    return resolved


def _open_read_only(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            timeout=5,
        )
    except sqlite3.Error as exc:
        raise ProductionPreflightError("无法以只读方式打开生产数据库") from exc
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def validate_database(path: Path) -> dict:
    import database

    if Path(database.DB_PATH).resolve() != path:
        raise ProductionPreflightError(
            "数据库模块已在 YD_OS_DB_PATH 生效前加载；拒绝继续启动"
        )

    connection = _open_read_only(path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ProductionPreflightError("生产数据库 integrity_check 失败")
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_rows:
            raise ProductionPreflightError("生产数据库 foreign_key_check 失败")
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if user_version != database.SCHEMA_USER_VERSION:
            raise ProductionPreflightError(
                "生产数据库不是当前 v2.2 schema；请先完成离线 staged migration"
            )
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if not row["name"].startswith("sqlite_")
        }
        required_tables = {"users", *database.PERSONAL_DATA_TABLES}
        if tables != required_tables:
            raise ProductionPreflightError("生产数据库表集合不是精确的 v2.2 schema")
        for table in database.PERSONAL_DATA_TABLES:
            columns = {
                row["name"]
                for row in connection.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
            }
            if "user_id" not in columns:
                raise ProductionPreflightError(
                    "生产数据库存在未完成 ownership 升级的业务表"
                )

        admin_counts = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active
            FROM users
            WHERE role = 'admin'
            """
        ).fetchone()
        total_admins = int(admin_counts["total"] or 0)
        active_admins = int(admin_counts["active"] or 0)
        if total_admins != 1 or active_admins != 1:
            raise ProductionPreflightError(
                "生产数据库必须且只能包含一个启用的管理员账户"
            )
        soft_orphans, _soft_issues = _verify_soft_relations(
            connection,
            int(
                connection.execute(
                    "SELECT id FROM users WHERE role = 'admin' AND is_active = 1"
                ).fetchone()["id"]
            ),
        )
        if any(soft_orphans.values()):
            raise ProductionPreflightError("生产数据库存在软关联孤儿")
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise ProductionPreflightError("生产数据库预检失败") from exc
    finally:
        connection.close()

    return {
        "schema_version": user_version,
        "integrity_check": "ok",
        "foreign_key_check_rows": 0,
        "active_admins": active_admins,
        "soft_orphan_rows": 0,
    }


def run_preflight(*, require_release_context=True) -> dict:
    release = _validate_release_context() if require_release_context else None
    try:
        safety = config.validate_production_safety()
    except RuntimeError as exc:
        raise ProductionPreflightError(str(exc)) from exc
    if not safety.production or safety.development:
        raise ProductionPreflightError(
            "production.py 只接受 PERSONAL_OS_ENV=production"
        )
    if not safety.remote:
        raise ProductionPreflightError(
            "production.py 必须设置 PERSONAL_OS_REMOTE=1，明确声明远程可达"
        )
    database_path = _resolve_database_path()
    report = validate_database(database_path)
    config.mark_production_preflight_complete(database_path)
    report["runtime"] = "production"
    report["proxy_hops"] = 1
    if release is not None:
        report["release"] = release
    return report


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # The application emits its own query-free access events. Do not enable a
    # second server access log that may include raw URLs or query strings.
    logging.getLogger("gunicorn.access").setLevel(logging.WARNING)


def create_app(*, require_release_context=True):
    """Run the same-process preflight before importing the WSGI app."""
    configure_logging()
    run_preflight(require_release_context=require_release_context)
    from app import app as flask_app

    config.validate_production_safety(flask_app)
    return flask_app


def create_production_app():
    """Zero-argument Gunicorn factory; callers cannot weaken release checks."""
    return create_app(require_release_context=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PSY v2.2 production preflight")
    parser.add_argument(
        "--check",
        action="store_true",
        help="run fail-closed active-release preflight without starting Gunicorn",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging()
    try:
        report = run_preflight()
    except (ProductionPreflightError, RuntimeError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(
        "[OK] Production preflight passed: "
        f"schema={report['schema_version']} integrity=ok "
        f"foreign_keys=ok admins={report['active_admins']} proxy_hops=1"
    )
    if not args.check:
        print(
            "[INFO] Preflight only. Start production through "
            "production_launcher.py and the active release pointer."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
