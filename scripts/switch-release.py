#!/usr/bin/env python3
"""Create, activate, or resolve an explicit PSY release descriptor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "personal-system-v2"
sys.path.insert(0, str(APP_DIR))

from database_artifacts import SUPPORTED_PROFILES  # noqa: E402
from release_switch import (  # noqa: E402
    ReleaseSwitchError,
    activate_release_pointer,
    create_release_descriptor,
    resolve_active_release,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Fail-closed PSY code/database release pairing"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    describe = subparsers.add_parser(
        "describe", help="create one immutable code/database descriptor"
    )
    describe.add_argument("--descriptor", type=Path, required=True)
    describe.add_argument("--release-id", required=True)
    describe.add_argument("--app-version", required=True)
    describe.add_argument("--git-commit", required=True)
    describe.add_argument("--code-root", type=Path, required=True)
    describe.add_argument("--entrypoint", type=Path, required=True)
    describe.add_argument("--config", type=Path, required=True)
    describe.add_argument("--database", type=Path, required=True)
    describe.add_argument("--manifest", type=Path, required=True)
    describe.add_argument(
        "--schema-profile", choices=SUPPORTED_PROFILES, required=True
    )

    activate = subparsers.add_parser(
        "activate", help="atomically replace the active release pointer"
    )
    activate.add_argument("--descriptor", type=Path, required=True)
    activate.add_argument("--active-pointer", type=Path, required=True)
    activate.add_argument("--expected-app-version", required=True)
    activate.add_argument("--expected-git-commit", required=True)
    activate.add_argument(
        "--service-stopped-confirmed",
        action="store_true",
        help="required assertion; the command does not stop a service",
    )

    resolve = subparsers.add_parser(
        "resolve", help="resolve and verify the selected release"
    )
    resolve.add_argument("--active-pointer", type=Path, required=True)
    resolve.add_argument("--expected-app-version", required=True)
    resolve.add_argument("--expected-git-commit", required=True)
    resolve.add_argument(
        "--verify-immutable-database",
        action="store_true",
        help="require the pre-start DB hash to still match its manifest",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "describe":
            report = create_release_descriptor(
                args.descriptor,
                release_id=args.release_id,
                application_version=args.app_version,
                git_commit=args.git_commit,
                code_root=args.code_root,
                code_entrypoint=args.entrypoint,
                config_path=args.config,
                database_path=args.database,
                database_manifest_path=args.manifest,
                expected_profile=args.schema_profile,
            )
        elif args.command == "activate":
            report = activate_release_pointer(
                args.descriptor,
                args.active_pointer,
                service_is_stopped=args.service_stopped_confirmed,
                expected_git_commit=args.expected_git_commit,
                expected_application_version=args.expected_app_version,
            )
        else:
            report = resolve_active_release(
                args.active_pointer,
                expected_git_commit=args.expected_git_commit,
                expected_application_version=args.expected_app_version,
                verify_immutable_database=args.verify_immutable_database,
            )
    except (ReleaseSwitchError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
