@echo off
setlocal
cd /d "%~dp0"

set "APP_DIR=%~dp0"
set "DESKTOP=%USERPROFILE%\Desktop"
set "RUN_FILE=%DESKTOP%\StockBot_Run.bat"
set "STOP_FILE=%DESKTOP%\StockBot_Stop.bat"
set "CHECK_FILE=%DESKTOP%\StockBot_Check.bat"
set "STATUS_FILE=%DESKTOP%\StockBot_Status.bat"
set "AI_BRIEF_FILE=%DESKTOP%\AIThemeBrief_Run.bat"
set "AI_BRIEF_ONCE_FILE=%DESKTOP%\AIThemeBrief_SendOnce.bat"

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

(
    echo @echo off
    echo cd /d "%APP_DIR%"
    echo call "run_readiness_check.bat"
) > "%CHECK_FILE%"

(
    echo @echo off
    echo cd /d "%APP_DIR%"
    echo call "show_stock_bot_status.bat"
) > "%STATUS_FILE%"

(
    echo @echo off
    echo cd /d "%APP_DIR%"
    echo call "run_ai_theme_brief_bot.bat"
) > "%AI_BRIEF_FILE%"

(
    echo @echo off
    echo cd /d "%APP_DIR%"
    echo call "run_ai_theme_brief_once.bat"
) > "%AI_BRIEF_ONCE_FILE%"

echo Desktop launchers created:
echo "%RUN_FILE%"
echo "%STOP_FILE%"
echo "%CHECK_FILE%"
echo "%STATUS_FILE%"
echo "%AI_BRIEF_FILE%"
echo "%AI_BRIEF_ONCE_FILE%"
