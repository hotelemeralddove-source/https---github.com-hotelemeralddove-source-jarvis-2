@echo off
title Arc Desk - open it, or tell me exactly why it will not
color 0B
setlocal EnableExtensions

echo ============================================================
echo   ARC DESK  -  one double-click
echo ============================================================
echo.
echo This does three things and then SHOWS you the result:
echo   1. makes the app visible when you click it
echo   2. starts it and waits 12 seconds
echo   3. writes what happened into one file you can send me
echo.
echo Nothing is downloaded, nothing is built, your vault is kept.
echo.
pause

set "REPORT=%USERPROFILE%\Desktop\ArcDeskFix-Report.txt"
> "%REPORT%" echo Arc Desk - what happened
>>"%REPORT%" echo date: %DATE% %TIME%
>>"%REPORT%" echo computer: %COMPUTERNAME%   user: %USERNAME%

REM ================================================== 1. find the app
set "EXE="
set "FOLDER="
if exist "%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe" set "EXE=%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe"
if not defined EXE if exist "%LOCALAPPDATA%\Programs\Arc Desk\ArcDesk.exe" set "EXE=%LOCALAPPDATA%\Programs\Arc Desk\ArcDesk.exe"
if not defined EXE if exist "%~dp0ArcDesk.exe" set "EXE=%~dp0ArcDesk.exe"
if not defined EXE if exist "%~dp0dist\ArcDesk\ArcDesk.exe" set "EXE=%~dp0dist\ArcDesk\ArcDesk.exe"
if not defined EXE goto :noexe
for %%A in ("%EXE%") do set "FOLDER=%%~dpA"
set "ARCEXE=%EXE%"
set "ARCFOLDER=%FOLDER%"

echo.
echo [1/5] app found: %EXE%
>>"%REPORT%" echo.
>>"%REPORT%" echo == 1. the app
>>"%REPORT%" echo path: %EXE%
for %%A in ("%EXE%") do >>"%REPORT%" echo size: %%~zA bytes
if exist "%FOLDER%_internal" (
  >>"%REPORT%" echo _internal folder: yes - this is a complete build
) else (
  >>"%REPORT%" echo _internal folder: NO - this copy CANNOT start, it is a broken build
  echo        PROBLEM: the _internal folder is missing next to the exe.
  echo        That copy can never start. I write it in the report.
)
if exist "%FOLDER%ArcDeskVoice.exe" (
  >>"%REPORT%" echo voice exe: yes
) else (
  >>"%REPORT%" echo voice exe: no
)

REM ================================================== 2. unblock it
echo [2/5] asking Windows to trust the files ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 2. unblocking
powershell -NoProfile -Command "Get-ChildItem -LiteralPath $env:ARCFOLDER -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue; 'unblocked'" >>"%REPORT%" 2>&1

REM ================================================== 3. turn the hidden start off
echo [3/5] turning "start hidden" OFF ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 3. settings
powershell -NoProfile -Command "$p = Join-Path $env:APPDATA 'ArcDesk\settings.json'; if (Test-Path $p) { Copy-Item $p ($p + '.backup.json') -Force; $j = Get-Content $p -Raw | ConvertFrom-Json; if (-not $j.PSObject.Properties['shadow']) { $j | Add-Member -NotePropertyName shadow -NotePropertyValue (New-Object psobject) }; $j.shadow | Add-Member -NotePropertyName enabled -NotePropertyValue $false -Force; $j.shadow | Add-Member -NotePropertyName user_choice -NotePropertyValue $false -Force; $j | ConvertTo-Json -Depth 12 | Set-Content $p -Encoding UTF8; 'hidden start: turned OFF in settings.json' } else { 'no settings.json yet - a first run writes a clean one, already OFF' }" >>"%REPORT%" 2>&1

REM ================================================== 4. shortcut
echo [4/5] putting the shortcut back ...
set "ARCEXE=%EXE%"
powershell -NoProfile -Command "$w = New-Object -ComObject WScript.Shell; $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Arc Desk.lnk'; $s = $w.CreateShortcut($lnk); $s.TargetPath = $env:ARCEXE; $s.Arguments = '--show'; $s.WorkingDirectory = Split-Path $env:ARCEXE; $s.IconLocation = $env:ARCEXE + ',0'; $s.Description = 'Arc Desk'; $s.Save(); 'shortcut written: ' + $lnk" >>"%REPORT%" 2>&1

REM ================================================== 5. start it and watch
echo [5/5] starting it now, and watching for 12 seconds ...
taskkill /f /im ArcDesk.exe >nul 2>&1
start "" "%EXE%" --show
timeout /t 12 /nobreak >nul
>>"%REPORT%" echo.
>>"%REPORT%" echo == 4. did it start
tasklist /fi "imagename eq ArcDesk.exe" 2>nul | find /i "ArcDesk.exe" >nul
if errorlevel 1 (
  >>"%REPORT%" echo ArcDesk.exe is NOT running 12 seconds after starting it
  echo.
  echo        RESULT: it is NOT running. So this is not the hidden-window
  echo        problem - the exe itself will not start on this PC.
) else (
  >>"%REPORT%" echo ArcDesk.exe IS running 12 seconds after starting it
  echo.
  echo        RESULT: it IS running. Look at your screen - the window should
  echo        be there now, and "Arc Desk" on the Desktop opens it from now on.
)

REM A process is not a window. "Running" and "visible" are two different questions, and
REM only this one decides whether the app is usable. MainWindowHandle is 0 when the
REM process has nothing on screen at all.
>>"%REPORT%" echo.
>>"%REPORT%" echo == 4b. is there a WINDOW, not just a process
powershell -NoProfile -Command "Get-Process -Name ArcDesk -ErrorAction SilentlyContinue | ForEach-Object { 'pid ' + $_.Id + '  window handle ' + $_.MainWindowHandle + '  title: ' + $_.MainWindowTitle }" >>"%REPORT%" 2>&1
for /f "delims=" %%L in ('powershell -NoProfile -Command "$p = Get-Process -Name ArcDesk -ErrorAction SilentlyContinue; if (-not $p) { 'NO-PROCESS' } elseif (($p | Where-Object { $_.MainWindowHandle -ne 0 }).Count -gt 0) { 'WINDOW-YES' } else { 'WINDOW-NO' }"') do set "WINDOWSTATE=%%L"
echo        window: %WINDOWSTATE%
>>"%REPORT%" echo window state: %WINDOWSTATE%
if "%WINDOWSTATE%"=="WINDOW-NO" (
  >>"%REPORT%" echo The process is alive but owns NO window. That is the OLD build: it never
  >>"%REPORT%" echo shows its window when the settings file says hidden, and its
  >>"%REPORT%" echo Ctrl+Alt+J is registered by nothing. A NEW build is needed, not a fix
  >>"%REPORT%" echo of these files.
  echo.
  echo        The app is running but owns NO window. So this copy will never show one -
  echo        it is the old build. Send me the report; the new build fixes it.
)

set "ARCLOG=%APPDATA%\ArcDesk\logs\arcdesk.log"
if exist "%ARCLOG%" (
  >>"%REPORT%" echo.
  >>"%REPORT%" echo the app's own last lines:
  powershell -NoProfile -Command "Get-Content -LiteralPath '%ARCLOG%' -Tail 30 | ForEach-Object { '  ' + $_ }" >>"%REPORT%" 2>&1
) else (
  >>"%REPORT%" echo.
  >>"%REPORT%" echo the app wrote NO log at all - it never reached its own start-up code
)

REM what Windows itself has to say about the files, and whether the C++ runtime is there
>>"%REPORT%" echo.
>>"%REPORT%" echo == 5. this PC
ver >>"%REPORT%" 2>&1
if exist "%WINDIR%\System32\msvcp140.dll" (
  >>"%REPORT%" echo msvcp140.dll: present - the C++ runtime is installed
) else (
  >>"%REPORT%" echo msvcp140.dll: MISSING - this is why a packaged app can die silently.
  >>"%REPORT%" echo fix: install "Microsoft Visual C++ 2015-2022 Redistributable x64"
  >>"%REPORT%" echo from https://aka.ms/vs/17/release/vc_redist.x64.exe then run this again
)
if exist "%FOLDER%_internal\msvcp140.dll" >>"%REPORT%" echo the build carries its own msvcp140.dll
if exist "%FOLDER%_internal\vcruntime140.dll" >>"%REPORT%" echo the build carries its own vcruntime140.dll
powershell -NoProfile -Command "Get-MpThreatDetection -ErrorAction SilentlyContinue | Select-Object -First 3 | ForEach-Object { 'defender: ' + $_.Resources }" >>"%REPORT%" 2>&1

echo.
echo ============================================================
echo   Send me ONE file, and I will name the fault in one line:
echo        %REPORT%
echo ============================================================
echo.
pause
endlocal
exit /b 0

:noexe
echo.
echo   I cannot find ArcDesk.exe anywhere on this PC.
echo.
echo   So this is not a settings problem and not a hidden window:
echo   there is no app to open yet. In that case, do only this:
echo.
echo     1. open the newest GREEN run on GitHub
echo     2. Artifacts  ^>  ArcDesk  ^>  download both files
echo     3. right-click ArcDesk-portable.zip  ^>  Extract All
echo     4. double-click ArcDesk.exe inside the folder it made
echo.
>>"%REPORT%" echo RESULT: no ArcDesk.exe found on this PC at all
pause
endlocal
exit /b 1
