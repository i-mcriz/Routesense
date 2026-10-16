@echo off
setlocal enabledelayedexpansion
title RouteSense AI - Web App Launcher

cd /d "%~dp0"

:: 1. Check if backend is already listening and responding on http://127.0.0.1:5000
set "SERVER_READY=0"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/api/health' -TimeoutSec 1 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% equ 0 set "SERVER_READY=1"

:: 2. If not running, start server in background
if "!SERVER_READY!"=="0" (
    echo Starting RouteSense AI Backend...
    
    if exist ".venv\Scripts\pythonw.exe" (
        start "" ".venv\Scripts\pythonw.exe" backend\app.py
    ) else if exist ".venv\Scripts\python.exe" (
        start /min "RouteSense Server" ".venv\Scripts\python.exe" backend\app.py
    ) else (
        start /min "RouteSense Server" python backend\app.py
    )

    :: Wait up to 15 seconds for server readiness
    for /L %%i in (1,1,30) do (
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/api/health' -TimeoutSec 1 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "SERVER_READY=1"
            goto launch_browser
        )
        timeout /t 1 /nobreak >nul 2>&1
    )
)

:launch_browser
:: 3. Launch in standalone Web App Mode (Chromium --app mode)
set "BROWSER_EXE="

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
) else if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) else if exist "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
)

if defined BROWSER_EXE (
    start "" "!BROWSER_EXE!" --app=http://localhost:5000
) else (
    start http://localhost:5000
)

exit /b 0
