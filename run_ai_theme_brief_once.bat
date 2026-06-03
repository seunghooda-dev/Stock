@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found: .venv\Scripts\python.exe
    echo Run setup_windows_pc.bat first, then try again.
    pause
    exit /b 1
)

echo Sending AI Theme Brief once...
echo.

".venv\Scripts\python.exe" "ai_theme_brief_bot.py" --once

echo.
pause
