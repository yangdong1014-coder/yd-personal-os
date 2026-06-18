@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
set "APP_DIR=%ROOT%\personal-system-v2"
set "URL=http://127.0.0.1:5000"
set "MODE=%~1"

cd /d "%APP_DIR%"
if errorlevel 1 goto err_dir

set "PYTHON=python"
set "PYTHONW="
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 goto err_python
    set "PYTHON=py -3"
) else (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYTHONW if exist "%%~dpPpythonw.exe" set "PYTHONW=%%~dpPpythonw.exe"
    )
)

if /i "%MODE%"=="launch" goto launch_mode

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
echo   Tip: use desktop shortcut to start without this window.
echo ========================================
echo.

start /b cmd /c "ping 127.0.0.1 -n 4 >nul && start "" %URL%"

%PYTHON% app.py
if errorlevel 1 goto err_start
exit /b 0

:launch_mode
call :server_running
if errorlevel 1 goto launch_start
start "" "%URL%"
exit /b 0

:launch_start
set "PERSONAL_OS_BG=1"
if defined PYTHONW (
    start "" "%PYTHONW%" "%APP_DIR%\app.py"
) else (
    start "" /MIN cmd /c "set PERSONAL_OS_BG=1&& cd /d "%APP_DIR%" && %PYTHON% app.py"
)

call :wait_for_server 30
if errorlevel 1 goto err_start
start "" "%URL%"
exit /b 0

:server_running
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul 2>&1
exit /b %errorlevel%

:wait_for_server
set "TRIES=%~1"
if "%TRIES%"=="" set "TRIES=30"
set /a COUNT=0
:wait_loop
call :server_running
if not errorlevel 1 exit /b 0
set /a COUNT+=1
if %COUNT% geq %TRIES% exit /b 1
ping 127.0.0.1 -n 2 >nul
goto wait_loop

:err_dir
echo [ERROR] App directory not found: %APP_DIR%
if /i not "%MODE%"=="launch" pause
exit /b 1

:err_python
echo [ERROR] Python not found. Install Python 3.11+ first.
if /i not "%MODE%"=="launch" pause
exit /b 1

:err_start
echo [ERROR] Server failed to start.
if /i not "%MODE%"=="launch" pause
exit /b 1