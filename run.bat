@echo off
setlocal enabledelayedexpansion
title RouteSense AI - Disaster Evacuation Intelligence

cd /d "%~dp0"

if "%~1"=="--help"    goto show_help
if "%~1"=="-h"        goto show_help
if "%~1"=="--test"    goto run_tests
if "%~1"=="test"      goto run_tests
if "%~1"=="-t"        goto run_tests
if "%~1"=="--rebuild" goto rebuild_data
if "%~1"=="rebuild"   goto rebuild_data

echo ======================================================================
echo           RouteSense AI - Disaster Evacuation Intelligence
echo                    Fast Application Launcher
echo ======================================================================
echo.

:: 1. Free Port 5000 if occupied
for /f "tokens=5" %%p in ('netstat -ano -p tcp 2^>nul ^| findstr /r /c:":5000 .*LISTENING"') do (
    echo [*] Clearing existing process on port 5000 (PID: %%p)...
    taskkill /F /PID %%p >nul 2>&1
)

:: 2. Resolve Python Runtime
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    echo [*] Resolving system Python...
    set "SYSTEM_PYTHON="
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        if not defined SYSTEM_PYTHON set "SYSTEM_PYTHON=%%i"
    )
    if not defined SYSTEM_PYTHON (
        for /f "tokens=*" %%i in ('where py 2^>nul') do (
            if not defined SYSTEM_PYTHON set "SYSTEM_PYTHON=%%i"
        )
    )
    if not defined SYSTEM_PYTHON (
        echo.
        echo [ERROR] Python was not found in your PATH!
        echo Please install Python 3.10+ from https://www.python.org/
        pause
        exit /b 1
    )
    echo [*] Creating project virtual environment (.venv)...
    "!SYSTEM_PYTHON!" -m venv .venv
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    set "PIP_EXE=.venv\Scripts\pip.exe"
    echo [*] Installing required packages...
    "!PIP_EXE!" install -r requirements.txt
)

:: 3. Ensure environmental data files exist
if not exist "data\thrissur_waterways_v1.geojson" (
    echo [*] Generating Thrissur waterways and flood scenario datasets...
    "!PYTHON_EXE!" scripts\generate_thrissur_environmental_datasets.py
)

:: 4. Launch RouteSense AI Server (Auto-opens browser on ready)
echo.
echo ======================================================================
echo   URL:      http://localhost:5000
echo   Status:   Starting server...
echo   Tip:      Browser opens automatically once ready!
echo.
echo   Press Ctrl+C in this window to stop the server.
echo ======================================================================
echo.

"!PYTHON_EXE!" backend\app.py

if !ERRORLEVEL! neq 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Server exited with code: !ERRORLEVEL!
    echo ======================================================================
    pause
)
exit /b 0

:: ======================================================================
:: SUBROUTINES
:: ======================================================================

:run_tests
echo [RouteSense] Running Automated Test Suite...
echo.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tests\test_routing.py
) else (
    python tests\test_routing.py
)
echo.
pause
exit /b 0

:rebuild_data
echo [RouteSense] Rebuilding environmental datasets...
echo.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\generate_thrissur_environmental_datasets.py
) else (
    python scripts\generate_thrissur_environmental_datasets.py
)
echo.
pause
exit /b 0

:show_help
echo.
echo RouteSense AI - Application Launcher
echo.
echo USAGE:
echo   run.bat               Launch RouteSense AI web application
echo   run.bat --test        Run test suite (32 regression tests)
echo   run.bat --rebuild     Regenerate environmental datasets
echo   run.bat --help        Show this help message
echo.
pause
exit /b 0
