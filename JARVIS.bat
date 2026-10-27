@echo off
REM ===========================================================================
REM  JARVIS - one double-click. Sets itself up the first time, then starts.
REM
REM  Works on a laptop that has never had Python:
REM    1. finds the project folder (it lives in one, but does not assume)
REM    2. finds Python, or downloads the official one and installs it per-user
REM    3. builds .venv and installs the dependencies  (first run only, 2-4 min)
REM    4. starts JARVIS, detached, so closing THIS window cannot close the app
REM
REM  This file also works from a FIX PACK folder that was unzipped on its own:
REM  it finds the real app, and offers to copy the pack into it (see :aboutpack).
REM  Before fix43 that case printed
REM    "find_project.bat is not recognized as an internal or external command"
REM  because the pack folder has no tools\ next to it.
REM
REM  It deliberately does NOT start the app through start_arcdesk.vbs: a .vbs
REM  unzipped from an internet download carries the mark of the web, so Windows
REM  asks "do you want to open this file?" and a Yes can end in silence. pythonw
REM  needs no such permission.
REM
REM  Everything it does is written to jarvis-start-log.txt next to this file,
REM  because a window that vanishes takes its error message with it.
REM ===========================================================================
REM  And it puts the icon where a person looks for it: once JARVIS is up, this
REM  file also creates the Desktop + Start Menu shortcut (tools\shortcut.py). A
REM  failed connection must never cost the shortcut, so the call is non-fatal.
setlocal enabledelayedexpansion
echo.
if exist "%~dp0VERSION.txt" type "%~dp0VERSION.txt"
echo.
title JARVIS
cd /d "%~dp0"
set "LOG=%~dp0jarvis-start-log.txt"
>"%LOG%" echo JARVIS start log - %DATE% %TIME%
>>"%LOG%" echo launched from: %~dp0

echo.
echo   J A R V I S
echo   -----------
echo.

set "PROJ="
if exist "%~dp0tools\find_project.bat" call "%~dp0tools\find_project.bat"
if not defined PROJ call :lookhere "%~dp0"
if not defined PROJ call :lookhere "%~dp0.."
if not defined PROJ call :lookhere "%~dp0..\.."
if not defined PROJ call :lookhere "%~dp0..\..\.."
if not defined PROJ call :lookhere "%USERPROFILE%\JARVIS"
if not defined PROJ call :lookhere "%USERPROFILE%\Documents\JARVIS"
if not defined PROJ call :lookhere "%USERPROFILE%\Downloads\JARVIS"
if not defined PROJ call :scanfor "%USERPROFILE%\Documents\GitHub"
if not defined PROJ call :scanfor "%USERPROFILE%\Desktop"
if not defined PROJ call :scanfor "%USERPROFILE%\OneDrive\Desktop"
if not defined PROJ call :scanfor "%USERPROFILE%\Downloads"
if not defined PROJ goto :wrongfolder
REM Show one clean path. find_project answers with things like
REM   C:\...\ArcDesk-full-project\tools\..
REM which works but reads like a mistake; %%~fI turns it into the real folder.
for %%I in ("%PROJ%") do set "PROJ=%%~fI"

REM Two copies of JARVIS, both in Downloads, is the most common way this gets confusing
REM ("JARVIS-ready (1)"). One line now, so it is not discovered a week later.
set "PDIR=%PROJ%"
if /i "%PDIR:Downloads=%"=="%PDIR%" goto :notdownloads
REM A second copy is its own trap: "JARVIS-ready (1)" is what Explorer makes when the zip is
REM opened twice, and then two folders both look like the app. Say it once, here, while the
REM person is looking at a window that names the folder.
set "PDUP=%PROJ:(1)=%"
if /i not "%PDUP%"=="%PROJ%" echo   NOTE: this folder name has "(1)" in it - that is a second copy of an
if /i not "%PDUP%"=="%PROJ%" echo   unzipped download. Keep one: run ONE-PLACE.bat in %PROJ%
echo.
echo.
echo   NOTE: this JARVIS lives in Downloads. Windows and disk cleaners empty that folder,
echo   and unzipping the zip twice makes a second copy. Park one copy for good:
echo     %PROJ%\ONE-PLACE.bat        then open %USERPROFILE%\JARVIS\JARVIS.bat
echo.
:notdownloads

REM A fix pack, unzipped as its own folder, next to nothing. Say so, and offer the
REM only useful thing: copy these files into the app.
set "HERE=%~dp0"
if /i "%HERE%"=="%PROJ%\" goto :same
if /i "%HERE%"=="%PROJ%" goto :same
if exist "%~dp0FIXPACK.txt" goto :aboutpack
goto :same

:same
cd /d "%PROJ%"
echo   project folder : %PROJ%
>>"%LOG%" echo project folder: %PROJ%

set "VPY=%PROJ%\.venv\Scripts\python.exe"
set "VPW=%PROJ%\.venv\Scripts\pythonw.exe"
set "JS=%PROJ%\tools\jarvis_state.py"

REM A venv is real only while it has its birth certificate, pyvenv.cfg. A half
REM deleted one keeps Scripts\python.exe but loses that file, and every call to
REM it prints "No pyvenv.cfg file" and does nothing - which is what a start-up
REM full of one-line errors and no window looks like from the outside. Rebuild.
if not exist "%PROJ%\.venv\pyvenv.cfg" goto :newvenv
if not exist "%VPY%" goto :newvenv
REM File checks are not enough: a .venv copied from another machine (a Drive
REM upload or a zip) keeps its pyvenv.cfg and python.exe, but they point at
REM the Python install of the machine they came from. Prove the venv can
REM really run the heaviest import; if it cannot, rebuild it on this laptop.
"%VPY%" -c "import PySide6" >nul 2>&1
if errorlevel 1 goto :newvenv
goto :ready

:newvenv
if exist "%PROJ%\.venv" (
  echo   the private Python environment is incomplete - rebuilding it.
  >>"%LOG%" echo rebuilding .venv - pyvenv.cfg was missing
)

echo   Python         : looking for it...
call "%~dp0tools\pybootstrap.bat"
if errorlevel 1 goto :fail
>>"%LOG%" echo bootstrap PY=%PY%

REM A JARVIS from THIS folder that is still running (in the tray) holds the
REM venv files open, and the rebuild cannot replace them. Close ours first -
REM the settings are on disk, so nothing is lost.
if exist "%PROJ%\.venv" "%PY%" "%JS%" --stop --quiet
timeout /t 1 >nul
if exist "%PROJ%\.venv" rmdir /s /q "%PROJ%\.venv" 2>nul

echo.
echo   building the private Python environment.
echo   this needs internet and takes 2-4 minutes. nothing global changes.
%PY% -m venv .venv
if errorlevel 1 goto :fail
"%VPY%" -m pip install --quiet --upgrade pip
"%VPY%" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto :fail
>"%PROJ%\.venv\.reqstamp" echo built
echo   ready.

:ready
REM An update can add a library. If requirements.txt changed since this .venv was
REM built, top it up - quietly, a few seconds, and never fatal.
if not exist "%VPY%" goto :fail
set "STAMP="
for %%F in ("requirements.txt") do set "STAMP=%%~zF-%%~tF"
set "OLD="
if exist ".venv\.reqstamp" set /p OLD=<".venv\.reqstamp"
if /i "%STAMP%"=="%OLD%" goto :start
echo   checking the libraries (a few seconds after an update) ...
>>"%LOG%" echo topping up requirements
"%VPY%" -m pip install --quiet -r requirements.txt
if errorlevel 1 echo   (could not update them - starting anyway)
echo %STAMP%>".venv\.reqstamp"

:start
REM A working copy already there? Show it, do not start a second one.
if not exist "%JS%" goto :launch
REM Copies of JARVIS left in OTHER folders (old downloads that are still alive
REM in the tray) hold the same lock port and steal the wake, so THIS launch
REM would get a sentence and no window. Close only those - never ours, never
REM any other python program. Non-fatal by design.
echo   closing JARVIS copies left in other folders (leftover downloads) ...
"%VPY%" "%JS%" --kill-foreign --quiet
echo   checking whether a working JARVIS is already up ...
"%VPY%" "%JS%" --wake --quiet
if not errorlevel 1 goto :brought
echo   a stuck copy of JARVIS is in the way - closing just that one.
"%VPY%" "%JS%" --kill-stale --quiet
timeout /t 1 >nul

:launch
echo.
echo   starting JARVIS ...
REM --show, not --shadow. The report was "JARVIS is running" with no window: an earlier
REM launcher passed --shadow, so a double-click hid the app and the person had nothing to
REM look at. A double-click means somebody is at the screen. Stealth is still the resting
REM state for the copy Windows starts at login, which passes --shadow itself.
REM launch.py --ensure is the brain: it repairs a library that a voice-engine install
REM broke, closes a stuck copy of ours, starts the app with its output captured - so a
REM crash leaves a traceback instead of nothing - and then WAITS FOR PROOF that a window
REM is on screen. The old version started the app and waited 25 seconds in silence, which
REM is what "terminal open aaguthu, app varala" looks like from the outside.
if not exist "%PROJ%\tools\launch.py" goto :launchplain
"%VPY%" "%PROJ%\tools\launch.py" --ensure --wait 25
if not errorlevel 1 goto :running
goto :didnotstart

:launchplain
REM Fallback for an older copy that has no launch.py: the plain detached start.
echo   (this copy has no tools\launch.py - using the plain start)
>>"%LOG%" echo starting plain: "%VPW%" "%PROJ%\run.py" --show
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -FilePath '%VPW%' -ArgumentList '%PROJ%\run.py','--show' -WindowStyle Hidden" >>"%LOG%" 2>&1
REM pythonw can be missing in an unusual venv; python.exe always exists next to it.
if errorlevel 1 powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -FilePath '%VPY%' -ArgumentList '%PROJ%\run.py','--show' -WindowStyle Hidden" >>"%LOG%" 2>&1
if errorlevel 1 start "" "%VPW%" "%PROJ%\run.py" --show
set "WAITED=0"
:wait
set /a WAITED+=1
REM Up to three tries, 25 s each, each one printing what it is doing.
"%VPY%" "%PROJ%\tools\launch.py" --wait 25
if not errorlevel 1 goto :running
if %WAITED% geq 3 goto :didnotstart
echo   trying again ...
goto :wait

:running
>>"%LOG%" echo the app is running and answering on its lock port
echo.
echo   JARVIS is running - the window is open now.
REM The icon, so the NEXT time is one click and no console. Non-fatal by design:
REM a shortcut is a convenience, and JARVIS being up matters more than the icon.
if exist "%PROJ%\tools\shortcut.py" "%VPY%" "%PROJ%\tools\shortcut.py" >>"%LOG%" 2>&1
echo.
echo     Ctrl+Alt+J   open / hide the window
echo     "hey jarvis" speak, once the microphone is set up
echo     Ctrl+Alt+Q   quit
echo.
echo   If you cannot see it, look on the taskbar, or press Ctrl+Alt+J.
echo   This window closes itself in 15 seconds.
timeout /t 15
exit /b 0

:brought
REM The app ANSWERED the wake - jarvis_state --wake now waits for its reply - but an
REM answer is not a window. Prove it: the app writes a WAKE line in its log when it really
REM shows one. No line, no window, so start a fresh copy instead of a happy sentence.
"%VPY%" "%PROJ%\tools\launch.py" --wait 6
if errorlevel 1 goto :broughtnothing
echo.
echo   JARVIS was already running - it answered, and its window is on screen now.
echo   Ctrl+Alt+J again if you cannot see it, Ctrl+Alt+Q quits.
>>"%LOG%" echo already running - woke it, window confirmed
timeout /t 10
exit /b 0

:broughtnothing
echo.
echo   A copy of JARVIS answered but did not show a window - so I am starting a fresh
echo   one instead of leaving you with nothing.
>>"%LOG%" echo wake accepted, no window appeared - starting fresh
REM Record what this laptop said it had before anything gets closed: --status answers
REM "running and answering" (0), "running but stuck" (2) or "not running" (1).
"%VPY%" "%JS%" --status >>"%LOG%" 2>&1
REM --stop, not --kill-stale: the copy IS answering its lock port (so
REM kill-stale would call it healthy and spare it) yet it failed the one job
REM that matters - showing a window. Ask it to quit, wait, then close it by
REM pid if it will not. This is the case that used to leave a "Not
REM Responding" copy holding the lock while every new launch piled up behind
REM it - the "multiple pythonw.exe" report.
"%VPY%" "%JS%" --stop --quiet
timeout /t 1 >nul
goto :launch

:didnotstart
echo.
echo   It started but no window appeared. Here is what I can prove about this laptop:
>>"%LOG%" echo started but no window appeared
REM Clear the field before diagnosing: whatever copy of ours answered but never
REM showed a window is still holding the lock. Ask, wait, close by pid.
"%VPY%" "%JS%" --stop --quiet
timeout /t 1 >nul
REM --diagnose prints the numbered checks, the child's own traceback (logs\spawn.log)
REM and the app's last log lines - all in THIS window, which stays open.
"%VPY%" "%PROJ%\tools\launch.py" --diagnose
>>"%LOG%" echo diagnosis printed
powershell -NoProfile -Command "Get-Content -Path ($env:APPDATA + '\ArcDesk\logs\arcdesk.log') -Tail 12 -ErrorAction SilentlyContinue"
echo.
echo   The same reasons are printed by JARVIS-DIAGNOSE.bat, which keeps its window open.
>>"%LOG%" echo last 12 log lines were shown
pause
exit /b 1

:fail
echo.
echo   setup stopped. the line above says which step; usually that is the internet.
echo   nothing was installed globally. details were written to:
echo     %LOG%
>>"%LOG%" echo FAILED at the step above
pause
exit /b 1

:wrongfolder
echo.
echo   I cannot find the app anywhere I looked, so there is nothing to start.
echo   I looked in: this folder, its parents, %USERPROFILE%\JARVIS,
echo   Documents\JARVIS, Downloads\JARVIS, Documents\GitHub, Desktop, Downloads.
echo.
echo   The app is the folder that has run.py and requirements.txt in it.
echo   If you just unzipped a download: unzip ArcDesk-full-project.zip somewhere such as
echo     C:\Users\%USERNAME%\JARVIS
echo   and double-click JARVIS.bat inside THAT folder.
>>"%LOG%" echo wrong folder, nothing found near: %~dp0
pause
exit /b 1

:aboutpack
echo.
echo   This folder is a FIX PACK - a few changed files, not the app itself.
echo.
echo   The app is here:
echo     %PROJ%
echo.
echo   I can copy these files into it now, which is what they are for.
echo   Your settings and the .venv are never touched.
echo.
choice /C YN /N /M "Apply them and start JARVIS  [Y = yes, N = no] "
if errorlevel 2 goto :declined
echo.
echo   copying into %PROJ% ...
REM "%~dp0" ENDS WITH A BACKSLASH, so quoting it made "C:\...\pack\" escape its own
REM closing quote and robocopy read the whole line as ONE argument:
REM   ERROR : Invalid Parameter #1 : "C:\...\arcdesk-fix45-..."      (screenshot 17.png)
REM So: strip it first, and prefer the app's own updater, which is the path that has tests.
set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "PYU=%PROJ%\.venv\Scripts\python.exe"
set "UPD=%PROJ%\tools\update_from_zip.py"
if not exist "%PYU%" goto :packcopy
if not exist "%UPD%" goto :packcopy
"%PYU%" "%UPD%" --folder "%SRC%"
if errorlevel 1 goto :packcopy
goto :packdone

:packcopy
robocopy "%SRC%" "%PROJ%" /E /XD ".venv" "__pycache__" ".git" ".failures" ^
         /XF "settings.json" "FIXPACK.txt" "README-FIX*.txt" /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfailed

:packdone
>>"%LOG%" echo applied this fix pack to %PROJ%
echo   applied.
echo.
echo   starting from %PROJ% ...
start "" "%PROJ%\JARVIS.bat"
exit /b 0

:declined
echo.
echo   Nothing was changed.
echo   To do it by hand: open this folder, select everything, copy, paste into
echo     %PROJ%
echo   and choose "Replace the files in the destination".
pause
exit /b 0

:copyfailed
echo.
echo   The copy did not finish. Nothing important was changed.
echo   Close JARVIS first (Ctrl+Alt+Q), then run this file again.
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
