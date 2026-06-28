@echo off
setlocal
set PYTHONDONTWRITEBYTECODE=1
set COSMIC_VOICE_ENGINE=windows
set COSMIC_PERFORMANCE_MODE=performance
title COSMIC Mark5 Launcher

cd /d "%~dp0"

echo.
echo ==========================================
echo            COSMIC MARK5 PERFORMANCE
echo ==========================================
echo.
echo Starting COSMIC Mark5 from:
echo %CD%
echo.

set "COSMIC_PY="
if exist ".venv\Scripts\python.exe" set "COSMIC_PY=.venv\Scripts\python.exe"
if not defined COSMIC_PY (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 set "COSMIC_PY=py -3.12"
)
if not defined COSMIC_PY (
    py -3 --version >nul 2>nul
    if not errorlevel 1 set "COSMIC_PY=py -3"
)
if not defined COSMIC_PY (
    python --version >nul 2>nul
    if not errorlevel 1 set "COSMIC_PY=python"
)
if not defined COSMIC_PY (
    echo Python was not found.
    pause
    exit /b 1
)
echo Using Python command:
echo %COSMIC_PY%
echo.
%COSMIC_PY% main.py --phone --open-web
if errorlevel 1 (
    echo.
    echo COSMIC Mark5 stopped with an error.
    echo Run "Run COSMIC Mark5 Self Check.bat" for diagnostics.
    echo.
    pause
)
