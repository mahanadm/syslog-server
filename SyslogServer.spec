# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Syslog Server (FastAPI web app)."""

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Collect all data and binaries for FastAPI, uvicorn, and their deps
datas = []
binaries = []
hiddenimports = []

for pkg in ('fastapi', 'uvicorn', 'starlette', 'anyio', 'h11', 'httptools',
            'websockets', 'watchfiles', 'pydantic', 'pydantic_core', 'click',
            'tomli_w', 'annotated_types', 'typing_inspection', 'annotated_doc'):
    tmp = collect_all(pkg)
    datas    += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]

# Bundle the web UI static files (HTML/JS)
datas += [
    ('src/syslog_server/web/static', 'syslog_server/web/static'),
]

a = Analysis(
    ['src/syslog_server/__main__.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'tomllib',
        'tomli_w',
        'sqlite3',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'email.mime.text',
        'email.mime.multipart',
        'syslog_server',
        'syslog_server.app',
        'syslog_server.web',
        'syslog_server.web.api',
        'syslog_server.web.api.messages',
        'syslog_server.web.api.devices',
        'syslog_server.web.api.stats',
        'syslog_server.web.api.alerts_api',
        'syslog_server.web.api.config_api',
        'syslog_server.web.ws',
        'syslog_server.web.ws.live',
        'syslog_server.web.broadcaster',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'PyQt5', 'PyQt6', 'tkinter', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SyslogServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,           # Console mode — needed for a service/daemon
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SyslogServer',
)
