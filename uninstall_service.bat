@echo off
title Syslog Server - Uninstall Service
setlocal

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click and select "Run as administrator".
    pause
    exit /b 1
)

set "SERVICE_NAME=SyslogServer"
set "INSTALL_DIR=%ProgramFiles%\SyslogServer"

echo.
echo ===================================================
echo   Syslog Server - Service Uninstaller
echo ===================================================
echo.

sc query "%SERVICE_NAME%" >nul 2>&1
if errorlevel 1 (
    echo Service "%SERVICE_NAME%" not found, nothing to remove.
) else (
    echo Stopping service...
    sc stop "%SERVICE_NAME%" >nul 2>&1
    timeout /t 3 /nobreak >nul
    echo Removing service...
    sc delete "%SERVICE_NAME%"
    echo Service removed.
)

set /p "REMOVE_FILES=Remove installed files from %INSTALL_DIR%? (y/n): "
if /i "%REMOVE_FILES%"=="y" (
    rd /s /q "%INSTALL_DIR%" 2>nul
    echo Files removed.
)

echo.
echo Uninstall complete.
pause
endlocal
