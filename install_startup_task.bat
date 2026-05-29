@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=StockTelegramBot"
set "TASK_CMD=%~dp0run_stock_bot_headless.bat"

echo Installing Windows startup task: %TASK_NAME%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$action = New-ScheduledTaskAction -Execute $env:TASK_CMD; $trigger = New-ScheduledTaskTrigger -AtLogOn; Register-ScheduledTask -TaskName $env:TASK_NAME -Action $action -Trigger $trigger -Description 'Stock Telegram Bot realtime scanner' -Force | Out-Null"
if errorlevel 1 (
    echo [ERROR] Failed to install startup task.
    pause
    exit /b 1
)

echo Startup task installed.
echo The bot will start automatically when this Windows user logs in.
echo You can also start it now by running:
echo schtasks /Run /TN "%TASK_NAME%"
pause
