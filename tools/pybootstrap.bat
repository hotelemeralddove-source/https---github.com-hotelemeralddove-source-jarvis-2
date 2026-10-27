@echo off
REM ============================================================================
REM  Arc Desk - find Python, or fetch it. Called by install.bat and friends.
REM
REM    call tools\pybootstrap.bat            -> sets PY to a working interpreter
REM    if errorlevel 1 -> nothing could be done; the caller should stop
REM
REM  Why this file exists: the first version assumed Python was already there and
REM  printed "Is Python 3.10+ installed and on PATH?" - which is not an answer, it is
REM  the user's problem handed back to them. The rule for this project is one
REM  double-click and no manual dependency setup, so the script now does what a
REM  person would do: check, then download, then check again.
REM
REM  Two things it deliberately does NOT trust:
REM    * python.exe inside ...\WindowsApps\ - that is the Microsoft Store stub. It
REM      prints "Python was not found..." and opens the Store. It is not a Python.
REM    * a `where python` that only finds the stub - it is treated as "not installed".
REM ============================================================================
setlocal EnableExtensions

REM ---- the version this project is tested against (a full, pinned URL) ------
set "PYVER=3.12.8"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"
set "PYINSTALLER=%TEMP%\arcdesk-python-%PYVER%.exe"

REM ---------------------------------------------------------------- 1. already here?
call :probe
if not errorlevel 1 goto :done

echo.
echo   Python was not found on this PC.
echo.
echo   Arc Desk can fetch it for you: Python %PYVER% (64-bit, about 25 MB).
echo   It installs for THIS user only - no administrator password, nothing global
echo   is changed apart from a normal per-user Python under:
echo       %%LOCALAPPDATA%%\Programs\Python
echo.
echo   All three routes are tried automatically, in this order:
echo     1. winget (the official Windows package manager)
echo     2. the installer downloaded from python.org
echo.
choice /c YN /n /m "   Download and install Python now? [Y/N] "
if errorlevel 2 goto :declined

REM ---------------------------------------------------------------- 2. winget
where winget >nul 2>nul
if errorlevel 1 goto :direct
echo.
echo   [1/2] winget: installing Python.Python.%PYVER:~0,4% ...
winget install --id Python.Python.%PYVER:~0,4% -e --silent --scope user ^
    --accept-package-agreements --accept-source-agreements
call :probe
if not errorlevel 1 goto :done
echo   winget did not give us a usable Python. Falling back to python.org.

REM ---------------------------------------------------------------- 3. python.org
:direct
echo.
echo   [2/2] downloading python.org installer (about 25 MB) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue';" ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
  "try { Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYINSTALLER%' -UseBasicParsing; " ^
  "Write-Host ('  downloaded ' + [math]::Round((Get-Item '%PYINSTALLER%').Length/1MB,1) + ' MB') } " ^
  "catch { Write-Host ('  download failed: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 goto :failed
if not exist "%PYINSTALLER%" goto :failed

echo   installing silently (this takes about a minute) ...
"%PYINSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0 ^
    Include_launcher=1 SimpleInstall=1
REM The installer returns 0 on success and 3010 when a reboot would be needed; a
REM per-user install never actually needs the reboot, so both count as success.
if errorlevel 3010 (
  echo   installed ^(Windows asked for a restart, which is not needed for this^).
) else (
  if errorlevel 1 echo   the installer reported an error, checking anyway ...
)
call :probe
if not errorlevel 1 goto :done

:failed
echo.
echo ============================================================================
echo   Python could not be installed automatically.
echo.
echo   One manual route, two clicks, nothing to configure:
echo     1. open  %PYURL%
echo     2. run it and TICK "Add python.exe to PATH" on the first screen
echo   Then run this installer again - it will find Python and continue.
echo.
echo   (If Windows asks whether to get Python from the Store, answer No: that
echo    version is a stub and Arc Desk cannot build its environment with it.)
echo ============================================================================
endlocal
exit /b 1

:declined
echo.
echo   Nothing was installed. Arc Desk needs Python for this route.
echo   If you already have the packaged app ^(ArcDesk.exe^), you do not need any of
echo   this: just double-click ArcDesk.exe.
endlocal
exit /b 1

REM ---------------------------------------------------------------- success
:done
echo   using: %PY% 
endlocal & set "PY=%PY%" & exit /b 0

REM ============================================================================
REM  :probe - is there a REAL python? sets PY, returns 0 if yes.
REM  Skips the Microsoft Store stub and anything that cannot run `-c ""`.
REM ============================================================================
:probe
set "PY="
call :try "py -3"
if defined PY exit /b 0
call :find_exe "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY exit /b 0
call :find_exe "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if defined PY exit /b 0
call :find_exe "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined PY exit /b 0
call :find_exe "%ProgramFiles%\Python312\python.exe"
if defined PY exit /b 0
call :find_exe "%ProgramFiles%\Python311\python.exe"
if defined PY exit /b 0
call :try "python"
if defined PY exit /b 0
exit /b 1

:find_exe
if not exist "%~1" exit /b 1
call :try "%~1"
exit /b 0

:try
REM A candidate is only accepted if it runs. The Store stub prints a message and
REM exits non-zero, so it fails this on purpose.
set "CAND=%~1"
echo %CAND% | find /i "WindowsApps" >nul && exit /b 1
%CAND% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
set "PY=%CAND%"
exit /b 0
