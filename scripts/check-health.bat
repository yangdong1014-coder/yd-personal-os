@echo off
setlocal EnableExtensions

set "URL=http://127.0.0.1:5000/api/health"

where curl >nul 2>&1
if not errorlevel 1 (
    curl -s -f "%URL%"
    if errorlevel 1 goto fail
    echo.
    echo [OK] Server is healthy.
    exit /b 0
)

python -c "import urllib.request,sys; r=urllib.request.urlopen('%URL%', timeout=5); print(r.read().decode()); sys.exit(0 if r.status==200 else 1)" 2>nul
if errorlevel 1 goto fail
echo [OK] Server is healthy.
exit /b 0

:fail
echo [ERROR] Health check failed. Is the server running?
exit /b 1