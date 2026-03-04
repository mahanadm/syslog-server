"""FastAPI application — wires all components together and serves the web UI."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from syslog_server.alerts.alert_engine import AlertEngine
from syslog_server.alerts.email_notifier import EmailNotifier
from syslog_server.alerts.notifier import Notifier
from syslog_server.core.config import ConfigManager
from syslog_server.core.dispatcher import MessageDispatcher
from syslog_server.core.message_queue import MessageQueue
from syslog_server.network.listener_manager import ListenerManager
from syslog_server.network.ntp_server import NtpServer
from syslog_server.storage.storage_manager import StorageManager
from syslog_server.web.broadcaster import WebSocketBroadcaster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App-level singletons — set during lifespan, used by API routes via deps
# ---------------------------------------------------------------------------

_config: ConfigManager | None = None
_storage: StorageManager | None = None
_dispatcher: MessageDispatcher | None = None
_listener_manager: ListenerManager | None = None
_broadcaster: WebSocketBroadcaster | None = None
_notifier: Notifier | None = None
_email_notifier: EmailNotifier | None = None
_ntp_server: NtpServer | None = None


def get_config() -> ConfigManager:
    assert _config is not None
    return _config


def get_storage() -> StorageManager:
    assert _storage is not None
    return _storage


def get_dispatcher() -> MessageDispatcher:
    assert _dispatcher is not None
    return _dispatcher


def get_listener_manager() -> ListenerManager:
    assert _listener_manager is not None
    return _listener_manager


def get_broadcaster() -> WebSocketBroadcaster:
    assert _broadcaster is not None
    return _broadcaster


def get_notifier() -> Notifier:
    assert _notifier is not None
    return _notifier


def get_email_notifier() -> EmailNotifier:
    assert _email_notifier is not None
    return _email_notifier


def get_ntp_server() -> NtpServer:
    assert _ntp_server is not None
    return _ntp_server


# ---------------------------------------------------------------------------
# Lifespan — startup and shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _storage, _dispatcher, _listener_manager, _broadcaster, _notifier, _email_notifier, _ntp_server

    logger.info("Starting Syslog Server")

    # Config
    _config = ConfigManager()
    _config.save()

    # Message queue
    message_queue = MessageQueue(maxsize=_config.queue_max_size)

    # Storage
    _storage = StorageManager(_config)
    _storage.open()

    # Alert engine
    alert_engine = AlertEngine()
    try:
        rules = _storage.database.get_alert_rules()
        alert_engine.load_rules(rules)
    except Exception:
        logger.exception("Failed to load alert rules")

    # Notifier (in-memory alert history, no desktop notifications)
    _notifier = Notifier()

    # Email notifier (background SMTP sender thread)
    _email_notifier = EmailNotifier()

    # WebSocket broadcaster
    _broadcaster = WebSocketBroadcaster()

    # Dispatcher (background thread)
    _dispatcher = MessageDispatcher(
        message_queue=message_queue,
        storage=_storage,
        alert_engine=alert_engine,
        notifier=_notifier,
        email_notifier=_email_notifier,
        config=_config,
        batch_size=_config.batch_size,
        batch_timeout_ms=_config.batch_timeout_ms,
    )
    # Give dispatcher access to broadcaster + running event loop
    loop = asyncio.get_running_loop()
    _dispatcher.set_broadcaster(_broadcaster, loop)
    _dispatcher.start()

    # Network listeners
    _listener_manager = ListenerManager(message_queue.inner_queue, _config)
    _listener_manager.start()
    _listener_manager.start_listeners_from_config()
    statuses = _listener_manager.get_statuses()
    logger.info("Listeners started: %s", {k: v.active for k, v in statuses.items()})

    # NTP server (optional)
    _ntp_server = NtpServer()
    if _config.get("ntp", "enabled", default=False):
        ntp_host = _config.get("ntp", "host", default="0.0.0.0")
        ntp_port = _config.get("ntp", "port", default=123)
        try:
            await _ntp_server.start(ntp_host, ntp_port)
        except Exception:
            logger.exception("Failed to start NTP server on %s:%d", ntp_host, ntp_port)

    logger.info("Syslog Server ready — web UI available")

    yield  # <-- server is running

    # Shutdown
    logger.info("Shutting down...")
    _ntp_server.stop()
    _email_notifier.stop()
    _listener_manager.stop()
    _dispatcher.stop()
    _dispatcher.join(timeout=5.0)
    _storage.close()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Syslog Server", lifespan=lifespan)

# Import and include routers (after app is created)
from syslog_server.web.api import messages as messages_router  # noqa: E402
from syslog_server.web.api import devices as devices_router    # noqa: E402
from syslog_server.web.api import stats as stats_router        # noqa: E402
from syslog_server.web.api import alerts_api as alerts_router  # noqa: E402
from syslog_server.web.api import config_api as config_router  # noqa: E402
from syslog_server.web.ws import live as live_router           # noqa: E402

app.include_router(messages_router.router, prefix="/api")
app.include_router(devices_router.router, prefix="/api")
app.include_router(stats_router.router, prefix="/api")
app.include_router(alerts_router.router, prefix="/api")
app.include_router(config_router.router, prefix="/api")
app.include_router(live_router.router)

# Serve static files (HTML/JS/CSS)
_static_dir = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(str(_static_dir / "index.html"))
