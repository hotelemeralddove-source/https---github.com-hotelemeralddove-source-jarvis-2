@echo off
setlocal EnableExtensions
title Arc Desk - remove the old copy before installing the new one
color 0B

echo ============================================================
echo   ARC DESK  -  clean out the old copy first
echo ============================================================
echo.
echo This removes the OLD program files and the OLD shortcut, so a
echo fresh download cannot end up mixed with them and so Windows
echo cannot keep showing a cached icon.
echo.
echo It does NOT touch your vault. Everything you made with Arc Desk
echo stays in:  %APPDATA%\ArcDesk
echo.
echo Close Arc Desk (and its black window, if open) before going on.
echo.
pause

echo [1/6] closing Arc Desk if it is running ...
taskkill /f /im ArcDesk.exe        >nul 2>&1
taskkill /f /im ArcDeskVoice.exe   >nul 2>&1

echo [2/6] removing the desktop shortcut ...
del /f /q "%USERPROFILE%\Desktop\Arc Desk.lnk" >nul 2>&1
if exist "%USERPROFILE%\OneDrive\Desktop\Arc Desk.lnk" del /f /q "%USERPROFILE%\OneDrive\Desktop\Arc Desk.lnk" >nul 2>&1

echo [3/6] removing the Start Menu entry ...
rd /s /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Arc Desk" >nul 2>&1

echo [4/6] removing the old program folder ...
rd /s /q "%LOCALAPPDATA%\Programs\ArcDesk" >nul 2>&1
rd /s /q "%LOCALAPPDATA%\Programs\Arc Desk" >nul 2>&1

echo [5/6] asking Windows to forget the old icon ...
ie4uinit.exe -show >nul 2>&1

echo [6/6] checking what is left ...
if exist "%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe" echo   still there - close it and run this again
if not exist "%LOCALAPPDATA%\Programs\ArcDesk\ArcDesk.exe" echo   old program files: gone

echo.
echo ============================================================
echo   DONE. Now:
echo     1. unzip the new ArcDesk-portable.zip
echo     2. open the folder and double-click ArcDesk.exe
echo     3. the icon should be Arc Desk's sparkle, not a python
echo   Your vault was not touched:  %APPDATA%\ArcDesk
echo ============================================================
echo.
pause
endlocal
