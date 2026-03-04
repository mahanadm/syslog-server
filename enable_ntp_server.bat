@echo off
:: Must be run as Administrator
:: Enables Windows Time Service (W32Time) to respond to NTP requests from network devices

echo Enabling Windows Time Service as NTP server...

:: Enable the NTP server provider
reg add "HKLM\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpServer" /v Enabled /t REG_DWORD /d 1 /f
if %ERRORLEVEL% neq 0 (
    echo ERROR: Registry change failed. Right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)

:: Mark this machine as a reliable time source
w32tm /config /reliable:yes /update

:: Restart Windows Time service
net stop W32Time
net start W32Time

:: Allow inbound NTP through Windows Firewall
netsh advfirewall firewall delete rule name="NTP Server (UDP 123)" >nul 2>&1
netsh advfirewall firewall add rule name="NTP Server (UDP 123)" dir=in action=allow protocol=UDP localport=123

echo.
echo Done. Windows Time Service is now serving NTP on UDP port 123.
echo Network devices should now be able to sync their clocks with this PC.
echo.
w32tm /query /status
pause
