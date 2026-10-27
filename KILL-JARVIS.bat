@echo off
REM ===========================================================================
REM  KILL-JARVIS - close EVERY copy of JARVIS on this PC, in one click.
REM
REM  Use it when:
REM    * Task Manager shows several pythonw.exe
REM    * JARVIS says "port ... is held but nothing answered"
REM    * a double-click shows a window from an OLD folder, or nothing at all
REM
REM  It closes, by pid only (never by name, so no other python program is
REM  touched):
REM    * every JARVIS / ArcDesk run.py (any folder, healthy or stuck)
REM    * the "hey jarvis" listener (arc_daemon.py) - it arms itself again
REM      the next time JARVIS starts
REM
REM  Your settings, voice clips and documents are never touched: they live in
REM  %APPDATA%\ArcDesk, not in any JARVIS folder.
REM
REM  After it runs: double-click JARVIS.bat in your ONE JARVIS folder.
REM ===========================================================================
setlocal
title JARVIS - close every copy
cd /d "%~dp0"
echo.
echo   Closing every copy of JARVIS on this PC ...
echo.
powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe' } | Where-Object { $_.CommandLine -ne $null -and ($_.CommandLine -like '*run.py*' -or $_.CommandLine -like '*arc_daemon.py*') -and ($_.CommandLine -like '*JARVIS*' -or $_.CommandLine -like '*ArcDesk*') } | ForEach-Object { Write-Host ('   closing pid ' + $_.ProcessId + ' : ' + ($_.CommandLine -replace ' +',' ')); Stop-Process -Id $_.ProcessId -Force }"
echo.
if exist "%APPDATA%\ArcDesk\lockport.txt" del "%APPDATA%\ArcDesk\lockport.txt"
echo   done. Every JARVIS copy is closed and the window lock is free.
echo.
echo   Now double-click JARVIS.bat in your ONE JARVIS folder
echo   (C:\Users\%USERNAME%\JARVIS if ONE-PLACE.bat moved it there).
echo   The old folders in Downloads are the leftovers - ONE-PLACE.bat in the
echo   real folder tells you which one is the real one; delete the rest.
echo.
echo   This window closes itself in 12 seconds.
timeout /t 12
exit /b 0
