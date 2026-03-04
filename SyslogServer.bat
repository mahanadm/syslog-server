@echo off
title Syslog Server
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
"C:\Users\Mahan\AppData\Local\Programs\Python\Python312\python.exe" -m syslog_server
if errorlevel 1 (
    echo.
    echo Syslog Server exited with an error. Press any key to close.
    pause >nul
)
