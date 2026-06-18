"""Add startup shortcut with correct Chinese filename."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BAT_PATH = PROJECT_ROOT / "scripts" / "start-server.bat"
APP_DIR = PROJECT_ROOT / "personal-system-v2"
SHORTCUT_NAME = "个人能力操作系统.lnk"


def startup_dir() -> Path:
    import winreg  # noqa: PLC0415

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
    ) as key:
        value, _ = winreg.QueryValueEx(key, "Startup")
    return Path(value)


def create_shortcut(folder: Path) -> Path:
    shortcut_path = folder / SHORTCUT_NAME
    ps = f"""
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut('{shortcut_path}')
$link.TargetPath = '{BAT_PATH}'
$link.WorkingDirectory = '{APP_DIR}'
$link.Description = '开机自启 - 个人能力操作系统'
$link.IconLocation = "$env:SystemRoot\\System32\\imageres.dll,109"
$link.Save()
Write-Host 'Created: {shortcut_path}'
"""
    tmp = PROJECT_ROOT / "scripts" / "_startup_tmp.ps1"
    tmp.write_text(ps, encoding="utf-8-sig")
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(tmp),
            ],
            check=True,
        )
    finally:
        tmp.unlink(missing_ok=True)
    return shortcut_path


def main() -> int:
    if not BAT_PATH.is_file():
        print(f"[ERROR] Missing launcher: {BAT_PATH}", file=sys.stderr)
        return 1
    path = create_shortcut(startup_dir())
    print(f"已加入开机自启: {path}")
    print("取消自启请删除上述 .lnk 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())