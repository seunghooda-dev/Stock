@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found: .venv\Scripts\python.exe
    echo Run setup first, then try again.
    pause
    exit /b 1
)

echo Starting Stock Telegram Bot...
echo Workspace: %cd%
echo Press Ctrl+C to stop.
echo.

".venv\Scripts\python.exe" "stock_telegram_bot.py"

echo.
echo Stock Telegram Bot stopped.
pause
