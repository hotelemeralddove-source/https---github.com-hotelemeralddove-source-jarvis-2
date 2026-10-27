@echo off
REM ===========================================================================
REM  ONE JARVIS, ONE PLACE - double-click this, answer one question.
REM
REM  It answers "which files are the correct ones?" by asking the app itself:
REM  the folder whose run.py is RUNNING right now is the real one, not a guess.
REM  Then it keeps that copy, parks the others in %USERPROFILE%\JARVIS-OLD,
REM  and tells you the single file to double-click from now on.
REM
REM  Nothing is deleted. Undo with:  tools\one_place.py --undo
REM ===========================================================================
setlocal enabledelayedexpansion
title JARVIS - one place
cd /d "%~dp0"
set "LOG=%~dp0jarvis-one-place-log.txt"
>"%LOG%" echo JARVIS one-place log - %DATE% %TIME%
>>"%LOG%" echo started from: %~dp0

set "PROJ="
if exist "%~dp0tools\find_project.bat" call "%~dp0tools\find_project.bat"
if not defined PROJ call :lookhere "%~dp0"
if not defined PROJ call :lookhere "%~dp0.."
if not defined PROJ call :lookhere "%~dp0..\.."
if not defined PROJ call :lookhere "%USERPROFILE%\JARVIS"
if not defined PROJ call :lookhere "%USERPROFILE%\Downloads\JARVIS"
if not defined PROJ call :scanfor "%USERPROFILE%\Downloads"
if not defined PROJ call :scanfor "%USERPROFILE%"
if not defined PROJ goto :notfound

set "VPY=%PROJ%\.venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"

echo.
echo   one JARVIS, one place
echo   --------------------
echo   project in use : %PROJ%
echo.
"%VPY%" "%PROJ%\tools\one_place.py" --report "%PROJ%\JARVIS-SCAN.txt"
>>"%LOG%" echo scan written to %PROJ%\JARVIS-SCAN.txt
echo.
echo   The same list is in %PROJ%\JARVIS-SCAN.txt
echo   Nothing has been changed yet.
echo.
choice /C YN /N /M "Keep one copy and park the rest  [Y = yes, N = no] "
if errorlevel 2 goto :declined

echo.
"%VPY%" "%PROJ%\tools\one_place.py" --apply --verify
>>"%LOG%" echo applied

echo.
echo   -------------------------------------------------------------
echo   From now on, ONE thing to double-click:
echo.
echo     %USERPROFILE%\JARVIS\JARVIS.bat
echo.
if exist "%USERPROFILE%\JARVIS\run.py" echo   that folder exists and has run.py - good.
if not exist "%USERPROFILE%\JARVIS\run.py" echo   (if that folder is not there yet, see the lines above)
echo   -------------------------------------------------------------
pause
exit /b 0

:declined
echo.
echo   Nothing was changed. The list above is what exists.
echo   Run this file again whenever you want to tidy it.
pause
exit /b 0

:notfound
echo.
echo   I cannot find a JARVIS folder anywhere I looked.
echo   Unzip ArcDesk-full-project.zip into  %USERPROFILE%\JARVIS
echo   and double-click JARVIS.bat in it.
echo.
echo   If you unzipped a FIX PACK as its own folder, double-click JARVIS.bat there
echo   instead - it finds the app and offers to apply itself.
pause
exit /b 1

:lookhere
if not defined PROJ if exist "%~1\run.py" if exist "%~1\requirements.txt" set "PROJ=%~1"
exit /b 0

:scanfor
if not defined PROJ if exist "%~1\run.py" if exist "%~1\requirements.txt" set "PROJ=%~1"
if defined PROJ exit /b 0
if not exist "%~1" exit /b 0
for /d %%D in ("%~1\*") do (
    if not defined PROJ if exist "%%D\run.py" if exist "%%D\requirements.txt" set "PROJ=%%D"
)
if defined PROJ exit /b 0
for /d %%D in ("%~1\*") do (
    for /d %%E in ("%%D\*") do (
        if not defined PROJ if exist "%%E\run.py" if exist "%%E\requirements.txt" set "PROJ=%%E"
    )
)
exit /b 0
