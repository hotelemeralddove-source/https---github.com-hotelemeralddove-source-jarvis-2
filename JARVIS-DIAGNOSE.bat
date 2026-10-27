@echo off
REM ===========================================================================
REM  JARVIS-DIAGNOSE - the same app, but the window stays and says everything.
REM
REM  Use this when JARVIS.bat seems to do nothing. It starts the app in a VISIBLE
REM  console, with the window shown (no stealth), so any error is on screen
REM  instead of inside a process that vanished.
REM ===========================================================================
setlocal
title JARVIS - diagnose
cd /d "%~dp0"
set "LOG=%~dp0jarvis-diagnose-log.txt"
>"%LOG%" echo JARVIS diagnose - %DATE% %TIME%

call "%~dp0tools\find_project.bat"
if not defined PROJ goto :wrongfolder
cd /d "%PROJ%"
echo   project folder : %PROJ%
>>"%LOG%" echo project folder: %PROJ%

set "VPY=%PROJ%\.venv\Scripts\python.exe"
if exist "%VPY%" goto :run

echo   no .venv yet - run JARVIS.bat once, it builds one.
echo   python on PATH: 
where python 2>nul
where py 2>nul
>>"%LOG%" echo no venv
pause
exit /b 1

:run
echo   python         : %VPY%
"%VPY%" -c "import sys;print('   python version :',sys.version.split()[0])"
echo.
echo   starting the app in this window. say "hey jarvis" or press Ctrl+Alt+J.
echo   anything wrong will be printed here. close the window to stop it.
echo.
>>"%LOG%" echo running app in console
"%VPY%" "%PROJ%\run.py"
echo.
echo   the app exited. the last lines above are the reason.
echo   (also written to %LOG%)
pause
exit /b 0

:wrongfolder
echo   this file must sit inside the ArcDesk folder (the one with run.py).
pause
exit /b 1
