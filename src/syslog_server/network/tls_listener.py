"""TLS syslog listener — SSL-wrapped TCP per RFC 5425."""

from __future__ import annotations

import logging
import ssl
from pathlib import Path

logger = logging.getLogger(__name__)


def create_tls_context(
    cert_file: str,
    key_file: str,
    ca_file: str = "",
    require_client_cert: bool = False,
) -> ssl.SSLContext | None:
    """Create an SSL context for the TLS syslog listener.

    Returns None if the certificate files are missing or invalid.
    """
    cert_path = Path(cert_file)
    key_path = Path(key_file)

    if not cert_path.exists():
        logger.error("TLS certificate file not found: %s", cert_file)
        return None
    if not key_path.exists():
        logger.error("TLS key file not found: %s", key_file)
        return None

    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert_path), str(key_path))

        if ca_file:
            ca_path = Path(ca_file)
            if ca_path.exists():
                ctx.load_verify_locations(str(ca_path))
            else:
                logger.warning("TLS CA file not found: %s", ca_file)

        if require_client_cert:
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx.verify_mode = ssl.CERT_NONE

        # Set reasonable defaults
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        return ctx
    except Exception:
        logger.exception("Failed to create TLS context")
        return None
