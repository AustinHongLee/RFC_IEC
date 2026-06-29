@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================
echo    Weld Joint Management System
echo    Hankou Guanli Xitong
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found.
  echo Install Python 3.10+ from https://www.python.org
  echo and tick "Add Python to PATH" during setup, then re-run.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo First run: creating virtual environment...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"

rem Use "python -m pip" (NOT pip.exe) so org Device Guard / WDAC does not block it.
python -c "import fastapi, uvicorn, openpyxl, multipart" 1>nul 2>nul
if not errorlevel 1 goto run

echo Installing packages ^(about 1 min^)...
python -m pip install --disable-pip-version-check --no-input -r requirements.txt
python -c "import fastapi" 1>nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERROR] Package installation failed.
  echo If a Device Guard / policy block appeared on pip.exe, this script already
  echo avoids it by using "python -m pip". If it still fails, contact IT, or try:
  echo     python -m pip install --user -r requirements.txt
  pause
  exit /b 1
)

:run
echo.
echo Starting server... your browser will open http://127.0.0.1:8000
echo To stop the system: press Ctrl+C in this window.
echo.
python app.py
pause
