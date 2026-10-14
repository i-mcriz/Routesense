@echo off
setlocal
title RouteSense AI - Automated Test Suite

cd /d "%~dp0"

echo ======================================================================
echo           RouteSense AI - Automated Regression Test Suite
echo ======================================================================
echo.

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

python tests\test_routing.py

echo.
pause
