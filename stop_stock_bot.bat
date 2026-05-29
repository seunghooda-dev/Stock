@echo off
setlocal

echo Stopping Stock Telegram Bot processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*stock_telegram_bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo Done.
pause
