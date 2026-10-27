@echo off
REM ===========================================================================
REM  JARVIS - put the icon back on the Desktop and in the Start Menu.
REM
REM  Double-click this once and JARVIS opens from an icon, with no black window.
REM  Nothing else changes: no files are moved, no settings are touched, and
REM  running it twice is harmless (it repairs the shortcut instead of piling up).
REM
REM  The window stays open at the end so the result is readable.
REM ===========================================================================
setlocal
cd /d "%~dp0"
call "%~dp0tools\find_project.bat"
if not defined PROJ goto :wrongfolder
cd /d "%PROJ%"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY call "%~dp0tools\pybootstrap.bat"
if not defined PY goto :nopython

echo.
echo   Where this copy lives: %PROJ%
echo.
"%PY%" tools\shortcut.py
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto :done
echo   The shortcut could not be made. The reason is on the line above.
goto :end

:done
echo   A JARVIS icon is now on your Desktop and in Start ^> JARVIS.
echo   Next launch: click that icon - no black window, no .bat.
goto :end

:nopython
echo.
echo   Python is not on this PC yet. Double-click JARVIS.bat first - it installs
echo   Python by itself - and then run this file again.
goto :end

:wrongfolder
echo.
echo   This is not the JARVIS folder (no run.py next to this file).
echo   Unzip the release first, then double-click CREATE-SHORTCUT.bat inside it.

:end
echo.
pause
exit /b %RC%
