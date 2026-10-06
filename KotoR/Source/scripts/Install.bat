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

echo.
echo Installing Archipelago's own base dependencies...
%PYCMD% -m pip install -r requirements.txt
if not %ERRORLEVEL%==0 (
    echo.
    echo ERROR: pip install -r requirements.txt failed -- see the output above.
    echo.
    pause
    exit /b 1
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
