@echo off
setlocal
cd /d "%~dp0"

rem The client runs on Archipelago's own files and the pip step below reads Archipelago's requirements.txt from this folder, so this
rem folder has to be the Archipelago source folder with the bundle extracted into it.
if exist "requirements.txt" if exist "CommonClient.py" goto FOLDER_OK
echo.
echo ERROR: this is not an Archipelago folder, so the installer cannot continue.
echo.
echo Install.bat has to sit inside the Archipelago SOURCE folder, next to CommonClient.py
echo and requirements.txt. The randomizer's client runs on those Archipelago files, and
echo this installer installs Archipelago's libraries from that requirements.txt.
echo.
echo Folder checked: %CD%
if not exist "requirements.txt" echo   Missing here: requirements.txt
if not exist "CommonClient.py" echo   Missing here: CommonClient.py
echo.
echo What to do:
echo   1. Download Archipelago's source code: on the Archipelago releases page on GitHub,
echo      pick the version the KOTOR randomizer asks for and download "Source code (zip)".
echo      This is not the Windows installer.
echo   2. Extract it. The folder you get contains CommonClient.py and requirements.txt.
echo   3. Extract the KOTOR PlayerBundle zip INTO that same folder, so Install.bat ends up
echo      next to those two files. Choose to merge or replace if Windows asks.
echo   4. Run Install.bat again from that folder.
echo.
pause
exit /b 1
:FOLDER_OK

echo KOTOR Archipelago Randomizer - Installer
echo.
echo If KOTOR is installed in the default Steam location, just press Enter.
echo Otherwise, paste the full path to your KOTOR install folder (the one
echo containing swkotor.exe) and press Enter.
echo.
set "GAMEDIR="
set /p GAMEDIR="KOTOR install folder (or press Enter for default): "
rem Pasted paths often come with quotes or a trailing backslash; either one breaks the path once it is passed on.
rem The goto matters: a line is expanded before it runs, and the quote-stripping line below is a syntax error on an empty answer (just Enter), which closes the window.
if not defined GAMEDIR goto GAMEDIR_CLEAN
set "GAMEDIR=%GAMEDIR:"=%"
if not defined GAMEDIR goto GAMEDIR_CLEAN
if "%GAMEDIR:~-1%"=="\" set "GAMEDIR=%GAMEDIR:~0,-1%"
:GAMEDIR_CLEAN

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
if %ERRORLEVEL%==0 goto PIP_OK

rem Archipelago's requirements.txt installs KivyMD straight from GitHub, which needs Git. Only when pip failed and Git is missing do we
rem point at it (a machine that already has KivyMD but no Git installs fine, so Git is not checked up front).
git --version >nul 2>nul
if not errorlevel 1 goto PIP_FAILED
echo.
echo Git for Windows was not found. Archipelago installs one of its libraries
echo ^(KivyMD^) straight from GitHub, and that needs Git.
where winget >nul 2>nul
if errorlevel 1 goto GIT_MANUAL
echo.
set "ANSWER="
set /p ANSWER="Install Git now with winget? (Y/N): "
if /i not "%ANSWER%"=="Y" goto GIT_MANUAL
call winget install --id Git.Git -e --source winget
set "WINGET_RESULT=%ERRORLEVEL%"
if not "%WINGET_RESULT%"=="0" goto WINGET_FAILED
echo.
echo When the Git install above has finished, close this window, open a NEW
echo Command Prompt ^(an already open window will not see the new Git^) and run
echo Install.bat again.
echo.
pause
exit /b 1

:WINGET_FAILED
echo.
echo winget could not install Git ^(exit code %WINGET_RESULT%^). That is fine: install it by hand.

:GIT_MANUAL
echo.
echo 1. Download Git for Windows from https://git-scm.com/download/win
echo 2. Run the installer and keep the default options. In particular keep the one
echo    named "Git from the command line and also from 3rd-party software": that is
echo    what lets Windows find Git ^(it adds Git to your PATH^).
echo 3. Close this window, open a NEW Command Prompt ^(an already open window will not
echo    see the new Git^) and run Install.bat again.
echo.
echo If Git is already installed, Windows cannot find it: run the Git installer again
echo and keep the option named above.
echo.
pause
exit /b 1

:PIP_FAILED
echo.
echo ERROR: Archipelago's own libraries could not be installed -- see the output above.
echo.
echo What to do:
echo   1. Make sure this computer is connected to the internet, and turn off any VPN
echo      or proxy for a moment. The libraries are downloaded while this runs.
echo   2. Run Install.bat again. It is safe to run more than once.
echo   3. If it fails again, take a screenshot of this whole window and post it where
echo      you downloaded the randomizer. The last few lines above are the important ones.
echo.
pause
exit /b 1

:PIP_OK

echo.
if "%GAMEDIR%"=="" (
    %PYCMD% scripts\install_playerbundle.py
) else (
    %PYCMD% scripts\install_playerbundle.py --game-dir "%GAMEDIR%"
)
set "INSTALL_RESULT=%ERRORLEVEL%"
echo.
if not "%INSTALL_RESULT%"=="0" goto INSTALL_FAILED
echo ============================================
echo Install finished.
echo If the text above lists anything under "need your attention", do those steps.
echo Otherwise you are done with this step.
echo ============================================
pause
endlocal
exit /b 0

:INSTALL_FAILED
echo ============================================
echo Install did NOT finish.
echo Scroll up to the message headed "INSTALL FAILED". It says what went wrong and
echo what to do. After you fix it, run Install.bat again: that is safe.
echo If there is no such message, take a screenshot of this whole window and post
echo it where you downloaded the randomizer.
echo ============================================
pause
endlocal
exit /b 1
