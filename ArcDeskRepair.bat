@echo off
REM ============================================================================
REM  Arc Desk - REPAIR.  Double-click it.
REM
REM  For the case you are in right now: the shortcut is on the desktop, you
REM  double-click it, and nothing happens. No window, no error, nothing.
REM
REM  This file finds every copy of Arc Desk on this PC, tries each one, and
REM  tells you in one line which one works. If one works it rebuilds the
REM  desktop shortcut to point at it. If none work it names the reason.
REM
REM  It writes ArcDeskRepair.txt on your Desktop and prints the path.
REM  It installs nothing and changes nothing except your own Arc Desk shortcut,
REM  and only after you say Y.
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "REPORT=%USERPROFILE%\Desktop\ArcDeskRepair.txt"
if not exist "%USERPROFILE%\Desktop" set "REPORT=%~dp0ArcDeskRepair.txt"
set "FOUND="
set "WORKS="
set "COUNT=0"

> "%REPORT%" echo Arc Desk repair report
if not exist "%REPORT%" set "REPORT=%TEMP%\ArcDeskRepair.txt"

echo ====================================================================
echo  ARC DESK - REPAIR
echo ====================================================================
echo  Report: %REPORT%
echo.

>>"%REPORT%" echo generated %DATE% %TIME%
>>"%REPORT%" echo run from %~dp0
>>"%REPORT%" echo.

REM ---------------------------------------------------------------- 1. find
echo [1/5] looking for Arc Desk on this PC ...
>>"%REPORT%" echo == 1. copies found
call :try_exe "%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe" "installed (per-user)"
call :try_exe "%~dp0dist\ArcDesk\ArcDesk.exe" "dist folder next to this file"
call :try_exe "%~dp0packaging\dist\ArcDesk\ArcDesk.exe" "packaging\dist next to this file"
call :try_exe "%~dp0ArcDesk.exe" "next to this file"
call :try_exe "%~dp0build\dist\ArcDesk\ArcDesk.exe" "build\dist next to this file"
call :try_exe "%LOCALAPPDATA%\ArcDesk\ArcDesk.exe" "old install location"
call :try_exe "%PROGRAMFILES%\Arc Desk\ArcDesk.exe" "Program Files"
if "%COUNT%"=="0" goto :no_exe
echo.
echo   found %COUNT% copy/copies.
goto :test

:no_exe
>>"%REPORT%" echo   no ArcDesk.exe anywhere obvious
echo   No ArcDesk.exe found - so the app was never actually installed, or it
echo   was installed somewhere unusual.
echo.
echo   Next step: run ArcDeskDiag.bat (it is in the same folder as this file
echo   if you downloaded both), or install ArcDeskSetup.exe again.
goto :end

REM ---------------------------------------------------------------- 2. test
:test
echo.
echo [2/5] trying to start each one (about 8 seconds each) ...
echo        If a window opens, that copy works - close it after the check.
>>"%REPORT%" echo.
>>"%REPORT%" echo == 2. start test
for %%E in (%FOUND%) do (
  echo.
  echo   testing: %%E
  tasklist /fi "imagename eq ArcDesk.exe" 2>nul | find /i "ArcDesk.exe" >nul
  if not errorlevel 1 (
    >>"%REPORT%" echo   %%E - already running, skipped
    echo     already running - skipped
  ) else (
    start "" "%%E"
    timeout /t 8 /nobreak >nul
    tasklist /fi "imagename eq ArcDesk.exe" 2>nul | find /i "ArcDesk.exe" >nul
    if errorlevel 1 (
      >>"%REPORT%" echo   %%E - DID NOT START
      echo     DID NOT START
    ) else (
      >>"%REPORT%" echo   %%E - STARTED
      echo     STARTED
      if not defined WORKS set "WORKS=%%E"
    )
  )
)

REM ---------------------------------------------------------------- 3. verdict
echo.
echo [3/5] what I found ...
if not defined WORKS goto :nothing_works
>>"%REPORT%" echo.
>>"%REPORT%" echo == 3. verdict: %WORKS% starts correctly
echo   GOOD NEWS: this copy starts correctly:
echo     %WORKS%
echo.
echo   So the app is fine - the SHORTCUT is pointing at the wrong thing.
echo.

echo [4/5] rebuilding your desktop shortcut ...
>>"%REPORT%" echo == 4. rebuilding the shortcut
choice /c YN /n /m "   Rebuild the Arc Desk shortcut on the Desktop now? [Y/N] "
if errorlevel 2 goto :end
if exist "%USERPROFILE%\Desktop\Arc Desk.lnk" del /q "%USERPROFILE%\Desktop\Arc Desk.lnk"
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Arc Desk.lnk'); $s.TargetPath='!WORKS!'; $s.WorkingDirectory=Split-Path '!WORKS!'; $s.IconLocation='!WORKS!,0'; $s.Arguments='--show'; $s.Description='Arc Desk'; $s.Save(); Write-Host '  shortcut written.'"
>>"%REPORT%" echo   shortcut now points at %WORKS%
echo.
echo   Done. Close this window, then double-click "Arc Desk" on the Desktop.
goto :end

REM ---------------------------------------------------------- 4. why nothing
:nothing_works
>>"%REPORT%" echo.
>>"%REPORT%" echo == 3. verdict: every copy failed to start
echo   BAD NEWS: %COUNT% copy/copies found, and none of them opened a window.
echo.
echo   That means the app dies in its first second. On Windows that failure is
echo   silent by design (the app has no console), so the cause is one of these
echo   three. Check them in this order:
echo.

REM --- a: is python the Store alias?
set "ALIAS="
for /f "delims=" %%P in ('where python 2^>nul') do (
  echo %%P | find /i "WindowsApps" >nul
  if not errorlevel 1 set "ALIAS=%%P"
)
if defined ALIAS (
  >>"%REPORT%" echo   CAUSE FOUND: python is the Microsoft Store alias - !ALIAS!
  echo   [1] YOUR PYTHON IS THE MICROSOFT STORE ALIAS
  echo       !ALIAS!
  echo       Any exe built with that interpreter dies at startup with 0xc0000142,
  echo       which is exactly the dialog you saw. Turn it off:
  echo         Settings ^> Apps ^> Advanced app settings ^> App execution aliases
  echo         python.exe and python3.exe  -^>  OFF
  echo       then install Python from python.org and rebuild.
  echo.
) else (
  >>"%REPORT%" echo   python: not the Store alias, or no python at all
)

REM --- b: the VC++ runtime
if not exist "%SystemRoot%\System32\vcruntime140.dll" (
  >>"%REPORT%" echo   CAUSE FOUND: vcruntime140.dll is missing from System32
  echo   [2] THE VC++ RUNTIME IS MISSING
  echo       C:\Windows\System32\vcruntime140.dll not found.
  echo       Qt needs it. Install the Microsoft Visual C++ Redistributable x64:
  echo         https://aka.ms/vs/17/release/vc_redist.x64.exe
  echo       then try the shortcut again.
  echo.
) else (
  >>"%REPORT%" echo   vcruntime140.dll: present in System32
)

REM --- c: was the folder copied without _internal ?
set "LONELY="
for %%E in (%FOUND%) do (
  if not exist "%%~dpE_internal" set "LONELY=%%E"
)
if defined LONELY (
  >>"%REPORT%" echo   CAUSE FOUND: no _internal folder next to !LONELY!
  echo   [3] THE APP'S FOLDER IS INCOMPLETE
  echo       !LONELY!
  echo       There is no _internal folder beside it. A packaged Arc Desk is the
  echo       exe PLUS that folder - the exe alone cannot start. Copy the whole
  echo       whole folder, or reinstall. Do not copy ArcDesk.exe by itself.
  echo.
) else (
  >>"%REPORT%" echo   _internal folder: present next to every copy
)

>>"%REPORT%" echo.
>>"%REPORT%" echo == 4. what to send me
echo [5/5] send me the report ...
echo   Report: %REPORT%
echo   Send that file. It lists every copy found and which check failed.
echo   If all three checks above say "fine", the answer is in the app's own log:
echo     %APPDATA%\ArcDesk\logs\arcdesk.log
echo   Send that too - it is a text file with no keys in it.
goto :end

:end
if exist "%~dp0" copy /y "%REPORT%" "%~dp0ArcDeskRepair.txt" >nul 2>&1
echo.
echo ====================================================================
echo  Report: %REPORT%
echo ====================================================================
echo.
pause
exit /b 0

REM ---------------------------------------------------------------- helper
:try_exe
if not exist "%~1" goto :eof
if not exist "%~1.exe" if "%~x1"=="" goto :eof
>>"%REPORT%" echo   %~1   [%~2]
if defined FOUND (set "FOUND=!FOUND! "%~1"") else (set "FOUND="%~1"")
set /a COUNT+=1
goto :eof
