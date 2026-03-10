"""Server process management for the tray manager."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ServerState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    STARTING = "starting"
    ERROR = "error"


class ServerControl:
    """Manages the syslog server process lifecycle."""

    def __init__(self, port: int = 8080, host: str = "localhost") -> None:
        self._process: subprocess.Popen | None = None
        self._port = port
        self._host = host
        self._state = ServerState.STOPPED

    @property
    def port(self) -> int:
        return self._port

    @property
    def state(self) -> ServerState:
        """Refresh and return the current server state."""
        if self._is_port_responding():
            self._state = ServerState.RUNNING
        elif self._process and self._process.poll() is None:
            self._state = ServerState.STARTING
        else:
            if self._process and self._process.poll() is not None:
                self._process = None
            self._state = ServerState.STOPPED
        return self._state

    def _is_port_responding(self) -> bool:
        """Check if the server is responding on its configured port."""
        try:
            url = f"http://{self._host}:{self._port}/api/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read())
                    return data.get("status") == "ok"
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
            pass
        return False

    def _find_server_command(self) -> tuple[list[str], dict[str, str] | None]:
        """Determine how to launch the server.

        Returns (command_list, env_dict_or_None).
        Priority:
        1. Installed EXE in Program Files (production install)
        2. python -m syslog_server (development / default)
        """
        # Only use EXE if formally installed in Program Files
        installed_exe = Path(r"C:\Program Files\SyslogServer\SyslogServer.exe")
        if installed_exe.exists():
            return [str(installed_exe)], None

        # Default: run as Python module (works with source tree)
        src_dir = str(Path(__file__).parents[2])
        env = os.environ.copy()
        env["PYTHONPATH"] = src_dir

        # Ensure we use python.exe (not pythonw.exe) for the server
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        return [str(python), "-m", "syslog_server"], env

    def start(self) -> bool:
        """Start the server process. Returns True if started successfully."""
        if self.state == ServerState.RUNNING:
            return True  # Already running (maybe as a service)

        cmd, env = self._find_server_command()
        logger.info("Starting server: %s", " ".join(cmd))

        try:
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=creation_flags,
            )
            self._state = ServerState.STARTING

            # Wait for server to become responsive (up to 15 seconds)
            for _ in range(30):
                time.sleep(0.5)
                if self._is_port_responding():
                    self._state = ServerState.RUNNING
                    logger.info("Server started successfully on port %d", self._port)
                    return True
                if self._process.poll() is not None:
                    self._state = ServerState.ERROR
                    logger.error("Server process exited prematurely")
                    return False

            # Timed out but process is still running
            if self._process.poll() is None:
                logger.warning("Server started but health check timed out")
                return self._is_port_responding()

            return False
        except Exception:
            logger.exception("Failed to start server")
            self._state = ServerState.ERROR
            return False

    def stop(self) -> bool:
        """Stop the server process. Returns True if stopped."""
        if self._process and self._process.poll() is None:
            logger.info("Stopping server...")
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Server did not stop gracefully, killing...")
                self._process.kill()
                self._process.wait(timeout=5)
            self._process = None
            self._state = ServerState.STOPPED
            logger.info("Server stopped")
            return True

        # We didn't start it (e.g., running as a service)
        self._process = None
        self._state = ServerState.STOPPED
        return False

    def restart(self) -> bool:
        """Restart the server."""
        self.stop()
        time.sleep(1)
        return self.start()

    @property
    def managed_by_us(self) -> bool:
        """True if we started this server process (vs. running as a service)."""
        return self._process is not None and self._process.poll() is None
