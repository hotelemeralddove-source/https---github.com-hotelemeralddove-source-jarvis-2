@echo off
REM ---------------------------------------------------------------------------
REM  Find the ArcDesk project folder and put it in %PROJ%.
REM
REM  Why this exists: a fix pack is a handful of files that sit INSIDE the
REM  project. Unzipped on its own, install.bat has no requirements.txt next to
REM  it and pip says "Could not open requirements file" - which looks like a bug
REM  in the app and is really the wrong folder.
REM
REM  So the installers do not trust their own location. They look for the one
REM  marker that cannot be faked: run.py next to requirements.txt.
REM
REM  Since fix43 it also looks TWO folders deep. The report that made this
REM  necessary: a fix pack unzipped to Downloads\arcdesk-fix42-... while the app
REM  itself sat in Downloads\JARVIS\arcdesk-src - one folder too deep for the old
REM  single-level scan, so the launcher announced "I cannot see the project files".
REM ---------------------------------------------------------------------------
set "PROJ="

if exist "%~dp0run.py" if exist "%~dp0requirements.txt" set "PROJ=%~dp0"
if not defined PROJ if exist "%~dp0..\run.py" if exist "%~dp0..\requirements.txt" set "PROJ=%~dp0.."
if not defined PROJ if exist "%~dp0..\..\run.py" if exist "%~dp0..\..\requirements.txt" set "PROJ=%~dp0..\.."
if not defined PROJ if exist "%~dp0..\..\..\run.py" if exist "%~dp0..\..\..\requirements.txt" set "PROJ=%~dp0..\..\.."

REM The places a person actually keeps it, deepest first.
if not defined PROJ call :scan "%USERPROFILE%\JARVIS"
if not defined PROJ call :scan "%USERPROFILE%\Documents\JARVIS"
if not defined PROJ call :scan "%USERPROFILE%\Downloads\JARVIS"
if not defined PROJ call :scan "%USERPROFILE%\Documents\GitHub"
if not defined PROJ call :scan "%USERPROFILE%\Desktop"
if not defined PROJ call :scan "%USERPROFILE%\OneDrive\Desktop"
if not defined PROJ call :scan "%USERPROFILE%\Downloads"

if defined PROJ for %%I in ("%PROJ%") do set "PROJ=%%~fI"
if defined PROJ exit /b 0
exit /b 1

REM :scan <root> - the root itself, then one level, then two.
:scan
if not defined PROJ if exist "%~1\run.py" if exist "%~1\requirements.txt" set "PROJ=%~1"
if defined PROJ goto :scanend
if not exist "%~1" goto :scanend
for /d %%D in ("%~1\*") do (
    if not defined PROJ if exist "%%D\run.py" if exist "%%D\requirements.txt" set "PROJ=%%D"
)
if defined PROJ goto :scanend
for /d %%D in ("%~1\*") do (
    for /d %%E in ("%%D\*") do (
        if not defined PROJ if exist "%%E\run.py" if exist "%%E\requirements.txt" set "PROJ=%%E"
    )
)
:scanend
exit /b 0
