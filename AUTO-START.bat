@echo off
REM ===========================================================================
REM  AUTO-START - "switch the laptop on and JARVIS is already running".
REM
REM  It starts HIDDEN: no window, no console, just the background process, the
REM  hotkeys and the wake word. Ctrl+Alt+J opens the window, Ctrl+Alt+Q quits.
REM
REM  Nothing here needs an administrator, and nothing is hidden from you: this is
REM  one value under HKEY_CURRENT_USER ... Run ("ArcDesk"), which appears in Task
REM  Manager -> Startup apps and which this file can remove again.
REM
REM  It also REPAIRS an entry that points at a folder that has moved or been
REM  renamed - which is exactly how auto-start "stopped working" before.
REM ===========================================================================
setlocal
title JARVIS - auto start
cd /d "%~dp0"

set "PROJ="
if exist "%~dp0tools\find_project.bat" call "%~dp0tools\find_project.bat"
if not defined PROJ goto :wrongfolder
for %%I in ("%PROJ%") do set "PROJ=%%~fI"
cd /d "%PROJ%"

set "VPY=%PROJ%\.venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"

echo.
echo   J A R V I S   -   auto start
echo   ---------------------------
echo   this folder : %PROJ%
echo.
"%VPY%" "%PROJ%\tools\autostart_set.py" status
if errorlevel 1 goto :unsupported

echo.
echo   1 = turn it ON   (starts hidden when the laptop starts)
echo   2 = turn it OFF  (nothing starts by itself)
echo   3 = repair the path (after moving or renaming this folder)
echo   4 = change nothing
echo.
choice /c 1234 /n /m "  your answer: "
if errorlevel 4 goto :nothing
if errorlevel 3 goto :repair
if errorlevel 2 goto :turnoff
goto :turnon

:turnon
echo.
"%VPY%" "%PROJ%\tools\autostart_set.py" on
goto :after

:turnoff
echo.
"%VPY%" "%PROJ%\tools\autostart_set.py" off
goto :after

:repair
echo.
"%VPY%" "%PROJ%\tools\autostart_set.py" repair
goto :after

:after
echo.
echo   That is all. Next time the laptop starts, JARVIS is already running in the
echo   background - say "hey jarvis", or press Ctrl+Alt+J.
echo.
pause
goto :eof

:nothing
echo.
echo   Nothing was changed.
echo.
pause
goto :eof

:unsupported
echo.
echo   This computer does not have the startup entry feature (Windows only).
echo   On Windows this file prints the exact registry value it would write.
echo.
pause
goto :eof

:wrongfolder
echo.
echo   This file has to sit inside the JARVIS folder (next to run.py).
echo.
pause
goto :eof
