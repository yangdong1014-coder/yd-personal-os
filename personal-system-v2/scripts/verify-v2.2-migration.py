#!/usr/bin/env python3
"""Authoritative verifier CLI for v2.2 migration execution envelope."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v22_migration import (  # noqa: E402
    VerificationError,
    verify_authoritative_envelope,
    verify_migration,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verify legacy-to-v2.2 database integrity with complete execution envelope"
    )
    parser.add_argument("source", type=Path, help="read-only legacy database")
    parser.add_argument("staged", type=Path, help="staged/migration v2.2 database")
    parser.add_argument(
        "--staged-dest",
        type=Path,
        default=None,
        help="future staged database destination path (for absence check)",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="future manifest path (for absence check)",
    )
    parser.add_argument(
        "--instance-root",
        type=Path,
        default=None,
        help="shadow instance root directory",
    )
    parser.add_argument(
        "--databases-root",
        type=Path,
        default=None,
        help="databases parent directory",
    )
    parser.add_argument(
        "--expected-source-size",
        type=int,
        default=None,
        help="expected source file size in bytes",
    )
    parser.add_argument(
        "--expected-source-sha256",
        type=str,
        default=None,
        help="expected source file SHA-256",
    )
    parser.add_argument(
        "--expected-migration-size",
        type=int,
        default=None,
        help="expected migration file size in bytes",
    )
    parser.add_argument(
        "--expected-migration-sha256",
        type=str,
        default=None,
        help="expected migration file SHA-256",
    )
    parser.add_argument(
        "--strict-shadow-layout",
        action="store_true",
        default=False,
        help="enforce strict shadow filesystem permissions and layout",
    )
    parser.add_argument(
        "--semantic-only",
        action="store_true",
        default=False,
        help="run semantic core verification directly without envelope",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.semantic_only:
        try:
            report = verify_migration(args.source, args.staged)
        except VerificationError as exc:
            report = exc.report or {"ok": False, "issues": exc.issues}
            print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    envelope_result = verify_authoritative_envelope(
        source_path=args.source,
        migration_path=args.staged,
        staged_dest=args.staged_dest,
        manifest_path=args.manifest_path,
        instance_root=args.instance_root,
        databases_root=args.databases_root,
        expected_source_size=args.expected_source_size,
        expected_source_sha256=args.expected_source_sha256,
        expected_migration_size=args.expected_migration_size,
        expected_migration_sha256=args.expected_migration_sha256,
        strict_shadow_layout=args.strict_shadow_layout,
    )

    formatted = json.dumps(envelope_result, ensure_ascii=False, indent=2)
    if envelope_result["raw_ok"]:
        print(formatted)
        return 0
    else:
        print(formatted, file=sys.stderr)
        return envelope_result["raw_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
