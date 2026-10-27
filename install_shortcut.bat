@echo off
REM ============================================================================
REM  Arc Desk - create the Start Menu + Desktop shortcuts.
REM
REM  Two rules, both learned the hard way:
REM
REM  1. A shortcut must point at a real executable with an icon of its own. A
REM     shortcut to a .py / .pyw gets the PYTHON icon, so it looks like a script
REM     and (because pythonw.exe is windowless) it fails with no message at all.
REM  2. If there is no packaged ArcDesk.exe, the shortcut points at
REM     ArcDeskStart.bat instead - which keeps a console open, so the failure is
REM     readable instead of silent.
REM ============================================================================
setlocal
cd /d "%~dp0"
set "EXE="
set "TARGET="
set "ARGS="
set "ICON="

if exist "%~dp0build\dist\ArcDesk\ArcDesk.exe" set "EXE=%~dp0build\dist\ArcDesk\ArcDesk.exe"
if not defined EXE if exist "%~dp0dist\ArcDesk\ArcDesk.exe" set "EXE=%~dp0dist\ArcDesk\ArcDesk.exe"
if not defined EXE if exist "%~dp0ArcDesk.exe" set "EXE=%~dp0ArcDesk.exe"

if defined EXE goto :have_exe
if exist "%~dp0ArcDeskStart.bat" goto :have_starter
echo   Neither ArcDesk.exe nor ArcDeskStart.bat is in this folder:
echo     %~dp0
echo   Build it first:  packaging\build_all.bat
pause
exit /b 1

:have_exe
set "TARGET=%EXE%"
set "ARGS=--show"
if exist "%~dp0assets\arc_icon.ico" set "ICON=%~dp0assets\arc_icon.ico"
echo [Arc Desk] packaged app found - the shortcut will point at it.
goto :make

:have_starter
set "TARGET=%~dp0ArcDeskStart.bat"
set "ARGS="
if exist "%~dp0assets\arc_icon.ico" set "ICON=%~dp0assets\arc_icon.ico"
echo [Arc Desk] no packaged ArcDesk.exe here, so the shortcut will point at
echo            ArcDeskStart.bat - it keeps a console open, so any error is visible.

:make
echo.
echo   target: %TARGET%
echo.
powershell -NoProfile -Command ^
  "$target='%TARGET%'; $args='%ARGS%'; $icon='%ICON%';" ^
  "$sm=[Environment]::GetFolderPath('Programs');" ^
  "$dt=[Environment]::GetFolderPath('Desktop');" ^
  "$sh=New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @($sm,$dt)) {" ^
  "  $path=Join-Path $dir 'Arc Desk.lnk';" ^
  "  if (Test-Path $path) { Remove-Item $path -Force }" ^
  "  $s=$sh.CreateShortcut($path);" ^
  "  $s.TargetPath=$target;" ^
  "  $s.Arguments=$args;" ^
  "  $s.WorkingDirectory=Split-Path $target;" ^
  "  if ($icon -ne '') { $s.IconLocation=$icon + ',0' }" ^
  "  $s.Description='Arc Desk';" ^
  "  $s.Save();" ^
  "  Write-Host ('  wrote ' + $path)" ^
  "}"
echo.
echo   Shortcuts created. If one still does nothing, double-click ArcDeskStart.bat
echo   - it shows the error instead of nothing.
echo.
set /p ANS="Start Arc Desk silently when Windows starts? (y/N) "
if /i not "%ANS%"=="y" goto :end
powershell -NoProfile -Command ^
  "$startup=[Environment]::GetFolderPath('Startup');" ^
  "$sh=New-Object -ComObject WScript.Shell;" ^
  "$s=$sh.CreateShortcut((Join-Path $startup 'Arc Desk.lnk'));" ^
  "$s.TargetPath='%TARGET%'; $s.Arguments='--shadow'; $s.Save();" ^
  "Write-Host '  startup entry created (silent, wake word only).'"
echo   (Undo it any time in Settings, or delete the shortcut from shell:startup.)
:end
echo.
pause
endlocal
