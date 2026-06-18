"""Create desktop shortcut with correct Chinese filename (UTF-8 safe)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BAT_PATH = PROJECT_ROOT / "scripts" / "start-server.bat"
APP_DIR = PROJECT_ROOT / "personal-system-v2"
SHORTCUT_NAME = "个人能力操作系统.lnk"


def desktop_dir() -> Path:
    return Path(os.path.join(os.environ["USERPROFILE"], "Desktop"))


def remove_old_shortcuts(desktop: Path) -> None:
    ps = f"""
$bat = '{BAT_PATH}'
Get-ChildItem '{desktop}' -Filter '*.lnk' | ForEach-Object {{
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($_.FullName)
    if ($s.TargetPath -eq $bat) {{ Remove-Item $_.FullName -Force; Write-Host "Removed: $($_.Name)" }}
}}
"""
    _run_ps(ps)


def create_shortcut(desktop: Path) -> Path:
    shortcut_path = desktop / SHORTCUT_NAME
    ps = f"""
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut('{shortcut_path}')
$link.TargetPath = '{BAT_PATH}'
$link.WorkingDirectory = '{APP_DIR}'
$link.Description = '启动个人能力操作系统 (http://127.0.0.1:5000)'
$link.IconLocation = "$env:SystemRoot\\System32\\imageres.dll,109"
$link.Save()
Write-Host 'Created: {shortcut_path}'
"""
    _run_ps(ps)
    return shortcut_path


def _run_ps(script: str) -> None:
    tmp = PROJECT_ROOT / "scripts" / "_shortcut_tmp.ps1"
    tmp.write_text(script, encoding="utf-8-sig")
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


def main() -> int:
    if not BAT_PATH.is_file():
        print(f"[ERROR] Missing launcher: {BAT_PATH}", file=sys.stderr)
        return 1
    desktop = desktop_dir()
    remove_old_shortcuts(desktop)
    path = create_shortcut(desktop)
    print(f"桌面快捷方式已创建: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())