@echo off
rem First-run launcher: creates the venv, installs dependencies, then starts.
rem Keeps the window open on error so it never "flash-closes".
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1" -Install
echo.
echo ============================================================
echo  The services have stopped or the launcher failed.
echo  Check the logs under data\logs\.
echo  Press any key to close this window.
echo ============================================================
pause >nul
endlocal
