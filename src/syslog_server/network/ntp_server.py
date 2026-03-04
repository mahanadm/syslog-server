"""Simple SNTP server (RFC 4330) — serves local system time to network devices."""

from __future__ import annotations

import asyncio
import logging
import struct
import time

logger = logging.getLogger(__name__)

# Seconds between NTP epoch (Jan 1, 1900) and Unix epoch (Jan 1, 1970)
_NTP_DELTA = 2208988800


def _to_ntp_ts(unix_time: float) -> tuple[int, int]:
    """Convert a Unix timestamp to an NTP (seconds, fraction) pair."""
    ntp = unix_time + _NTP_DELTA
    secs = int(ntp)
    frac = int((ntp - secs) * (2 ** 32))
    return secs, frac


class _NtpProtocol(asyncio.DatagramProtocol):
    """asyncio DatagramProtocol that responds to SNTP client requests."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if len(data) < 48:
            return

        recv_time = time.time()

        # Echo the client's transmit timestamp as our originate timestamp
        orig_secs = struct.unpack_from("!I", data, 40)[0]
        orig_frac = struct.unpack_from("!I", data, 44)[0]

        ref_s, ref_f = _to_ntp_ts(recv_time)
        recv_s, recv_f = _to_ntp_ts(recv_time)
        send_s, send_f = _to_ntp_ts(time.time())

        # LI=0 (no warning), VN=4, Mode=4 (server)
        li_vn_mode = (0 << 6) | (4 << 3) | 4

        pkt = struct.pack(
            "!B B b b I I 4s II II II II",
            li_vn_mode,           # LI=0, VN=4, Mode=4
            1,                    # Stratum 1 (primary reference clock)
            6,                    # Poll interval (exponent, 2^6 = 64s)
            -20,                  # Precision (~microsecond, 2^-20)
            0,                    # Root delay (0 for stratum 1)
            0,                    # Root dispersion (0 for stratum 1)
            b"LOCL",              # Reference ID (local clock)
            ref_s, ref_f,         # Reference timestamp
            orig_secs, orig_frac, # Originate timestamp (echo client's transmit)
            recv_s, recv_f,       # Receive timestamp
            send_s, send_f,       # Transmit timestamp
        )

        if self.transport:
            self.transport.sendto(pkt, addr)

    def error_received(self, exc: Exception) -> None:
        logger.debug("NTP protocol error: %s", exc)


class NtpServer:
    """Manages the SNTP UDP server lifecycle in the asyncio event loop."""

    def __init__(self) -> None:
        self._transport: asyncio.DatagramTransport | None = None
        self._host: str = "0.0.0.0"
        self._port: int = 123

    @property
    def active(self) -> bool:
        return self._transport is not None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    async def start(self, host: str, port: int) -> None:
        """Start the NTP server on the given host/port."""
        if self._transport is not None:
            self.stop()

        self._host = host
        self._port = port

        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            _NtpProtocol,
            local_addr=(host, port),
        )
        self._transport = transport  # type: ignore[assignment]
        logger.info("NTP server listening on %s:%d (UDP)", host, port)

    def stop(self) -> None:
        """Stop the NTP server."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            logger.info("NTP server stopped")
