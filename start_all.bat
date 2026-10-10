@echo off
rem RAG Studio launcher. Keeps the window open on error so it never "flash-closes".
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1" %*
echo.
echo ============================================================
echo  The services have stopped or the launcher failed.
echo  Check the logs under data\logs\.
echo  Press any key to close this window.
echo ============================================================
pause >nul
endlocal
