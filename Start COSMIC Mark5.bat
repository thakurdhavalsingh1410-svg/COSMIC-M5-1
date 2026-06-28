@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "COSMIC_STATE_DIR=%LOCALAPPDATA%\COSMIC\Mark5"
set "COSMIC_WEB_PORT=8775"
set "COSMIC_VOICE_ENGINE=windows"
set "COSMIC_PHONE_ACCESS=1"
set "COSMIC_PERFORMANCE_MODE=performance"
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
  echo Python was not found. Install Python 3.12 or activate COSMIC's venv.
  pause
  exit /b 1
)

title COSMIC Mark5
echo Starting COSMIC Mark5 desktop + web console on http://localhost:8775
%COSMIC_PY% main.py --phone --open-web
echo.
echo COSMIC Mark5 stopped. If there was an error, copy it and send it to Codex.
pause
