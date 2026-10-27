@echo off
REM ============================================================================
REM  Arc Desk - DIAGNOSE THIS PC.
REM
REM  HOW TO USE: put this file anywhere you like, then DOUBLE-CLICK it.
REM  A black window opens, does its checks, and leaves a report on your DESKTOP:
REM
REM      ArcDeskDiag.txt
REM
REM  It needs no Python, no internet and no install. It changes nothing unless
REM  you answer Y to unblocking our own downloaded files.
REM
REM  Careful with one thing: do not run it from INSIDE the .zip. Windows would
REM  extract it to a temporary folder and the report would land there. Extract
REM  the zip first, then double-click the file in the extracted folder.
REM ============================================================================
setlocal enabledelayedexpansion
set PYEXE=
set FIXED=0

REM ---- where the report goes ------------------------------------------------
REM The Desktop, because that is where a person actually looks. If there is no
REM Desktop folder, the folder this file sits in. Either way the path is printed
REM at the end AND written into the report itself.
set "REPORT=%USERPROFILE%\Desktop\ArcDeskDiag.txt"
if not exist "%USERPROFILE%\Desktop" set "REPORT=%~dp0ArcDeskDiag.txt"
if exist "%~dp0" if not exist "%USERPROFILE%\Desktop" set "REPORT=%~dp0ArcDeskDiag.txt"

REM The very first thing: prove the report can be written at all. If it cannot,
REM say so in the window instead of running checks nobody will ever read.
> "%REPORT%" echo ArcDesk diagnostic
if not exist "%REPORT%" (
  set "REPORT=%TEMP%\ArcDeskDiag.txt"
  > "!REPORT!" echo ArcDesk diagnostic
)

echo ====================================================================
echo  ARC DESK - DIAGNOSING THIS PC
echo ====================================================================
echo  Report: %REPORT%
echo  This takes about 10 seconds. Please leave the window open.
echo.
echo  If you double-clicked this from INSIDE the .zip, close it and extract the
echo  zip first - otherwise the report lands in a temporary folder.
echo ====================================================================
echo.

>>"%REPORT%" echo generated %DATE% %TIME%
>>"%REPORT%" echo script folder %~dp0
>>"%REPORT%" echo.
>>"%REPORT%" echo == 0. VERSION OF THIS DIAGNOSTIC
>>"%REPORT%" echo fix17 - checks the Store Python alias, the 0xc0000142 runtime,
>>"%REPORT%" echo and whether a downloaded file is blocked.

echo [1/7] this PC ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 1. this PC
powershell -NoProfile -Command "$o=Get-CimInstance Win32_OperatingSystem; '  windows : '+$o.Caption+' '+$o.Version+' '+$o.OSArchitecture" 2>nul >>"%REPORT%"
powershell -NoProfile -Command "'  shell   : PowerShell ' + $PSVersionTable.PSVersion.ToString()" 2>nul >>"%REPORT%"
powershell -NoProfile -Command "'  user    : ' + $env:USERNAME + '   temp: ' + $env:TEMP" 2>nul >>"%REPORT%"

echo [2/7] what is on this disk ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 2. files in the folder this was run from
for %%F in (ArcDeskSetup.exe ArcDesk-portable.zip ArcDesk.exe ArcDeskDiag.bat) do (
  if exist "%~dp0%%F" (
    >>"%REPORT%" echo   %%F  %%~zF bytes
  ) else (
    >>"%REPORT%" echo   %%F  not here
  )
)
>>"%REPORT%" echo   expected sizes: portable zip about 92 MB, setup exe about 53 MB.
>>"%REPORT%" echo   A setup exe far under 40 MB is a half download - delete it and
>>"%REPORT%" echo   download again. A zip that will not open is the same problem.

echo [3/7] is the download blocked by Windows? ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 3. blocked files - Mark of the Web
set BLOCKED=
for %%F in (ArcDeskSetup.exe ArcDesk-portable.zip) do (
  if exist "%~dp0%%F" (
    set MARK=
    for /f "delims=" %%S in ('powershell -NoProfile -Command "try{$s=Get-Item -LiteralPath '%~dp0%%F' -Stream Zone.Identifier -ErrorAction Stop; 'yes'}catch{'no'}" 2^>nul') do set MARK=%%S
    if "!MARK!"=="yes" (
      set BLOCKED=!BLOCKED! %%F
      >>"%REPORT%" echo   %%F is BLOCKED - Windows tagged it as came from the internet
    ) else (
      >>"%REPORT%" echo   %%F is not blocked
    )
  )
)
if "!BLOCKED!"=="" goto :unblock_done
echo.
echo   Windows is blocking:!BLOCKED!
echo   Unblocking only removes the came-from-the-internet tag. It is safe.
choice /c YN /n /m "   Unblock these files now? [Y/N] "
if errorlevel 2 (
  >>"%REPORT%" echo   left blocked - the .exe will keep refusing to start
  goto :unblock_done
)
for %%F in (ArcDeskSetup.exe ArcDesk-portable.zip) do (
  if exist "%~dp0%%F" (
    powershell -NoProfile -Command "Unblock-File -LiteralPath '%~dp0%%F'" >nul 2>&1
    >>"%REPORT%" echo   unblocked %%F
    set FIXED=1
  )
)
echo   done.
:unblock_done

echo [4/7] python - is it the Microsoft Store alias? ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 4. python
where python 2>nul >>"%REPORT%"
where python3 2>nul >>"%REPORT%"
for /f "delims=" %%P in ('where python 2^>nul') do (
  echo %%P | find /i "WindowsApps" >nul
  if not errorlevel 1 (
    >>"%REPORT%" echo   WARNING: %%P IS the Microsoft Store ALIAS
    >>"%REPORT%" echo   That is the AppInstallerPythonRedirector.exe dialog, and the
    >>"%REPORT%" echo   reason an exe built on this PC dies with 0xc0000142.
  )
)
for /f "delims=" %%P in ('where py 2^>nul') do (
  >>"%REPORT%" echo   py launcher: %%P
  if not defined PYEXE set PYEXE=py -3
)
if not defined PYEXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYEXE set PYEXE=%%P
if not defined PYEXE goto :no_python
>>"%REPORT%" echo   using: !PYEXE!
!PYEXE! -c "import sys,struct;print('  real python :',sys.executable);print('  version     :',sys.version.split()[0]);print('  bits        :',struct.calcsize('P')*8);print('  base prefix :',sys.base_prefix)" 1>>"%REPORT%" 2>nul
goto :python_done
:no_python
>>"%REPORT%" echo   no python on PATH - fine for RUNNING Arc Desk, the app carries its own
>>"%REPORT%" echo   it only matters for BUILDING it
:python_done

echo [5/7] the MSVC runtime - where 0xc0000142 comes from ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 5. MSVC runtime in System32
for %%D in (vcruntime140.dll vcruntime140_1.dll msvcp140.dll concrt140.dll) do (
  if exist "%SystemRoot%\System32\%%D" (
    >>"%REPORT%" echo   System32\%%D  present
  ) else (
    >>"%REPORT%" echo   System32\%%D  MISSING
  )
)
if exist "%~dp0dist\ArcDesk" (
  >>"%REPORT%" echo   shipped next to the built app:
  dir /b "%~dp0dist\ArcDesk\vc*.dll" 2>nul >>"%REPORT%"
  dir /b "%~dp0dist\ArcDesk\msvc*.dll" 2>nul >>"%REPORT%"
)

echo [6/7] what is installed already ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 6. installed copies
if exist "%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe" (
  >>"%REPORT%" echo   installed at %LOCALAPPDATA%\Programs\ArcDesk
) else (
  >>"%REPORT%" echo   not installed in %LOCALAPPDATA%\Programs\ArcDesk
)
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall" /s /f "Arc Desk" 2>nul | find /i "DisplayName" >>"%REPORT%"
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v ArcDesk 2>nul | find /i "ArcDesk" >>"%REPORT%"
tasklist /fi "imagename eq ArcDesk.exe" 2>nul | find /i "ArcDesk" >>"%REPORT%"

echo [7/7] app execution aliases ...
>>"%REPORT%" echo.
>>"%REPORT%" echo == 7. App execution alias state
if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" (
  for %%A in ("%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe") do (
    >>"%REPORT%" echo   python.exe alias present, %%~zA bytes
    if %%~zA LSS 2000 (
      >>"%REPORT%" echo   a stub this small means the Store Python itself is gone
    )
  )
) else (
  >>"%REPORT%" echo   no python.exe alias
)

>>"%REPORT%" echo.
>>"%REPORT%" echo == 6. WHAT ARC DESK ITSELF SAID  - the log is the only honest witness
REM The app writes a line at boot saying whether it showed a window, and why. Without
REM this section a report could only say "it did not work", which is not a diagnosis.
set "ARCLOG=%APPDATA%\ArcDesk\logs\arcdesk.log"
if exist "%ARCLOG%" (
  >>"%REPORT%" echo   log: %ARCLOG%   - last 60 lines
  >>"%REPORT%" echo   ------------------------------------------------------------
  powershell -NoProfile -Command "Get-Content -LiteralPath '%ARCLOG%' -Tail 60 | ForEach-Object { '  ' + $_ }" >>"%REPORT%" 2>&1
  >>"%REPORT%" echo   ------------------------------------------------------------
) else (
  >>"%REPORT%" echo   no log at %ARCLOG%
  >>"%REPORT%" echo   That means the exe has never reached its own start-up code.
  >>"%REPORT%" echo   If you double-clicked ArcDesk.exe and no window appeared, this is
  >>"%REPORT%" echo   the single most useful line in this report - send it as it is.
)
set "ARCSET=%APPDATA%\ArcDesk\settings.json"
if exist "%ARCSET%" (
  >>"%REPORT%" echo.
  >>"%REPORT%" echo   settings: %ARCSET%
  powershell -NoProfile -Command "try { $j = Get-Content -LiteralPath '%ARCSET%' -Raw | ConvertFrom-Json; '  first_run      : ' + $j.first_run; '  shadow.enabled : ' + $j.shadow.enabled; '  shadow.user_choice : ' + $j.shadow.user_choice; '  wake.enabled   : ' + $j.wake.enabled } catch { '  (could not read settings.json)' }" >>"%REPORT%" 2>&1
) else (
  >>"%REPORT%" echo   no settings file - the app has never run to the point of saving one.
)

REM Did the installed exe keep Arc Desk's icon, or PyInstaller's yellow python?
set "ARCEXE=%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe"
if not exist "%ARCEXE%" set "ARCEXE=%~dp0ArcDesk.exe"
if exist "%ARCEXE%" (
  >>"%REPORT%" echo.
  >>"%REPORT%" echo   exe: %ARCEXE%
  for %%A in ("%ARCEXE%") do >>"%REPORT%" echo   size: %%~zA bytes   - a real build is 10-25 MB, a stub is far less
  if exist "%~dp0..\dist\ArcDesk\ArcDeskVoice.exe" >>"%REPORT%" echo   voice exe: present
)

>>"%REPORT%" echo.
>>"%REPORT%" echo == WHAT TO DO WITH THIS REPORT
>>"%REPORT%" echo 1. If section 3 said BLOCKED and you answered N: run this again, answer Y.
>>"%REPORT%" echo 2. If section 4 shows WindowsApps: turn the alias off in
>>"%REPORT%" echo    Settings ^> Apps ^> Advanced app settings ^> App execution aliases
>>"%REPORT%" echo    python.exe and python3.exe OFF, then install Python from python.org.
>>"%REPORT%" echo 3. To use Arc Desk TODAY, no installer and no Python needed:
>>"%REPORT%" echo    right-click ArcDesk-portable.zip ^> Extract All ^> open the folder
>>"%REPORT%" echo    ^> double-click ArcDesk.exe
>>"%REPORT%" echo 4. Send this file back. It holds no keys and no personal files.

if exist "%~dp0" copy /y "%REPORT%" "%~dp0ArcDeskDiag.txt" >nul 2>&1

echo.
echo ====================================================================
echo  DONE.
echo.
echo  Report:  %REPORT%
if exist "%~dp0ArcDeskDiag.txt" echo  Copy:    %~dp0ArcDeskDiag.txt
echo.
if "!FIXED!"=="1" echo  Some files were unblocked - try ArcDeskSetup.exe again.
echo  Send me that report and I will name the fault in one line.
echo ====================================================================
echo.
pause
endlocal
