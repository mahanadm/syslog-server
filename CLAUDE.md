# Syslog Server Project

## Overview
Cross-platform syslog server application for OT (Operational Technology) network devices including Hirschmann, Cisco, and Stratix switches. Built with Python 3.12, FastAPI/uvicorn web server with browser-based UI.

## Project Location
- Source: C:/Users/Mahan/Documents/Claude Projects/Syslog Server Project/
- Config: C:/Users/Mahan/AppData/Roaming/SyslogServer/config.toml
- Database: C:/Users/Mahan/AppData/Roaming/SyslogServer/syslog.db
- Log files: C:/Users/Mahan/AppData/Roaming/SyslogServer/logs/
- Lock file: C:/Users/Mahan/AppData/Roaming/SyslogServer/tray.lock

## How to Run
- Desktop shortcut (recommended): Double-click Syslog Server on Desktop - launches tray manager which auto-starts server
- System tray icon: Right-click for Start/Stop/Restart/Open Web UI/Exit. Double-click opens web UI
- With console (debug): Double-click SyslogServer.bat
- Server only (no tray): Double-click SyslogServer.pyw
- Tray only (no auto-start): SyslogServerTray.pyw --no-auto-start
- From terminal: cd to project dir and run python -m syslog_server
- Auto-start on login: Shortcut in Windows Startup folder
- Note: .pyw launchers add src/ to sys.path directly

## System Tray Manager
- File: SyslogServerTray.pyw -> src/syslog_server/tray/tray_manager.py
- Uses pystray (lightweight) for system tray icon, NOT PySide6
- Icon shows green dot (running) or red dot (stopped) via Pillow overlay
- Polls /api/health endpoint every 5 seconds to check server status
- Manages server as a subprocess with CREATE_NO_WINDOW flag
- Single-instance enforced via lock file at AppData/Roaming/SyslogServer/tray.lock
- --no-auto-start flag skips auto-starting server (for Windows Service use)
- Desktop shortcut targets pythonw.exe with quoted .pyw path (spaces in dir names)
- server_control.py prefers python -m syslog_server for dev, EXE only if in Program Files

## Current Configuration
- UDP listener: Port 1514
- Web UI: Port 8080 (http://localhost:8080)
- TCP/TLS: Disabled by default
- Theme: Dark mode

## Tech Stack
- Python 3.12 with FastAPI + uvicorn web server
- SQLite with WAL mode and FTS5 for full-text search
- asyncio for network listeners
- TOML for configuration (tomli/tomli-w)
- pystray + Pillow for system tray manager
- websockets package required by uvicorn for WebSocket support
- Dependencies: fastapi, uvicorn, websockets, pystray, Pillow, tomli-w

## Known Issues
- Tray lock file: If stale, delete AppData/Roaming/SyslogServer/tray.lock
- WebSocket: Needs websockets package installed
- pystray: Use enabled= not visible= for menu items on Windows
- Paths with spaces: Must quote .pyw path in shortcut arguments
- Ports: syslog=1514, web=8080
