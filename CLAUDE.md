# Syslog Server Project

## Overview
Cross-platform syslog server application for OT (Operational Technology) network devices including Hirschmann, Cisco, and Stratix switches. Built with Python 3.10+ and PySide6 (Qt GUI).

## Project Location
- **Source**: `C:\Users\Test\Documents\Claude\Syslog Server Project\`
- **Config**: `C:\Users\Test\AppData\Roaming\SyslogServer\config.toml`
- **Database**: `C:\Users\Test\AppData\Roaming\SyslogServer\syslog.db`
- **Log files**: `C:\Users\Test\AppData\Roaming\SyslogServer\logs\`

## How to Run
- **With console (debug)**: Double-click `SyslogServer.bat`
- **Without console (normal)**: Double-click `SyslogServer.pyw` or the desktop shortcut `C:\Users\Test\Desktop\Syslog Server.lnk`
- **From terminal**: `cd "C:\Users\Test\Documents\Claude\Syslog Server Project" && python -m syslog_server`
- **Note**: The `.pyw` launcher adds `src/` to `sys.path` directly, bypassing environment variable issues on Windows

## Current Configuration
- **UDP listener**: Port 1514 (configured in config.toml, not the default 514)
- **TCP/TLS**: Disabled by default
- **Theme**: Dark mode set in config
- **Hirschmann switch IP**: 192.168.10.1 (hostname RSP-ECE55576F0F0)

## Tech Stack
- **Python 3.10+** with **PySide6** (LGPL-licensed Qt bindings)
- **SQLite** with WAL mode and FTS5 for full-text search
- **asyncio** for network listeners (in dedicated thread)
- **TOML** for configuration (`tomli`/`tomli-w`)
- Dependencies: PySide6, tomli, tomli-w

## Architecture

### Threading Model
```
Thread 1 (Qt GUI)         Thread 2 (asyncio)          Thread 3 (QThread Dispatcher)
Qt event loop             asyncio event loop           Blocking loop on Queue
All widget updates        UDP/TCP/TLS listeners        Reads queue, batches msgs
QTimer polls buffer       Parses -> queue.put()        Writes to DB + log files
                                                       Fills GUI buffer (thread-safe)
```

### Message Pipeline
1. **Network listener** (asyncio thread) receives UDP/TCP data
2. **Parser** (`auto_detect.py`) identifies format and parses to `SyslogMessage`
3. **queue.Queue** bridges network thread -> dispatcher thread
4. **Dispatcher** (QThread) drains queue, writes to storage, fills `_gui_buffer`
5. **QTimer** (100ms, GUI thread) polls `dispatcher.poll_gui_buffer()` -> feeds Live View

**IMPORTANT**: Cross-thread Qt Signals with Python objects (list, dataclass) are UNRELIABLE in PySide6. The GUI uses QTimer polling with a `threading.Lock`-protected buffer instead. Only native Qt types (float, int) are safe to use with cross-thread signals.

### Parser Detection Order (auto_detect.py)
1. **RFC 5424** - version digit after PRI
2. **Cisco IOS** - `%FACILITY-SEVERITY-MNEMONIC` pattern
3. **Hirschmann** - `[APPNAME TASKNAME TASKID]` bracket pattern
4. **RFC 3164** - traditional BSD format (with both standard and ISO timestamp support)
5. **Raw fallback** - wraps unparsed data

### Hirschmann Parser Details
- Handles **BSD timestamps** (`Dec 27 21:46:20`) - most common from real switches
- Handles **ISO timestamps** (`2025-12-27 21:14:43`) - some firmware versions
- Extracts bracket fields: `[APPNAME TASKNAME TASKID]` -> `app_name`, `process_id`, `message_id`
- **Message enricher** (`hirschmann_enricher.py`) translates cryptic MIB OID values to human-readable text
  - `hm2ConfigurationChangedTrap: hm2FMNvmState.0=1` -> `Configuration Changed: NVM state.0 = out of sync (unsaved changes)`
  - Covers: config traps, web login/logout, link up/down, STP, port security, power supply, temperature, etc.

## Project Structure
```
syslog-server/
├── pyproject.toml
├── requirements.txt
├── SyslogServer.bat          # Debug launcher (with console)
├── SyslogServer.pyw          # Normal launcher (no console)
├── SyslogServer.vbs          # VBS wrapper
├── CLAUDE.md                 # This file
├── src/syslog_server/
│   ├── __init__.py            # Version "1.0.0"
│   ├── __main__.py            # Entry point for python -m
│   ├── app.py                 # QApplication setup, QTimer polling, wiring
│   ├── core/
│   │   ├── config.py          # TOML config manager (platform-aware paths)
│   │   ├── constants.py       # Severity/Facility enums, color maps
│   │   ├── message.py         # SyslogMessage frozen dataclass with slots
│   │   ├── message_queue.py   # Thread-safe queue wrapper with drain()
│   │   └── dispatcher.py      # QThread: queue->storage+GUI buffer, stats signal
│   ├── network/
│   │   ├── udp_listener.py    # asyncio DatagramProtocol
│   │   ├── tcp_listener.py    # asyncio StreamServer with framing
│   │   ├── tls_listener.py    # SSL-wrapped TCP
│   │   └── listener_manager.py # Manages asyncio loop in thread
│   ├── parser/
│   │   ├── rfc3164.py         # BSD syslog (standard + ISO timestamp)
│   │   ├── rfc5424.py         # Modern syslog with structured data
│   │   ├── cisco.py           # Cisco IOS %FACILITY-SEV-MNEMONIC
│   │   ├── hirschmann.py      # Hirschmann [APP TASK ID] bracket format
│   │   ├── hirschmann_enricher.py  # MIB OID -> human-readable translation
│   │   └── auto_detect.py     # Format detection + dispatch
│   ├── storage/
│   │   ├── database.py        # SQLite: WAL, FTS5, batch insert, search
│   │   ├── file_writer.py     # Per-device rotating log files
│   │   └── storage_manager.py # Coordinates DB + file writes
│   ├── gui/
│   │   ├── main_window.py     # QMainWindow: tabs, menu, status bar, tray
│   │   ├── live_view.py       # Real-time log stream (QTableView, Interactive columns)
│   │   ├── search_view.py     # DB-backed search with filters, CSV export
│   │   ├── device_manager.py  # Device profiles CRUD with color picker
│   │   ├── settings_dialog.py # Tabbed settings: Listeners, TLS, Storage, GUI, Perf
│   │   ├── alert_config.py    # Alert rule editor (QListWidget)
│   │   ├── export_dialog.py   # Export summary report dialog
│   │   ├── stats_view.py      # Dashboard: StatCards, SeverityBar, top devices
│   │   ├── models/
│   │   │   ├── log_table_model.py      # Ring-buffer deque (50k rows max)
│   │   │   ├── search_result_model.py  # DB query results
│   │   │   └── device_table_model.py   # Device list
│   │   └── delegates/
│   │       ├── severity_delegate.py    # Row background color by severity
│   │       └── device_delegate.py      # Left border in device color
│   ├── alerts/
│   │   ├── alert_engine.py    # Rule evaluation with cooldown
│   │   └── notifier.py        # Desktop notifications via tray icon
│   └── export/
│       ├── csv_exporter.py    # CSV export
│       └── report_generator.py # Text summary reports
└── tests/
```

## Database Schema (Key Tables)
- **messages** - id, timestamp, received_at, source_ip, severity, facility, hostname, app_name, message, raw, protocol, rfc_format, cisco_mnemonic, device_id
- **messages_fts** - FTS5 virtual table on message column
- **devices** - id, ip_address, display_name, color, vendor, hostname, first_seen, last_seen, message_count
- **alert_rules** - id, name, min/max_severity, keyword_pattern, device_filter, cooldown, notification/sound flags
- Indexes on: timestamp, source_ip, severity, composite(source_ip+severity+timestamp)

## SyslogMessage Dataclass Fields
`timestamp`, `received_at`, `source_ip`, `source_port`, `facility`, `severity`, `hostname`, `app_name`, `process_id`, `message_id`, `message`, `raw`, `protocol`, `rfc_format`, `structured_data`, `cisco_sequence`, `cisco_mnemonic`

## Known Issues & Solutions

### PySide6 Cross-Thread Signals
**Problem**: `Signal(list)` and `Signal(object)` are unreliable for passing Python objects between threads in PySide6.
**Solution**: Use `threading.Lock`-protected buffer + QTimer polling from GUI thread. Only use signals for native Qt types (float, int).

### Port Conflicts
**Problem**: `[WinError 10048]` when another app (e.g., Graylog) uses the same port.
**Solution**: Check with `netstat -ano | findstr ":PORT"`. Kill old instances with `powershell.exe -Command "Stop-Process -Name pythonw -Force"`. Current port: 1514.

### Hirschmann Timestamp Formats
**Problem**: Original parser only handled ISO timestamps, but real switches send BSD timestamps.
**Solution**: Parser now tries BSD patterns first (`Dec 27 21:46:20`), then ISO (`2025-12-27 21:14:43`).

### Windows Launcher
**Problem**: VBS script environment variables didn't propagate to child processes.
**Solution**: Created `SyslogServer.pyw` that adds `src/` to `sys.path` directly in Python. Desktop shortcut points to `pythonw.exe` running the `.pyw` file.

## GUI Column Layout
All table views use `QHeaderView.ResizeMode.Interactive` so columns are user-resizable by dragging. The last column (typically Message) stretches to fill remaining space via `setStretchLastSection(True)`.

## Future Enhancements
- Quick filter implementation (currently a stub using `_apply_quick_filter`)
- PyInstaller packaging for standalone executable
- TCP/TLS listener testing with real devices
- Additional vendor-specific parsers as needed
- Column width persistence across sessions
