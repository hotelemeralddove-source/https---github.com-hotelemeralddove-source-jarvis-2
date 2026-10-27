@echo off
REM ============================================================================
REM  Arc Desk - START (with the lights on).  Double-click it.
REM
REM  Use this when the desktop shortcut does nothing. A black window stays open
REM  while Arc Desk starts, so if it fails you SEE the reason instead of
REM  silence. This is the single most useful file when something will not open.
REM
REM  Two kinds of Arc Desk install are handled:
REM    * a package (ArcDesk.exe)   - started with --show
REM    * a source copy (run.py)    - started with this folder's .venv, or with
REM                                  the Python on this PC
REM ============================================================================
setlocal
cd /d "%~dp0"
echo ====================================================================
echo  ARC DESK - starting with a visible console
echo ====================================================================
echo  If anything fails, the reason stays on this screen.
echo.

set "FROZEN="
if exist "%~dp0ArcDesk.exe" set "FROZEN=%~dp0ArcDesk.exe"
if not defined FROZEN if exist "%~dp0dist\ArcDesk\ArcDesk.exe" set "FROZEN=%~dp0dist\ArcDesk\ArcDesk.exe"
if not defined FROZEN if exist "%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe" set "FROZEN=%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe"

if defined FROZEN goto :packaged
if exist "%~dp0run.py" goto :source
goto :nothing

:packaged
echo  Package: %FROZEN%
echo.
echo  Starting ...
"%FROZEN%" --show
set "RC=%ERRORLEVEL%"
echo.
echo  Arc Desk exited with code %RC%.
if not "%RC%"=="0" echo  That code is the reason: 0xc0000142 means a missing VC++ runtime or a
if not "%RC%"=="0" echo  build made with the Microsoft Store Python. Send this window to me.
goto :end

:source
echo  Source copy: %~dp0run.py
if exist "%~dp0.venv\Scripts\python.exe" goto :venv
echo  No .venv here, so this will use the Python on PATH.
where python >nul 2>nul
if errorlevel 1 goto :no_python
echo.
echo  Starting ...
python "%~dp0run.py" --show
set "RC=%ERRORLEVEL%"
goto :after_source

:venv
echo  Using .venv\Scripts\python.exe
echo.
echo  Starting ...
"%~dp0.venv\Scripts\python.exe" "%~dp0run.py" --show
set "RC=%ERRORLEVEL%"
goto :after_source

:after_source
echo.
echo  Arc Desk exited with code %RC%.
if not "%RC%"=="0" echo  Scroll up: the Python traceback above is the reason. Send it to me.
goto :end

:no_python
echo.
echo  There is no .venv folder and no python on PATH.
echo  A source copy needs both. Two ways forward:
echo    1. Use the packaged app instead: double-click ArcDesk.exe if you have it.
echo    2. Install Python from python.org, then run  install.bat  once.
goto :end

:nothing
echo  I cannot find ArcDesk.exe or run.py in this folder:
echo    %~dp0
echo.
echo  Put this file next to the app (or run it from the installed folder),
echo  then double-click again.

:end
echo.
echo ====================================================================
pause
endlocal
