"""Generate summary statistics reports."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from syslog_server.core.constants import FACILITY_NAMES, SEVERITY_NAMES, Facility, Severity


def generate_summary_report(stats: dict[str, Any], output_path: Path) -> None:
    """Generate a text summary report from database statistics."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 60,
        "SYSLOG SERVER — SUMMARY REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"Total Messages: {stats.get('total_messages', 0):,}",
        f"Total Devices:  {stats.get('total_devices', 0)}",
        f"Messages (last hour): {stats.get('messages_last_hour', 0):,}",
        "",
        "-" * 40,
        "SEVERITY DISTRIBUTION",
        "-" * 40,
    ]

    severity_counts = stats.get("severity_counts", {})
    for sev in Severity:
        count = severity_counts.get(sev.value, 0)
        name = SEVERITY_NAMES.get(sev, sev.name)
        bar = "#" * min(count // 100, 50)
        lines.append(f"  {name:<15} {count:>10,}  {bar}")

    lines.extend([
        "",
        "-" * 40,
        "TOP DEVICES BY MESSAGE COUNT",
        "-" * 40,
    ])

    for device in stats.get("top_devices", []):
        name = device.get("display_name", device.get("ip_address", "?"))
        ip = device.get("ip_address", "?")
        count = device.get("message_count", 0)
        lines.append(f"  {name:<30} ({ip:<15}) {count:>10,}")

    lines.extend(["", "=" * 60])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
