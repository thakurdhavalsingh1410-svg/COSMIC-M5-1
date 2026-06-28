@echo off
setlocal
set PYTHONDONTWRITEBYTECODE=1
cd /d "%~dp0"
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
if not defined COSMIC_PY set "COSMIC_PY=python"
%COSMIC_PY% -m voice.voice_manager list
echo.
pause
