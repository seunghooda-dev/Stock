@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found: .venv\Scripts\python.exe
    echo Run setup_windows_pc.bat first, then try again.
    pause
    exit /b 1
)

echo Showing Stock Bot status...
echo.
".venv\Scripts\python.exe" "status_stock_bot.py"

echo.
pause
