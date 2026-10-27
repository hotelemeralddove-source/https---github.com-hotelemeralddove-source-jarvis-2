@echo off
REM Arc Desk - validate this checkout in one go. Nothing here changes anything.
setlocal enabledelayedexpansion
title JARVIS - check
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)
set "FAILS=0"

echo.
echo   J A R V I S   -   check
echo   =====================
echo   Nothing here changes anything. It only measures.
echo.

echo [1/9] does saying "bye jarvis" really close it?  (real app, real protocol) ...
%PY% tools\voice_roundtrip.py --case quit
if errorlevel 1 set /a FAILS+=1

echo.
echo [2/9] does it actually boot?  (run.py --shadow, 6 s, isolated) ...
REM NOT --no-instance: the whole point of this section is the polite close ("bye jarvis"),
REM and a copy with no instance lock cannot be asked to close - only killed. On Windows a
REM kill is exit code 1 with no message, which looked like an app bug for weeks.
%PY% tools\smoke_firstrun.py --shadow --seconds 12
if errorlevel 1 set /a FAILS+=1

echo.
echo [3/9] the test suite ...
REM --jobs 1 keeps it predictable on a small laptop, and the per-test tail is printed
%PY% tests\run_all.py
if errorlevel 1 set /a FAILS+=1

echo.
echo [4/9] install health ...
%PY% run.py --doctor
if errorlevel 1 set /a FAILS+=1

echo.
echo [5/9] is Windows still untouched? ...
%PY% tools\desktop_check.py --scan
if errorlevel 1 set /a FAILS+=1

echo.
echo [6/9] open-source stack on this PC ...
%PY% tools\github_scan.py --plan
if errorlevel 1 set /a FAILS+=1

echo.
echo [7/9] what can it actually do? ...
%PY% tools\capability.py --all
if errorlevel 1 set /a FAILS+=1

echo.
echo [8/9] can this be packaged and uninstalled safely? ...
%PY% tools\packaging.py
if errorlevel 1 set /a FAILS+=1

echo.
echo [9/9] the tools reference matches the code ...
%PY% tools\gen_tools_doc.py --check
if errorlevel 1 set /a FAILS+=1

echo.
echo [report] one file that says what failed and why ...
%PY% tools\failure_report.py --write

echo.
echo   =====================
if "%FAILS%"=="0" (
    echo   EVERYTHING PASSED. The app is healthy on this PC.
) else (
    echo   %FAILS% of 9 sections reported a problem.
    echo.
    echo   What to do next, in order of likelihood:
    echo     1. the failing lines are printed above, and copied into check-report.txt
    echo     2. send that one file - it holds versions and the failing lines only
    echo     3. per-test details are also in the folder  .failures\
)
echo   =====================
echo.
echo   Reminder: this window is only a doctor. The app itself is JARVIS.bat.
pause
exit /b 0
