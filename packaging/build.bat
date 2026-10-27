@echo off
REM Arc Desk - build the two Windows binaries.
REM   dist\ArcDesk\ArcDesk.exe       the app
REM   dist\ArcDesk\ArcDeskVoice.exe  the ears (separate process, separate RAM)
REM Run this ON WINDOWS. PyInstaller cannot cross-compile from Linux.
setlocal
cd /d "%~dp0\.."

if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)

REM Step 0 is not optional any more. The Microsoft Store's Python alias (the dialog
REM titled AppInstallerPythonRedirector.exe) produces an exe that installs and then
REM dies with 0xc0000142 — the build looks fine, the user gets nothing. So the
REM interpreter, the MSVC runtime and the build path are judged BEFORE PyInstaller
REM spends two minutes producing something that cannot open.
%PY% tools\preflight_win.py
if errorlevel 1 (
  echo.
  echo   Fix the line^(s^) above and run this script again.
  echo   Nothing was built, nothing was changed on this PC.
  exit /b 1
)
echo.

echo [1/5] python:
%PY% --version
echo.
echo [2/5] required packages ...
%PY% -c "import PySide6, psutil" || (echo   PySide6/psutil missing: %PY% -m pip install -r requirements.txt & goto :fail)
echo   ok
echo.
echo [3/5] static pre-flight (everything PyInstaller would only tell you after 2 minutes) ...
%PY% tools\packaging.py --check || goto :fail
echo.
echo [4/5] cleaning previous output ...
if exist packaging\work rmdir /S /Q packaging\work
if exist dist\ArcDesk rmdir /S /Q dist\ArcDesk
echo.
echo [5/5] PyInstaller ...
%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath packaging\work packaging\arcdesk.spec || goto :fail

echo.
echo Built: dist\ArcDesk\ArcDesk.exe  and  dist\ArcDesk\ArcDeskVoice.exe
echo Optional: a real installer -^> packaging\make_installer.bat
exit /b 0

:fail
echo.
echo BUILD FAILED - nothing was installed, nothing was changed on this PC.
exit /b 1
