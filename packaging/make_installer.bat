@echo off
REM Arc Desk - wrap dist\ArcDesk into a single Setup.exe with Inno Setup (free).
REM Needs Inno Setup 6:  winget install JRSoftware.InnoSetup
setlocal
cd /d "%~dp0\.."

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Inno Setup 6 not found. Install it free:
  echo     winget install JRSoftware.InnoSetup
  echo Then run this again. Nothing was changed.
  exit /b 1
)

if not exist dist\ArcDesk\ArcDesk.exe (
  echo dist\ArcDesk\ArcDesk.exe is missing - run packaging\build.bat first.
  exit /b 1
)

%ISCC% /Qp packaging\arcdesk.iss || exit /b 1
echo.
echo Installer: dist\ArcDeskSetup.exe
echo It installs per-user (no admin), adds Start Menu + optional desktop shortcut,
echo registers uninstall, and touches nothing in Windows itself.
