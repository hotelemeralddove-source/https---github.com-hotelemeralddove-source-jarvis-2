@echo off
REM Arc Desk - clean removal. Stops *our* processes, removes the startup entry and
REM the settings folder. Nothing else on this machine is touched.
REM
REM Why the precise process matching: the first version of this file ran
REM   taskkill /IM pythonw.exe /F
REM which kills EVERY Python GUI app the user is running - their Jupyter, their
REM scripts, someone else's tool. That is collateral damage, and this project's
REM first rule is "your files and your machine are never damaged". So we match on
REM our own executable names and on our own port/script instead.
setlocal
cd /d "%~dp0"

echo [Arc Desk] stopping Arc Desk (only its own processes) ...
taskkill /IM ArcDesk.exe /F >nul 2>nul
taskkill /IM ArcDeskVoice.exe /F >nul 2>nul

REM A source checkout runs as "python ...\arc_desk*" - match the command line, not the
REM interpreter. wmic is present on Windows 10/11; if it is absent we simply skip.
where wmic >nul 2>nul && (
  for /f "skip=1 tokens=1" %%P in ('wmic process where "name='python.exe' and CommandLine like '%%arc_desk%%'" get ProcessId 2^>nul') do (
    if not "%%P"=="" taskkill /PID %%P /F >nul 2>nul
  )
  for /f "skip=1 tokens=1" %%P in ('wmic process where "name='pythonw.exe' and CommandLine like '%%arc_desk%%'" get ProcessId 2^>nul') do (
    if not "%%P"=="" taskkill /PID %%P /F >nul 2>nul
  )
  for /f "skip=1 tokens=1" %%P in ('wmic process where "name='python.exe' and CommandLine like '%%run.py%%'" get ProcessId 2^>nul') do (
    if not "%%P"=="" taskkill /PID %%P /F >nul 2>nul
  )
)

echo [Arc Desk] removing the "Start with Windows" entry ...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v ArcDesk /f >nul 2>nul

echo [Arc Desk] removing settings, notes, caches and the voice model ...
if exist "%APPDATA%\ArcDesk" rmdir /S /Q "%APPDATA%\ArcDesk"

echo.
echo [Arc Desk] done. No Arc Desk process is running and no autostart entry remains.
echo            Your own documents were never touched - Arc Desk only read them.
echo            To remove the program itself, delete this folder (or run the installer's
echo            uninstaller if you installed it that way).
echo.
pause
exit /b 0
