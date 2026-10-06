@echo off
setlocal
cd /d "%~dp0"

echo KOTOR Archipelago Randomizer - Uninstaller
echo.
echo This reverts everything Install.bat set up: restores your original
echo binkw32.dll, reverts any door-randomization/item-suppression file
echo edits, and removes the Override files the installer added.
echo.

rem Archipelago supports Python 3.11.9 through 3.13.x only, and Kivy has no
rem wheel for 3.14, so "py -3" (the newest installed) can pick an unusable
rem Python. Ask the py launcher for 3.13, 3.12, then 3.11 by name, and fall
rem back to a plain "python" only if it is inside the supported range.
set "PYCMD="
for %%V in (3.13 3.12 3.11) do (
    if not defined PYCMD (
        py -%%V -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PYCMD=py -%%V"
    )
)
if not defined PYCMD (
    python -c "import sys; sys.exit(0 if (3, 11, 9) <= sys.version_info < (3, 14) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    echo.
    echo ERROR: no supported Python found. This needs Python 3.12 or 3.13
    echo ^(3.11.9 or newer 3.11 also works^). Python 3.14 does not work: the
    echo Archipelago client refuses to run on it. Install 3.12 or 3.13 from
    echo https://www.python.org/ ^(you can keep 3.14 installed alongside it^),
    echo then run this again. To see what is installed, open a Command
    echo Prompt and run:  py -0p
    echo.
    pause
    exit /b 1
)
echo Using: %PYCMD%

%PYCMD% scripts\install_playerbundle.py --uninstall

echo.
echo ============================================
echo Uninstall finished. Review the output above.
echo ============================================
pause
endlocal
