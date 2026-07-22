@echo off
setlocal
cd /d "%~dp0"
set "OCR_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%OCR_PYTHON%" (
  echo The application is not installed yet.
  echo Run: powershell -ExecutionPolicy Bypass -File install_windows.ps1
  exit /b 1
)
start "" "http://127.0.0.1:8000"
"%OCR_PYTHON%" -m uvicorn arabic_schoolbook_ocr.api:app --host 127.0.0.1 --port 8000
endlocal
