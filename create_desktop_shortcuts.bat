@echo off
setlocal
cd /d "%~dp0"

set "APP_DIR=%~dp0"
set "DESKTOP=%USERPROFILE%\Desktop"
set "RUN_FILE=%DESKTOP%\StockBot_Run.bat"
set "STOP_FILE=%DESKTOP%\StockBot_Stop.bat"

(
    echo @echo off
    echo cd /d "%APP_DIR%"
    echo call "run_stock_bot.bat"
) > "%RUN_FILE%"

(
    echo @echo off
    echo cd /d "%APP_DIR%"
    echo call "stop_stock_bot.bat"
) > "%STOP_FILE%"

echo Desktop launchers created:
echo "%RUN_FILE%"
echo "%STOP_FILE%"
