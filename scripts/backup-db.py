"""备份 personal-system-v2/data/yd_os.db 到 backups/，保留最近 N 份。"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "personal-system-v2"
DB_PATH = APP_DIR / "data" / "yd_os.db"
BACKUP_DIR = APP_DIR / "backups"
DEFAULT_KEEP = 30


def backup_database(keep: int = DEFAULT_KEEP) -> Path:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"yd_os_{stamp}.db"
    shutil.copy2(DB_PATH, dest)
    _prune_old_backups(keep)
    return dest


def _prune_old_backups(keep: int) -> None:
    files = sorted(
        BACKUP_DIR.glob("yd_os_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="备份 PSY-1 SQLite 数据库")
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP,
        help=f"保留最近 N 份备份（默认 {DEFAULT_KEEP}）",
    )
    args = parser.parse_args()
    try:
        dest = backup_database(keep=max(1, args.keep))
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] Backup created: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())