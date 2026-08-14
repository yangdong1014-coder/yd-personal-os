#!/usr/bin/env python3
"""Create, verify, or restore a PSY SQLite backup artifact.

Every path is explicit. There is intentionally no default pointing at the
repository's data directory, and historical artifacts are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "personal-system-v2"
sys.path.insert(0, str(APP_DIR))

from database_artifacts import (  # noqa: E402
    DatabaseArtifactError,
    SUPPORTED_PROFILES,
    create_verified_backup,
    restore_verified_backup,
    verify_database_artifact,
)


def backup_database(
    source,
    backup_directory,
    *,
    expected_profile,
    git_commit,
    application_version,
    timestamp=None,
    failure_hook=None,
):
    return create_verified_backup(
        source,
        backup_directory,
        expected_profile=expected_profile,
        git_commit=git_commit,
        application_version=application_version,
        timestamp=timestamp,
        failure_hook=failure_hook,
    )


def verify_backup(database_path, manifest_path, *, expected_profile):
    return verify_database_artifact(
        database_path,
        manifest_path,
        expected_profile=expected_profile,
    )


def restore_backup(
    database_path,
    manifest_path,
    restore_path,
    *,
    expected_profile,
):
    return restore_verified_backup(
        database_path,
        manifest_path,
        restore_path,
        expected_profile=expected_profile,
    )


def _profile_argument(parser):
    parser.add_argument(
        "--schema-profile",
        choices=SUPPORTED_PROFILES,
        required=True,
        help="expected database contract: legacy_v214 or v22",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Fail-closed PSY SQLite backup and restore verification"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create", help="create a consistent SQLite backup plus manifest"
    )
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--backup-dir", type=Path, required=True)
    _profile_argument(create)
    create.add_argument("--git-commit", required=True)
    create.add_argument("--app-version", required=True)

    verify = subparsers.add_parser(
        "verify", help="verify a backup/staged database against its manifest"
    )
    verify.add_argument("--database", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    _profile_argument(verify)

    restore = subparsers.add_parser(
        "restore", help="restore a verified artifact to a new path"
    )
    restore.add_argument("--database", type=Path, required=True)
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--restore", type=Path, required=True)
    _profile_argument(restore)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            report = backup_database(
                args.source,
                args.backup_dir,
                expected_profile=args.schema_profile,
                git_commit=args.git_commit,
                application_version=args.app_version,
            )
        elif args.command == "verify":
            report = verify_backup(
                args.database,
                args.manifest,
                expected_profile=args.schema_profile,
            )
        else:
            report = restore_backup(
                args.database,
                args.manifest,
                args.restore,
                expected_profile=args.schema_profile,
            )
    except (DatabaseArtifactError, OSError, sqlite3.Error) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
