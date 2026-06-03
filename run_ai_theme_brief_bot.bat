@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found: .venv\Scripts\python.exe
    echo Run setup_windows_pc.bat first, then try again.
    pause
    exit /b 1
)

echo Starting AI Theme Brief Bot...
echo It will send the brief every day at 08:00 KST.
echo Press Ctrl+C to stop.
echo.

".venv\Scripts\python.exe" "ai_theme_brief_bot.py"

echo.
echo AI Theme Brief Bot stopped.
pause
