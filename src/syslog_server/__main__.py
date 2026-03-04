"""Entry point: starts the uvicorn web server."""

from __future__ import annotations

import sys


def main() -> None:
    import uvicorn
    from syslog_server.core.config import ConfigManager

    config = ConfigManager()
    port = config.get("web", "port", default=8080)
    host = config.get("web", "host", default="0.0.0.0")

    uvicorn.run(
        "syslog_server.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    # Allow: python -m syslog_server
    src_dir = __file__
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(src_dir)), ".."))
    main()
