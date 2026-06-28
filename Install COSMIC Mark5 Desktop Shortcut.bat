@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop=[Environment]::GetFolderPath('Desktop'); $target=Join-Path (Get-Location) 'Start COSMIC Mark5.bat'; $shortcut=Join-Path $desktop 'COSMIC Mark5 Launcher.lnk'; $ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut($shortcut); $s.TargetPath=$target; $s.WorkingDirectory=(Get-Location).Path; $icon=Join-Path (Get-Location) 'assets\cosmic.ico'; if(Test-Path $icon){$s.IconLocation=$icon}; $s.Save(); Write-Host 'Created/updated:' $shortcut"
echo.
pause
