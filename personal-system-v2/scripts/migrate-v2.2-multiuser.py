#!/usr/bin/env python3
"""Create a new staged v2.2 database from a read-only v2.1.4 database."""

import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v22_migration import MigrationError, migrate_legacy_database  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(
        description="Offline legacy v2.1.4 to staged v2.2 multi-user migration"
    )
    parser.add_argument("source", type=Path, help="read-only legacy database")
    parser.add_argument("staged", type=Path, help="new staged v2.2 database")
    parser.add_argument("--admin-username", required=True)
    parser.add_argument("--admin-email", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    password = getpass.getpass("Bootstrap admin password: ")
    confirmation = getpass.getpass("Confirm bootstrap admin password: ")
    if password != confirmation:
        print("Migration stopped: passwords do not match.", file=sys.stderr)
        return 2
    try:
        report = migrate_legacy_database(
            args.source,
            args.staged,
            admin_username=args.admin_username,
            admin_email=args.admin_email,
            admin_password=password,
        )
    except (MigrationError, ValueError, OSError) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
