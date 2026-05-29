@echo off
setlocal

set "TASK_NAME=StockTelegramBot"

echo Removing Windows startup task: %TASK_NAME%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$task = Get-ScheduledTask -TaskName $env:TASK_NAME -ErrorAction SilentlyContinue; if ($task) { Unregister-ScheduledTask -TaskName $env:TASK_NAME -Confirm:$false; Write-Host 'Startup task removed.' } else { Write-Host 'Startup task does not exist.' }"
if errorlevel 1 (
    echo [WARN] Task may not exist or could not be removed.
)
pause
