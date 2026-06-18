@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "FOUND=0"
set "ROUNDS=0"

:kill_round
set "KILLED=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    set "FOUND=1"
    set "KILLED=1"
    echo Stopping server PID %%P ...
    taskkill /PID %%P /F >nul 2>&1
)
set /a ROUNDS+=1
if "!KILLED!"=="1" if !ROUNDS! lss 5 (
    ping 127.0.0.1 -n 2 >nul
    goto kill_round
)

if "%FOUND%"=="0" (
    echo [INFO] No server listening on port 5000.
) else (
    call :server_running
    if errorlevel 1 (
        echo [OK] Server stopped.
    ) else (
        echo [WARN] Port 5000 may still be in use. Close Python manually if needed.
    )
)

ping 127.0.0.1 -n 3 >nul
exit /b 0

:server_running
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul 2>&1
exit /b %errorlevel%