@echo off
setlocal
cd /d "%~dp0"

echo Setting up Stock Telegram Bot on this Windows PC...

where py >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=python"
    ) else (
        echo [ERROR] Python 3 was not found.
        echo Install Python 3.11+ from https://www.python.org/downloads/windows/ and enable "Add python.exe to PATH".
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example.
    echo Open .env and fill TELEGRAM/KIS settings before running the bot.
) else (
    echo .env already exists. Keeping existing local secrets.
)

call "create_desktop_shortcuts.bat"

echo.
echo Setup complete.
echo Next step:
echo 1. Edit .env with Telegram/KIS settings.
echo 2. Run "StockBot_Check.bat" from Desktop.
echo 3. If readiness passes, run "StockBot_Run.bat" from Desktop.
pause
