@echo off
title Syslog Server - Install Service
setlocal

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click and select "Run as administrator".
    pause
    exit /b 1
)

set "INSTALL_DIR=%ProgramFiles%\SyslogServer"
set "EXE=%INSTALL_DIR%\SyslogServer.exe"
set "SERVICE_NAME=SyslogServer"
set "DISPLAY_NAME=Syslog Server"

echo.
echo ===================================================
echo   Syslog Server - Service Installer
echo ===================================================
echo.
echo Install directory : %INSTALL_DIR%
echo Service name      : %SERVICE_NAME%
echo.

:: Copy files to install directory
echo Copying files...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy /E /I /Y "%~dp0*" "%INSTALL_DIR%\" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy files.
    pause
    exit /b 1
)
echo Files copied OK.

:: Remove existing service if present
sc query "%SERVICE_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo Removing existing service...
    sc stop "%SERVICE_NAME%" >nul 2>&1
    timeout /t 2 /nobreak >nul
    sc delete "%SERVICE_NAME%" >nul 2>&1
    timeout /t 1 /nobreak >nul
)

:: Create the Windows service
echo Creating service...
sc create "%SERVICE_NAME%" ^
    binPath= "\"%EXE%\"" ^
    start= auto ^
    DisplayName= "%DISPLAY_NAME%"
if errorlevel 1 (
    echo ERROR: Failed to create service.
    pause
    exit /b 1
)

sc description "%SERVICE_NAME%" "Syslog server with web UI. Access at http://localhost:8080"
sc failure "%SERVICE_NAME%" reset= 60 actions= restart/5000/restart/10000/restart/30000

:: Start the service
echo Starting service...
sc start "%SERVICE_NAME%"
if errorlevel 1 (
    echo WARNING: Service created but failed to start immediately.
    echo You can start it manually: sc start %SERVICE_NAME%
) else (
    echo Service started OK.
)

:: ── NTP: enable Windows Time Service as a network time server ────────────────
echo.
echo Configuring Windows Time Service as NTP server...

:: Enable the NTP server provider
reg add "HKLM\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpServer" /v Enabled /t REG_DWORD /d 1 /f >nul
if errorlevel 1 (
    echo WARNING: Could not enable W32Time NTP server provider.
) else (
    :: Mark this machine as a reliable time source for clients
    w32tm /config /reliable:yes /update >nul 2>&1

    :: Restart Windows Time Service to apply changes
    net stop W32Time >nul 2>&1
    net start W32Time >nul 2>&1

    :: Add inbound firewall rule for NTP (remove first to avoid duplicates)
    netsh advfirewall firewall delete rule name="NTP Server (UDP 123)" >nul 2>&1
    netsh advfirewall firewall add rule name="NTP Server (UDP 123)" dir=in action=allow protocol=UDP localport=123 >nul
    echo Windows Time Service configured as NTP server on UDP port 123.
)

echo.
echo ===================================================
echo   Installation complete!
echo   Web UI: http://localhost:8080
echo   (or use your server IP address)
echo   NTP : UDP port 123 (Windows Time Service)
echo ===================================================
echo.

:: Open browser
timeout /t 2 /nobreak >nul
start "" "http://localhost:8080"

pause
endlocal
