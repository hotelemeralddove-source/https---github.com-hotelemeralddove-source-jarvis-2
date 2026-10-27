@echo off
REM Arc Desk - optional voice backend. Installs speech engines only, no models.
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

if exist .venv\Scripts\python.exe (
  set "PY=.venv\Scripts\python.exe"
) else (
  REM No environment yet: find Python, or fetch it. Never assume it is there.
  call "%~dp0tools\pybootstrap.bat"
  if errorlevel 1 goto :fail
)

echo [Arc Desk] installing voice backend (vosk + sounddevice) ...
%PY% -m pip install --quiet -r requirements-voice.txt || goto :fail

echo.
echo [Arc Desk] downloading the 40 MB speech model ...
%PY% arc_daemon.py --download-model

echo.
echo [Arc Desk] done. In the app: click "WAKE OFF" in the header, then say "Hey Jarvis".
echo            Test without a mic first:  menu -^> "Test wake word (no mic)"
echo.
echo With these installed, "BYE JARVIS" can also CLOSE the app and keep a launcher
echo listening, so "HEY JARVIS" starts it again. Settings -^> On "BYE JARVIS".
echo Without them the app stays open on "bye jarvis" and tells you why - it never
echo quits and leaves you with nothing to call it back.
pause
exit /b 0

:fail
echo [Arc Desk] voice setup failed. The line above says why; if it was Python, the
echo            two-click route is written out above. The model download also needs
echo            internet - check the connection and run this again.
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
echo   Pick one:
echo     1) You have ArcDesk.exe (installer or portable zip)? You need none of this.
echo     2) You have the project folder (run.py + requirements.txt)? Unzip the fix
echo        pack INTO it and double-click this file again.
echo     3) Neither? Clone it with GitHub Desktop, then run this file inside it.
echo.
pause
exit /b 1
