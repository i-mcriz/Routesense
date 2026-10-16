@echo off
title Stop RouteSense AI
echo [*] Terminating RouteSense AI backend processes...

for /f "tokens=5" %%p in ('netstat -ano -p tcp 2^>nul ^| findstr /r /c:":5000 .*LISTENING"') do (
    echo [*] Stopping PID: %%p
    taskkill /F /PID %%p >nul 2>&1
)

echo [*] RouteSense AI background service stopped.
timeout /t 2 >nul
exit /b 0
