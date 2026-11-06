@echo off
REM Windows harness
setlocal
cd /d "%~dp0"
chcp 65001 >nul

REM 1) Python 3.9+
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys;sys.exit(sys.version_info<(3,9))" >nul 2>&1 && set "PY=py -3")
if not defined PY (where python >nul 2>&1 && (python -c "import sys;sys.exit(sys.version_info<(3,9))" >nul 2>&1 && set "PY=python"))
if not defined PY (
  echo [X] Python 3.9+ not found. Install with:  winget install -e --id Python.Python.3.12
  pause & exit /b 1
)
echo [OK] Python found

REM 2) ffmpeg
where ffmpeg >nul 2>&1 && where ffprobe >nul 2>&1
if errorlevel 1 (
  echo [X] ffmpeg is not installed.
  where winget >nul 2>&1
  if errorlevel 1 (
    echo Download it from https://www.gyan.dev/ffmpeg/builds/ and add it to PATH.
    pause & exit /b 1
  )
  set /p A="Install now with winget? [Y/N] "
  if /i not "%A%"=="Y" ( echo ffmpeg is required. & pause & exit /b 1 )
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  echo.
  echo ffmpeg installed. CLOSE this window and run start.bat again to refresh PATH.
  pause & exit /b 0
)
echo [OK] ffmpeg

REM 3) venv + dependencies
if not exist .venv ( echo Creating virtual environment... & %PY% -m venv .venv )
call .venv\Scripts\activate.bat
echo Syncing dependencies...
python -m pip install -q --disable-pip-version-check -r requirements.txt

REM 4) .env
if not exist .env ( copy .env.example .env >nul & echo [!] .env created: add your API keys. )

echo Starting...
python app.py
if errorlevel 1 pause
