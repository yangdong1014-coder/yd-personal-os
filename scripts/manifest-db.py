#!/usr/bin/env python3
"""Create an exclusive manifest for an already verified DB artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "personal-system-v2"
sys.path.insert(0, str(APP_DIR))

from database_artifacts import (  # noqa: E402
    DatabaseArtifactError,
    SUPPORTED_PROFILES,
    create_database_manifest,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Bind a staged/restored SQLite database to verified metadata"
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--schema-profile", choices=SUPPORTED_PROFILES, required=True
    )
    parser.add_argument("--artifact-kind", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--source-schema-profile", choices=SUPPORTED_PROFILES, required=True
    )
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--app-version", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        report = create_database_manifest(
            args.database,
            args.manifest,
            expected_profile=args.schema_profile,
            artifact_kind=args.artifact_kind,
            source_path=args.source,
            source_profile=args.source_schema_profile,
            git_commit=args.git_commit,
            application_version=args.app_version,
        )
    except (DatabaseArtifactError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
