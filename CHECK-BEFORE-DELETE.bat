@echo off
REM ===========================================================================
REM  CHECK BEFORE DELETE - double-click this BEFORE you remove an old JARVIS.
REM
REM  It does three things, and it never deletes anything by itself:
REM
REM    1. shows what JARVIS keeps OUTSIDE the folder - your settings, your voice
REM       clip, your memory - so you can see what deleting the folder cannot lose
REM    2. shows what is really inside the old folder: the engine packages hidden
REM       in its .venv, and any file in there that is not part of JARVIS
REM    3. if you type R, RENAMES the old folder to JARVIS-OLD. Nothing is deleted.
REM       You delete it yourself once you are happy, or never.
REM
REM  Two ways to use it:
REM    * drag the old JARVIS folder onto this file, or
REM    * double-click it and it points at a second copy if it finds one
REM
REM  Everything it prints is also written to check-before-delete-log.txt
REM ===========================================================================
setlocal enabledelayedexpansion
title JARVIS - check before delete
cd /d "%~dp0"
set "LOG=%~dp0check-before-delete-log.txt"
>"%LOG%" echo check before delete - %DATE% %TIME%
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
for %%I in ("%HERE%") do set "HERE=%%~fI"
>>"%LOG%" echo clean copy: %HERE%

echo.
echo   J A R V I S   -   check before delete
echo   -----------------------------------
echo   this file never deletes anything. it looks, then renames.
echo.

echo   1. things JARVIS keeps OUTSIDE the folder - these are NOT touched
echo   ------------------------------------------------------------
set "DATA=%APPDATA%\ArcDesk"
>>"%LOG%" echo data folder: %DATA%
echo   in: %DATA%
call :look "%DATA%\settings.json" "your settings, API keys, chosen voice"
call :look "%DATA%\vault" "your notes and memory"
call :look "%DATA%\voice" "your own voice clip"
call :look "%DATA%\voices" "downloaded voice models"
call :look "%DATA%\models" "downloaded AI models"
call :look "%DATA%\logs" "the crash log"
echo.
echo   so: deleting the old folder loses none of the above.
echo.

echo   2. which folder is the OLD one?
echo   ------------------------------
set "OLD="
if not "%~1"=="" for %%I in ("%~1") do set "OLD=%%~fI"
if defined OLD goto :have
set "FOUND="
call :cand "%USERPROFILE%\JARVIS"
call :cand "%USERPROFILE%\Downloads\JARVIS"
call :cand "%USERPROFILE%\Desktop\JARVIS"
call :cand "%USERPROFILE%\OneDrive\Desktop\JARVIS"
call :cand "%USERPROFILE%\ArcDesk"
call :cand "%USERPROFILE%\Downloads\ArcDesk-full-project"
call :cand "%USERPROFILE%\Documents\GitHub\ArcDesk"
call :cand "%USERPROFILE%\Documents\GitHub\JARVIS"
if defined FOUND goto :askpath
echo   no second copy found in the usual places.
:askpath
echo   drag the old JARVIS folder onto this file, or type its path below.
echo.
set "OLD="
set /p "OLD=  old JARVIS folder, or press Enter to stop: "
if not defined OLD goto :nothing
set OLD=%OLD:"=%
for %%I in ("!OLD!") do set "OLD=%%~fI"

:have
echo.
echo   3. what is in  !OLD!
echo   --------------------------
if not exist "!OLD!\run.py" if not exist "!OLD!\arcdesk\__init__.py" goto :notjarvis
if /i "!OLD!"=="!HERE!" goto :itself
if /i "!OLD:~1!"==":\" goto :toobig
set "INHERE=!HERE:%OLD%=!"
if /i not "!INHERE!"=="!HERE!" goto :contains

if exist "!OLD!\.venv" (
  echo   .venv: YES - packages installed inside the old folder. Deleting it
  echo   means these are installed again on the next start:
  dir /b /a-d "!OLD!\.venv\Lib\site-packages" 2>nul | findstr /i "piper onnx torch tts whisper coqui sounddevice numpy" 2>nul
  >>"%LOG%" echo venv present in %OLD%
) else (
  echo   .venv: no - nothing was installed inside the folder.
)
echo.
set /a EXTRA=0
for %%F in ("!OLD!\*") do (
  if not exist "!HERE!\%%~nxF" (
    echo   not part of JARVIS: %%~nxF
    set /a EXTRA+=1
  )
)
if !EXTRA!==0 echo   every item in that folder is a normal JARVIS item.
>>"%LOG%" echo extra items: !EXTRA!
echo.
tasklist /fi "imagename eq pythonw.exe" 2>nul | find /i "pythonw.exe" >nul
if not errorlevel 1 echo   NOTE: JARVIS looks like it is running. Quit it from the tray first.

echo   4. what happens next
echo   --------------------
echo   R = rename the old folder to JARVIS-OLD. nothing is deleted.
echo   X = stop. change nothing.
echo.
set "ANS="
set /p "ANS=  your answer, R or X: "
if /i not "!ANS!"=="R" goto :nothing

for %%I in ("!OLD!\..") do set "PARENT=%%~fI"
if "!PARENT:~-1!"=="\" if not "!PARENT:~1!"==":\" set "PARENT=!PARENT:~0,-1!"
call :rename
if errorlevel 1 goto :failed
echo.
echo   done. nothing was deleted.
echo   old copy:    !DEST!
echo   clean copy:  !HERE!   - untouched
echo.
echo   from now on open only  !HERE!\JARVIS.bat
echo   happy after a week? delete  !DEST!  yourself.
echo.
echo   if you had "start JARVIS when I sign in" ticked in Settings, tick
echo   it again once - the old tick still points at the renamed folder.
>>"%LOG%" echo renamed %OLD% -^> %DEST%
goto :eof

:itself
echo   that is the clean copy this file lives in. refusing, so you cannot
echo   rename the app you are about to use.
>>"%LOG%" echo refused: target is this clean copy
goto :nothing

:contains
echo   that folder CONTAINS this clean copy, so renaming it would move both.
echo   point at the old JARVIS folder itself, not the folder around it.
>>"%LOG%" echo refused: target contains this copy
goto :nothing

:toobig
echo   that is a whole drive. point at the old JARVIS folder itself.
>>"%LOG%" echo refused: target is a drive
goto :nothing

:notjarvis
echo   that folder has no run.py and no arcdesk folder - it does not look
echo   like a JARVIS copy. nothing changed.
>>"%LOG%" echo refused: not a jarvis folder: %OLD%
goto :nothing

:failed
echo   could not rename it. most likely JARVIS is still open, or the folder
echo   is in use. quit JARVIS from the tray and run this file again.
>>"%LOG%" echo rename failed for %OLD%
goto :nothing

:nothing
echo.
echo   stopped. nothing was changed.
echo.
echo   your clean JARVIS is here:  %HERE%
echo   open it with:  %HERE%\JARVIS.bat
>>"%LOG%" echo stopped without changes
goto :eof

REM ------------------------------------------------------------------ helpers
:look
if exist "%~1" (
  echo   [ keep ]  %~2
) else (
  echo   [  none ]  %~2
)
exit /b 0

:cand
if not exist "%~1\run.py" exit /b 0
for %%I in ("%~1") do set "C=%%~fI"
if /i "!C!"=="!HERE!" exit /b 0
echo    found: !C!
set "FOUND=1"
exit /b 0

:rename
set "N=1"
set "DEST=%PARENT%\JARVIS-OLD"
:rename_loop
if not exist "!DEST!" goto :rename_do
set /a N+=1
if !N! gtr 9 exit /b 1
set "DEST=%PARENT%\JARVIS-OLD-!N!"
goto :rename_loop
:rename_do
move "!OLD!" "!DEST!" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
