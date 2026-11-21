@echo off
setlocal
cd /d "%~dp0"

echo KOTOR 2 Archipelago Randomizer - Uninstaller
echo.
echo This reverts everything Install.bat and the client set up: takes the seed's files
echo out of your game's Override folder, puts back the module files and dialog.tlk the
echo client changed, and removes the extension (version.dll).
echo.

rem Archipelago supports Python 3.11.9 through 3.13.x only (see Install.bat).
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
    echo ^(3.11.9 or newer 3.11 also works^). Install 3.12 or 3.13 from
    echo https://www.python.org/ then run this again. To see what is installed,
    echo open a Command Prompt and run:  py -0p
    echo.
    pause
    exit /b 1
)
echo Using: %PYCMD%

if not exist "installer\install_bundle.py" (
    echo.
    echo ERROR: installer\install_bundle.py is missing. Run Uninstall.bat from the folder you
    echo extracted the KOTOR 2 PlayerBundle into.
    pause
    exit /b 1
)

%PYCMD% installer\install_bundle.py --uninstall
set "UNINSTALL_RESULT=%ERRORLEVEL%"
echo.
if not "%UNINSTALL_RESULT%"=="0" goto UNINSTALL_FAILED
echo ============================================
echo Uninstall finished.
echo If the text above lists anything under "need your attention", do those steps.
echo ============================================
pause
endlocal
exit /b 0

:UNINSTALL_FAILED
echo ============================================
echo Uninstall did NOT finish.
echo Scroll up to the message headed "UNINSTALL FAILED". It says what went wrong and
echo what to do. After you fix it, run Uninstall.bat again: that is safe.
echo If there is no such message, take a screenshot of this whole window and post
echo it where you downloaded the randomizer.
echo ============================================
pause
endlocal
exit /b 1
