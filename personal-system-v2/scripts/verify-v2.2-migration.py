#!/usr/bin/env python3
"""Verify a staged v2.2 database against its read-only legacy source."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v22_migration import VerificationError, verify_migration  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verify legacy-to-v2.2 staged database integrity"
    )
    parser.add_argument("source", type=Path, help="read-only legacy database")
    parser.add_argument("staged", type=Path, help="staged v2.2 database")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        report = verify_migration(args.source, args.staged)
    except VerificationError as exc:
        report = exc.report or {"ok": False, "issues": exc.issues}
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
