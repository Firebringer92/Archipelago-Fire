@echo off
setlocal
cd /d "%~dp0"

echo KOTOR Archipelago Randomizer - Uninstaller
echo.
echo This reverts everything Install.bat set up: restores your original
echo binkw32.dll, reverts any door-randomization/item-suppression file
echo edits, and removes the Override files the installer added.
echo.

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

%PYCMD% scripts\install_playerbundle.py --uninstall

echo.
echo ============================================
echo Uninstall finished. Review the output above.
echo ============================================
pause
endlocal
