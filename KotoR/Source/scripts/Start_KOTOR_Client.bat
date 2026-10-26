@echo off
setlocal
cd /d "%~dp0"

rem Starts the KOTOR Archipelago client from this folder, with the Python that Install.bat found (recorded in python_path.txt). Any arguments are passed on.
set "PYEXE="
if exist "%LOCALAPPDATA%\KotorAP\python_path.txt" set /p PYEXE=<"%LOCALAPPDATA%\KotorAP\python_path.txt"
if not defined PYEXE goto FIND_PYTHON
if exist "%PYEXE%" goto RUN
set "PYEXE="

:FIND_PYTHON
rem No recorded Python (or it was moved): ask the py launcher for a supported one by name, then fall back to a plain "python" in the supported range.
for %%V in (3.13 3.12 3.11) do (
    if not defined PYEXE (
        py -%%V -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PYEXE=py -%%V"
    )
)
if not defined PYEXE (
    python -c "import sys; sys.exit(0 if (3, 11, 9) <= sys.version_info < (3, 14) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)
if defined PYEXE goto RUN_FOUND
echo.
echo ERROR: no supported Python was found. Run Install.bat first: it finds Python 3.12 or 3.13
echo and installs what the client needs.
echo.
pause
exit /b 1

:RUN
"%PYEXE%" KotorClient.py %*
goto DONE

:RUN_FOUND
%PYEXE% KotorClient.py %*

:DONE
if errorlevel 1 (
    echo.
    echo The client stopped with an error. If it did not say why above, run Install.bat again
    echo and then start the client again.
    pause
)
endlocal
