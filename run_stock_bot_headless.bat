@echo off
setlocal
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

if not exist ".venv\Scripts\python.exe" (
    echo [%date% %time%] Python virtual environment not found. >> "logs\bot.log"
    exit /b 1
)

echo [%date% %time%] Starting Stock Telegram Bot. >> "logs\bot.log"
".venv\Scripts\python.exe" "stock_telegram_bot.py" >> "logs\bot.log" 2>&1
echo [%date% %time%] Stock Telegram Bot stopped. >> "logs\bot.log"
