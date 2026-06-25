@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

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
  echo First run: creating virtual env and installing packages ^(about 1 min^)...
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip >nul
  pip install -r requirements.txt
) else (
  call ".venv\Scripts\activate.bat"
)

echo.
echo Starting server... your browser will open http://127.0.0.1:8000
echo To stop the system: press Ctrl+C in this window.
echo.
python app.py
pause
