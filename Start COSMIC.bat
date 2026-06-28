@echo off
setlocal
set PYTHONDONTWRITEBYTECODE=1
title COSMIC Launcher

cd /d "%~dp0"

echo.
echo ==========================================
echo              COSMIC LAUNCHER
echo ==========================================
echo.
echo Starting COSMIC from:
echo %CD%
echo.

set "COSMIC_PY="

if exist ".venv\Scripts\python.exe" (
    set "COSMIC_PY=.venv\Scripts\python.exe"
)

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
    echo.
    echo Install Python 3.12, then run:
    echo pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Using Python command:
echo %COSMIC_PY%
echo.
echo Opening COSMIC desktop app, web dashboard, and phone access...
echo.

%COSMIC_PY% main.py --phone --open-web

if errorlevel 1 (
    echo.
    echo COSMIC stopped with an error.
    echo If this is the first run, install requirements first:
    echo pip install -r requirements.txt
    echo playwright install
    echo.
    pause
)



