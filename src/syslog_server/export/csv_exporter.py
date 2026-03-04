"""Export syslog messages to CSV format."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "timestamp",
    "received_at",
    "source_ip",
    "severity",
    "facility",
    "hostname",
    "app_name",
    "process_id",
    "message",
    "protocol",
    "rfc_format",
    "cisco_mnemonic",
    "device_name",
]


def export_to_csv(
    messages: list[dict[str, Any]],
    output_path: Path,
    columns: list[str] | None = None,
) -> int:
    """Export messages to a CSV file.

    Args:
        messages: List of message dicts (from DatabaseManager.search)
        output_path: Path to write the CSV file
        columns: Optional list of column names to include

    Returns:
        Number of rows written
    """
    if columns is None:
        columns = CSV_COLUMNS

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for msg in messages:
            writer.writerow(msg)

    logger.info("Exported %d messages to %s", len(messages), output_path)
    return len(messages)
