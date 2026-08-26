@echo off
REM mubsir - double-click to start (Windows)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up. This happens once.
  call setup.bat || goto :fail
)
".venv\Scripts\python.exe" -m mubsir.webui
goto :eof
:fail
echo Setup failed.
pause
