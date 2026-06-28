@echo off
setlocal
title COSMIC Phone Access

cd /d "%~dp0"

echo.
echo ==========================================
echo          COSMIC PHONE ACCESS
echo ==========================================
echo.
echo Starting COSMIC so your phone can connect.
echo Use Tailscale for mobile-data access outside home.
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
echo COSMIC will show phone links in the dashboard log.
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
