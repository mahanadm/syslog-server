"""System tray manager for Syslog Server."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
from pystray import MenuItem as Item

# Ensure src/ is on the path when running from source
_src_dir = str(Path(__file__).parents[2])
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from syslog_server.core.config import ConfigManager
from syslog_server.tray.icon_helper import load_icon, make_status_icon
from syslog_server.tray.server_control import ServerControl, ServerState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class SyslogTrayApp:
    """Manages the system tray icon and server lifecycle."""

    def __init__(self, auto_start: bool = True) -> None:
        self._config = ConfigManager()
        port = self._config.get("web", "port", default=8080)
        self._server = ServerControl(port=port)
        self._auto_start = auto_start
        self._base_icon = load_icon()
        self._icon: pystray.Icon | None = None
        self._running = True

    # ── Icon helpers ─────────────────────────────────────────────────────

    def _get_icon(self) -> "PIL.Image.Image":
        running = self._server.state == ServerState.RUNNING
        return make_status_icon(self._base_icon, running)

    def _update_icon(self) -> None:
        if self._icon:
            self._icon.icon = self._get_icon()
            state = self._server.state
            self._icon.title = f"Syslog Server - {state.value.title()}"

    # ── Menu callbacks ───────────────────────────────────────────────────

    def _on_start(self, icon: pystray.Icon, item: Item) -> None:
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self) -> None:
        if self._icon:
            self._icon.title = "Syslog Server - Starting..."
        ok = self._server.start()
        self._update_icon()
        if not ok and self._icon:
            self._icon.notify("Failed to start server", "Syslog Server")

    def _on_stop(self, icon: pystray.Icon, item: Item) -> None:
        self._server.stop()
        self._update_icon()

    def _on_restart(self, icon: pystray.Icon, item: Item) -> None:
        threading.Thread(target=self._do_restart, daemon=True).start()

    def _do_restart(self) -> None:
        if self._icon:
            self._icon.title = "Syslog Server - Restarting..."
        self._server.restart()
        self._update_icon()

    def _on_open_ui(self, icon: pystray.Icon, item: Item) -> None:
        port = self._server.port
        webbrowser.open(f"http://localhost:{port}")

    def _on_exit(self, icon: pystray.Icon, item: Item) -> None:
        self._running = False
        if self._server.managed_by_us:
            self._server.stop()
        icon.stop()

    # ── Menu enabled-state helpers ───────────────────────────────────────

    def _is_running(self, item: Item) -> bool:
        return self._server.state == ServerState.RUNNING

    def _is_stopped(self, item: Item) -> bool:
        return self._server.state != ServerState.RUNNING

    # ── Menu construction ────────────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            Item("Syslog Server", None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Open Web UI", self._on_open_ui, default=True),
            pystray.Menu.SEPARATOR,
            Item("Start Server", self._on_start, enabled=self._is_stopped),
            Item("Stop Server", self._on_stop, enabled=self._is_running),
            Item("Restart Server", self._on_restart, enabled=self._is_running),
            pystray.Menu.SEPARATOR,
            Item("Exit", self._on_exit),
        )

    # ── Background polling ───────────────────────────────────────────────

    def _status_poll_loop(self) -> None:
        """Background thread that refreshes the icon every 5 seconds."""
        while self._running:
            try:
                self._update_icon()
                if self._icon:
                    self._icon.update_menu()
            except Exception:
                pass
            time.sleep(5)

    # ── Single instance check ────────────────────────────────────────────

    def _acquire_lock(self) -> bool:
        """Prevent multiple tray manager instances via a lock file."""
        lock_dir = Path(os.environ.get("APPDATA", Path.home())) / "SyslogServer"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = lock_dir / "tray.lock"

        try:
            if self._lock_path.exists():
                # Check if the PID in the lock file is still running
                try:
                    old_pid = int(self._lock_path.read_text().strip())
                    if sys.platform == "win32":
                        import ctypes
                        kernel32 = ctypes.windll.kernel32
                        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                        handle = kernel32.OpenProcess(0x1000, False, old_pid)
                        if handle:
                            kernel32.CloseHandle(handle)
                            # Process exists — but is it actually a Python/tray process?
                            # Be lenient: if the PID is our own, allow it
                            if old_pid != os.getpid():
                                logger.warning(
                                    "Another tray manager may be running (PID %d)", old_pid
                                )
                                # Don't block — the old process might not be ours
                except (ValueError, OSError, AttributeError):
                    pass  # Stale lock file or can't check, proceed

                # Remove stale lock and continue
                self._lock_path.unlink(missing_ok=True)

            self._lock_path.write_text(str(os.getpid()))
            return True
        except OSError:
            return True  # Can't check, just proceed

    def _release_lock(self) -> None:
        try:
            if hasattr(self, "_lock_path") and self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            pass

    # ── Main entry ───────────────────────────────────────────────────────

    def run(self) -> None:
        """Main entry point - blocks until Exit is chosen."""
        if not self._acquire_lock():
            logger.error("Another instance is already running. Exiting.")
            return

        try:
            # Auto-start server if configured
            if self._auto_start:
                threading.Thread(target=self._do_start, daemon=True).start()

            self._icon = pystray.Icon(
                name="SyslogServer",
                icon=self._get_icon(),
                title="Syslog Server",
                menu=self._build_menu(),
            )

            # Start background status polling
            poll_thread = threading.Thread(target=self._status_poll_loop, daemon=True)
            poll_thread.start()

            # This blocks until icon.stop() is called
            self._icon.run()
        finally:
            self._release_lock()


def main() -> None:
    parser = argparse.ArgumentParser(description="Syslog Server Tray Manager")
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Don't automatically start the server on launch",
    )
    args = parser.parse_args()

    app = SyslogTrayApp(auto_start=not args.no_auto_start)
    app.run()


if __name__ == "__main__":
    main()
