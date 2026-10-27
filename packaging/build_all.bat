@echo off
REM ============================================================================
REM  Arc Desk - ONE command that produces ONE file to double-click.
REM
REM      packaging\build_all.bat        -> dist\ArcDeskSetup.exe
REM
REM  It does the boring parts so the person installing never has to:
REM     1. checks python + packages
REM     2. downloads ffmpeg + node ONCE (cached; this machine only, never the user's)
REM     3. runs the static pre-flight (spec / installer / uninstaller / paths)
REM     4. builds ArcDesk.exe + ArcDeskVoice.exe
REM     5. compresses everything into a per-user installer with Inno Setup
REM
REM  Run this ON WINDOWS. PyInstaller cannot cross-compile.
REM ============================================================================
setlocal enabledelayedexpansion
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

echo.
echo [1/6] python:
%PY% --version || goto :fail
echo.
echo [2/6] required packages ...
%PY% -c "import PySide6, psutil" || (
  echo   installing from requirements.txt ...
  %PY% -m pip install -r requirements.txt || goto :fail
)
REM The voice backends are part of the product, not an optional extra: the wake word
REM needs vosk + sounddevice, and voice lock needs sherpa-onnx. If they are missing at
REM BUILD time they are missing for the user forever, because a frozen EXE cannot pip
REM install anything later. That is why this is step 2 and not "see VOICE.md".
%PY% -c "import vosk, sherpa_onnx" || (
  echo   installing from requirements-voice.txt ^(vosk, sounddevice, sherpa-onnx^) ...
  %PY% -m pip install -r requirements-voice.txt || goto :fail
)
echo   ok
echo.
echo [3/6] portable runtimes (ffmpeg + node) - cached after the first run ...
%PY% packaging\fetch_runtime.py
if errorlevel 1 (
  echo.
  echo   WARNING: runtimes could not be fetched ^(offline?^).
  echo   The installer will still be built; media tools will honestly report
  echo   ffmpeg as missing instead of pretending it works.
  echo   Re-run this script when you have internet to include them.
)
echo.
echo [4/6] static pre-flight ...
%PY% tools\packaging.py || goto :fail
echo.
echo [5/6] building the two executables ...
if exist packaging\work rmdir /S /Q packaging\work
if exist dist\ArcDesk rmdir /S /Q dist\ArcDesk
%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath packaging\work packaging\arcdesk.spec || goto :fail
%PY% tools\sizecheck.py --dist dist\ArcDesk
echo.
echo [6/6] compressing into one installer ...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo   Inno Setup 6 not found. Install it free, once:
  echo       winget install JRSoftware.InnoSetup
  echo   Then run this script again - steps 1-5 are already done and cached.
  goto :done_no_installer
)
%ISCC% /Qp packaging\arcdesk.iss || goto :fail
echo.
echo   ============================================================
if exist dist\ArcDeskSetup.exe (
  for %%F in (dist\ArcDeskSetup.exe) do echo    READY:  dist\ArcDeskSetup.exe   %%~zF bytes
  echo.
  echo    Double-click that one file on any Windows 11 PC.
  echo    No admin, no Python, no ffmpeg install, no PATH editing.
) else (
  echo    The compiler ran but produced no installer - see the log above.
)
echo   ============================================================
exit /b 0

:done_no_installer
echo   Steps 1-5 are done: dist\ArcDesk\ArcDesk.exe is ready to run as a folder.
exit /b 1

:fail
echo.
echo BUILD FAILED - nothing was installed and nothing on this PC was changed.
exit /b 1
