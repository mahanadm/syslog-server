"""Create desktop and auto-start shortcuts for Syslog Server Tray Manager.

Usage:
    python tools/create_shortcuts.py
    python tools/create_shortcuts.py --no-desktop
    python tools/create_shortcuts.py --no-startup
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def create_shortcut_ps(
    shortcut_path: Path,
    target: Path,
    arguments: str = "",
    working_dir: Path | None = None,
    icon_path: Path | None = None,
    description: str = "",
) -> None:
    """Create a Windows .lnk shortcut using PowerShell."""
    work_dir = working_dir or target.parent
    icon_line = f"$s.IconLocation = '{icon_path}'" if icon_path else ""
    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{shortcut_path}')
$s.TargetPath = '{target}'
$s.Arguments = '{arguments}'
$s.WorkingDirectory = '{work_dir}'
$s.Description = '{description}'
{icon_line}
$s.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        check=True,
        capture_output=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Syslog Server shortcuts")
    parser.add_argument("--no-desktop", action="store_true", help="Skip desktop shortcut")
    parser.add_argument("--no-startup", action="store_true", help="Skip auto-start shortcut")
    args = parser.parse_args()

    # Determine paths
    project_root = Path(__file__).parent.parent.resolve()
    pyw_file = project_root / "SyslogServerTray.pyw"
    icon_file = project_root / "src" / "syslog_server" / "assets" / "syslog_server.ico"

    # Find pythonw.exe
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)  # Fallback to python.exe

    if not pyw_file.exists():
        print(f"ERROR: {pyw_file} not found!")
        sys.exit(1)

    if not args.no_desktop:
        desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
        lnk = desktop / "Syslog Server.lnk"
        create_shortcut_ps(
            lnk,
            target=pythonw,
            arguments=str(pyw_file),
            working_dir=project_root,
            icon_path=icon_file if icon_file.exists() else None,
            description="Syslog Server Tray Manager",
        )
        print(f"Desktop shortcut created: {lnk}")

    if not args.no_startup:
        startup = (
            Path(os.environ["APPDATA"])
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        lnk = startup / "Syslog Server.lnk"
        create_shortcut_ps(
            lnk,
            target=pythonw,
            arguments=str(pyw_file),
            working_dir=project_root,
            icon_path=icon_file if icon_file.exists() else None,
            description="Syslog Server Tray Manager",
        )
        print(f"Startup shortcut created: {lnk}")

    print("\nDone! The tray manager will now:")
    if not args.no_desktop:
        print("  - Be launchable from the Desktop shortcut")
    if not args.no_startup:
        print("  - Auto-start when you log in to Windows")


if __name__ == "__main__":
    main()
