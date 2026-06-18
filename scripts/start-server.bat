@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
set "APP_DIR=%ROOT%\personal-system-v2"
set "URL=http://127.0.0.1:5000"

cd /d "%APP_DIR%"
if errorlevel 1 goto err_dir

set "PYTHON=python"
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 goto err_python
    set "PYTHON=py -3"
)

netstat -ano | findstr ":5000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Server is already running.
    start "" "%URL%"
    ping 127.0.0.1 -n 4 >nul
    exit /b 0
)

title Personal OS - http://127.0.0.1:5000
echo ========================================
echo   Personal OS - Starting...
echo   URL: %URL%
echo   Close this window to stop the server.
echo ========================================
echo.

start /b cmd /c "ping 127.0.0.1 -n 4 >nul && start "" %URL%"

%PYTHON% app.py
if errorlevel 1 goto err_start
exit /b 0

:err_dir
echo [ERROR] App directory not found: %APP_DIR%
pause
exit /b 1

:err_python
echo [ERROR] Python not found. Install Python 3.11+ first.
pause
exit /b 1

:err_start
echo.
echo [ERROR] Server failed to start. Check messages above.
pause
exit /b 1