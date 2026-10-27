@echo off
REM Arc Desk - one-time setup. Creates a local venv so nothing global is touched.
setlocal

REM This file is one piece of the project, not the project. Find the real folder
REM first (the one holding run.py and requirements.txt) - see tools\find_project.bat.
call "%~dp0tools\find_project.bat"
if not defined PROJ goto :wrongfolder
cd /d "%PROJ%"
echo [Arc Desk] project folder: %PROJ%

REM Fail BEFORE building anything: a venv made in the wrong folder is a mess to
REM clean up, and this check is the difference between a clear message and
REM "Could not open requirements file".
if not exist "requirements.txt" goto :wrongfolder
if not exist "run.py" goto :wrongfolder

REM Python is not assumed. tools\pybootstrap.bat finds it, or downloads the official
REM installer from python.org (per-user, no administrator password) and finds it after.
REM The old version handed the problem back to the person; a laptop that had never
REM had Python answered with the Microsoft Store stub and a dead end.
call "%~dp0tools\pybootstrap.bat"
if errorlevel 1 goto :fail

echo [Arc Desk] creating virtual environment .venv ...
%PY% -m venv .venv || goto :fail
call .venv\Scripts\activate.bat

echo [Arc Desk] installing dependencies ...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt || goto :fail

echo.
echo [Arc Desk] done. Launch with:  start_arcdesk.vbs   (no console window)
echo            or:                  .venv\Scripts\python run.py
pause
exit /b 0

:fail
echo.
echo [Arc Desk] setup did not finish. The line above says which step stopped.
echo   Nothing outside this folder was changed, and nothing was installed globally.
echo   The likely cause is written above it (usually: this PC is offline).
pause
exit /b 1

:wrongfolder
echo.
echo [Arc Desk] This is not the project folder, so there is nothing to install here.
echo.
echo   What happened: a fix pack is a few files that belong INSIDE the ArcDesk
echo   project. Unzipped on its own there is no requirements.txt next to this .bat,
echo   so pip can only complain that the file is missing.
echo.
echo   What to do, pick one:
echo.
echo     1) You already have ArcDesk.exe (the installer or the portable zip)?
echo        Then you need none of this. Just run ArcDesk.exe.
echo.
echo     2) You have the project folder (it contains run.py and requirements.txt)?
echo        Unzip the fix pack INTO that folder and double-click install.bat again.
echo.
echo     3) Neither? Clone it with GitHub Desktop, then double-click install.bat
echo        inside the folder it created.
echo.
pause
exit /b 1
