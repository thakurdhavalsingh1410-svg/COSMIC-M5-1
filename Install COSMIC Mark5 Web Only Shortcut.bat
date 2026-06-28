@echo off
setlocal
title Install COSMIC Mark5 Web Only Shortcut

set "MARK5_DIR=%~dp0"
set "TARGET=%MARK5_DIR%Start COSMIC Mark5 Web Only.bat"
set "SHORTCUT=%USERPROFILE%\OneDrive\Desktop\COSMIC Mark5 Web Only.lnk"
set "ICON=%MARK5_DIR%assets\cosmic.ico"

if not exist "%TARGET%" (
  echo Missing target:
  echo %TARGET%
  pause
  exit /b 1
)

set "COSMIC_SHORTCUT=%SHORTCUT%"
set "COSMIC_TARGET=%TARGET%"
set "COSMIC_WORKDIR=%MARK5_DIR%"
set "COSMIC_ICON=%ICON%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:COSMIC_SHORTCUT);" ^
  "$s.TargetPath=$env:ComSpec;" ^
  "$s.Arguments='/k ' + [char]34 + $env:COSMIC_TARGET + [char]34;" ^
  "$s.WorkingDirectory=$env:COSMIC_WORKDIR;" ^
  "$s.Description='Start COSMIC Mark5 in fast web-only mode.';" ^
  "if(Test-Path $env:COSMIC_ICON){$s.IconLocation=$env:COSMIC_ICON+',0'};" ^
  "$s.Save()"

echo.
echo Created shortcut:
echo %SHORTCUT%
echo.
pause
rem COSMIC_MARK5_DEDICATED_WEB_PORT: shortcut launches Mark5 Web Only on localhost:8775 through the launcher env.
