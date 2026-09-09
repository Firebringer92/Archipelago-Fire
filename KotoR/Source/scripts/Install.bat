@echo off
setlocal
cd /d "%~dp0"

echo KOTOR Archipelago Randomizer - Installer
echo.
echo If KOTOR is installed in the default Steam location, just press Enter.
echo Otherwise, paste the full path to your KOTOR install folder (the one
echo containing swkotor.exe) and press Enter.
echo.
set "GAMEDIR="
set /p GAMEDIR="KOTOR install folder (or press Enter for default): "

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYCMD=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYCMD=python"
    ) else (
        echo.
        echo ERROR: Python was not found. Install Python 3.12 or 3.13 from
        echo https://www.python.org/ first, then run this again.
        echo.
        pause
        exit /b 1
    )
)

echo.
if "%GAMEDIR%"=="" (
    %PYCMD% scripts\install_playerbundle.py
) else (
    %PYCMD% scripts\install_playerbundle.py --game-dir "%GAMEDIR%"
)

echo.
echo ============================================
echo Install finished. Review the output above.
echo ============================================
pause
endlocal
