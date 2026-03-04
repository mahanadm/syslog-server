"""Configuration manager — loads/saves TOML config with platform-aware defaults."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import tomli_w

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _get_platform_dir() -> Path:
    """Get the platform-appropriate config/data directory."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming" / "SyslogServer"
    else:
        base = Path.home() / ".config" / "syslog-server"
    return base


DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "theme": "system",
        "minimize_to_tray": True,
        "start_minimized": False,
    },
    "listeners": {
        "udp": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 514,
        },
        "tcp": {
            "enabled": False,
            "host": "0.0.0.0",
            "port": 514,
            "framing": "newline",
        },
        "tls": {
            "enabled": False,
            "host": "0.0.0.0",
            "port": 6514,
            "cert_file": "",
            "key_file": "",
            "ca_file": "",
            "require_client_cert": False,
        },
    },
    "storage": {
        "database": {
            "path": "",
            "vacuum_interval_hours": 168,
            "retention_days": 0,
        },
        "files": {
            "enabled": True,
            "directory": "",
            "format": "{timestamp} [{severity}] {hostname} {app_name}: {message}",
            "organize_by": "ip",
            "rotation": "size",
            "max_file_size_mb": 10,
            "max_files": 10,
        },
    },
    "gui": {
        "live_view": {
            "max_rows": 50000,
            "auto_scroll": True,
            "show_raw": False,
            "timestamp_format": "%Y-%m-%d %H:%M:%S",
        },
        "columns": {
            "visible": [
                "timestamp", "source_ip", "device_name", "severity",
                "facility", "app_name", "message",
            ],
        },
    },
    "alerts": {
        "defaults": {
            "notification_enabled": True,
            "sound_enabled": False,
            "sound_file": "",
            "cooldown_seconds": 60,
        },
    },
    "performance": {
        "queue_max_size": 100000,
        "batch_size": 500,
        "batch_timeout_ms": 100,
    },
    "ntp": {
        "enabled": False,
        "host": "0.0.0.0",
        "port": 123,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively. Returns a new dict."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ConfigManager:
    """Manages application configuration with TOML persistence."""

    def __init__(self, config_path: Path | None = None):
        self._platform_dir = _get_platform_dir()
        self._config_path = config_path or (self._platform_dir / "config.toml")
        self._data: dict[str, Any] = deepcopy(DEFAULT_CONFIG)
        self.load()

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def platform_dir(self) -> Path:
        return self._platform_dir

    def load(self) -> None:
        """Load config from disk, merging with defaults."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "rb") as f:
                    user_config = tomllib.load(f)
                self._data = _deep_merge(DEFAULT_CONFIG, user_config)
            except Exception:
                self._data = deepcopy(DEFAULT_CONFIG)
        else:
            self._data = deepcopy(DEFAULT_CONFIG)

    def save(self) -> None:
        """Save current config to disk."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "wb") as f:
            tomli_w.dump(self._data, f)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Get a nested config value. Usage: config.get("listeners", "udp", "port")"""
        obj = self._data
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key)
                if obj is None:
                    return default
            else:
                return default
        return obj

    def set(self, *keys_and_value: Any) -> None:
        """Set a nested config value. Last arg is the value.
        Usage: config.set("listeners", "udp", "port", 1514)
        """
        if len(keys_and_value) < 2:
            raise ValueError("Need at least one key and a value")

        keys = keys_and_value[:-1]
        value = keys_and_value[-1]

        obj = self._data
        for key in keys[:-1]:
            if key not in obj or not isinstance(obj[key], dict):
                obj[key] = {}
            obj = obj[key]
        obj[keys[-1]] = value

    # Convenience accessors

    @property
    def db_path(self) -> Path:
        """Get the SQLite database path, with platform default."""
        p = self.get("storage", "database", "path", default="")
        if p:
            return Path(p)
        return self._platform_dir / "syslog.db"

    @property
    def log_directory(self) -> Path:
        """Get the log file directory, with platform default."""
        d = self.get("storage", "files", "directory", default="")
        if d:
            return Path(d)
        return self._platform_dir / "logs"

    @property
    def retention_days(self) -> int:
        return self.get("storage", "database", "retention_days", default=0)

    @property
    def queue_max_size(self) -> int:
        return self.get("performance", "queue_max_size", default=100000)

    @property
    def batch_size(self) -> int:
        return self.get("performance", "batch_size", default=500)

    @property
    def batch_timeout_ms(self) -> int:
        return self.get("performance", "batch_timeout_ms", default=100)

    @property
    def live_view_max_rows(self) -> int:
        return self.get("gui", "live_view", "max_rows", default=50000)
