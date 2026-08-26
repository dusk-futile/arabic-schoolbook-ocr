@echo off
REM One-time setup for Windows. No administrator rights required.
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where uv >nul 2>nul
if errorlevel 1 (
  echo [1/4] Installing uv ^(user-local^)...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" || goto :fail
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo [2/4] Python 3.11 + dependencies...
uv python install 3.11 || goto :fail
uv venv --python 3.11 .venv || goto :fail
uv pip install --python .venv -r requirements.txt || goto :fail

if not exist ".mm-tess\Library\bin\tesseract.exe" (
  echo [3/4] Tesseract 5 ^(user-local, no admin^)...
  if not exist "%USERPROFILE%\.local\mm\micromamba.exe" (
    mkdir "%USERPROFILE%\.local\mm" 2>nul
    powershell -ExecutionPolicy ByPass -c "Invoke-WebRequest -Uri 'https://micro.mamba.pm/api/micromamba/win-64/latest' -OutFile '%TEMP%\mm.tar.bz2'; tar -xf '%TEMP%\mm.tar.bz2' -C '%USERPROFILE%\.local\mm' Library/bin/micromamba.exe; Move-Item -Force '%USERPROFILE%\.local\mm\Library\bin\micromamba.exe' '%USERPROFILE%\.local\mm\micromamba.exe'" || goto :fail
  )
  set "MAMBA_ROOT_PREFIX=%USERPROFILE%\.local\mm"
  "%USERPROFILE%\.local\mm\micromamba.exe" create -y -q -p .mm-tess -c conda-forge tesseract || goto :fail
) else (
  echo [3/4] Tesseract already present.
)

echo [4/4] Models and dictionaries...
".venv\Scripts\python.exe" -m mubsir.fetch_models || goto :fail
echo.
echo Setup complete. Double-click run.bat
exit /b 0
:fail
echo Setup failed.
pause
exit /b 1
