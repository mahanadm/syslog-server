@echo off
title Syslog Server - Build
setlocal
cd /d "%~dp0"

echo.
echo ===================================================
echo   Syslog Server - PyInstaller Build
echo ===================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo Install Python 3.10+ from https://python.org and add it to PATH.
    pause
    exit /b 1
)

:: Install / upgrade build tools
echo Installing build dependencies...
python -m pip install --quiet --upgrade pyinstaller fastapi "uvicorn[standard]" tomli-w pydantic
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

:: Clean previous build
if exist dist\SyslogServer rd /s /q dist\SyslogServer
if exist build\SyslogServer rd /s /q build\SyslogServer

:: Run PyInstaller
echo.
echo Building executable (this may take a few minutes)...
python -m PyInstaller SyslogServer.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. Check output above.
    pause
    exit /b 1
)

:: Copy installer scripts into the dist folder
echo Copying installer scripts...
copy /y install_service.bat   dist\SyslogServer\ >nul
copy /y uninstall_service.bat dist\SyslogServer\ >nul
copy /y install_service.sh    dist\SyslogServer\ >nul
copy /y uninstall_service.sh  dist\SyslogServer\ >nul

:: Create distributable ZIP using PowerShell
set "VERSION=1.0.0"
set "ZIPFILE=dist\SyslogServer-v%VERSION%-Windows.zip"
echo Creating %ZIPFILE%...
powershell -Command "Compress-Archive -Path 'dist\SyslogServer\*' -DestinationPath '%ZIPFILE%' -Force"
if errorlevel 1 (
    echo WARNING: Could not create ZIP. The dist\SyslogServer\ folder is ready to distribute.
) else (
    echo ZIP created: %ZIPFILE%
)

echo.
echo ===================================================
echo   Build complete!
echo   Distribute: %ZIPFILE%
echo   End-users: unzip, run install_service.bat as Admin
echo ===================================================
echo.
pause
endlocal
