@echo off
REM ===========================================================================
REM  JARVIS - UPDATE. One file, one action: put a new version on top of this one.
REM
REM  How it decides what to do, in order:
REM    1. the app's own Python (tools\update_from_zip.py) - zipfile cannot fail the
REM       way PowerShell did ("Unable to find type [IO.Compression.ZipFile]"), and
REM       that route is also what JARVIS itself can run
REM    2. tar.exe + robocopy, both part of Windows, if there is no .venv yet
REM
REM  A full project zip has run.py at its root. A fix pack does not, and is refused
REM  with an explanation instead of being copied over the app.
REM ===========================================================================
setlocal enabledelayedexpansion
title JARVIS - update
cd /d "%~dp0"
set "HERE=%~dp0"
set "LOG=%HERE%jarvis-update-log.txt"
>"%LOG%" echo JARVIS update - %DATE% %TIME%

call "%HERE%tools\find_project.bat"
if not defined PROJ goto :wrongfolder
echo   project folder : %PROJ%
>>"%LOG%" echo project folder: %PROJ%

REM ---- 1. find the new zip ------------------------------------------------
set "ZIP="
if not "%~1"=="" if exist "%~1" set "ZIP=%~1"
if not defined ZIP for %%F in ("%HERE%ArcDesk-full-project.zip") do (
    if not defined ZIP if exist "%%~fF" set "ZIP=%%~fF"
)
if not defined ZIP for /d %%D in ("%USERPROFILE%\Downloads" "%USERPROFILE%\Desktop" "%USERPROFILE%\OneDrive\Desktop" "%HERE%..") do (
    if not defined ZIP for /f "delims=" %%F in ('dir /b /o-d "%%~D\ArcDesk-full-project*.zip" "%%~D\arcdesk-fix*.zip" 2^>nul') do (
        if not defined ZIP set "ZIP=%%~D\%%F"
    )
)
if not defined ZIP goto :nozip
echo   update file    : %ZIP%
>>"%LOG%" echo zip: %ZIP%

REM ---- 2. the good route: the app's own Python ---------------------------
set "VPY=%PROJ%\.venv\Scripts\python.exe"
if not exist "%VPY%" goto :fallback
if not exist "%PROJ%\tools\update_from_zip.py" goto :fallback

REM Close only OUR app: ask it, by pid, or over its own lock socket. Never a blanket
REM "kill every pythonw", which takes other python programs down with it.
"%PROJ%\.venv\Scripts\python.exe" "%PROJ%\tools\jarvis_state.py" --any --quiet
if not errorlevel 1 (
    echo   closing the running JARVIS so its files can be replaced ...
    "%PROJ%\.venv\Scripts\python.exe" "%PROJ%\tools\jarvis_state.py" --stop --quiet
    timeout /t 2 >nul
)
echo.
"%VPY%" "%PROJ%\tools\update_from_zip.py" "%ZIP%" --no-restart
if errorlevel 3 goto :unreadable
if errorlevel 1 goto :copyfailed
goto :start

REM ---- 2b. no .venv yet: tar + robocopy, both shipped with Windows --------
:fallback
set "TAR="
if exist "%SystemRoot%\System32\tar.exe" set "TAR=%SystemRoot%\System32\tar.exe"
if not defined TAR for /f "delims=" %%T in ('where tar 2^>nul') do if not defined TAR set "TAR=%%T"

set "ISAPP=0"
set "LIST=%TEMP%\jarvis-zip-list.txt"
if defined TAR (
    REM list first: piping a quoted program path into findstr inside FOR /F is a
    REM quoting minefield. A temp file is boring and always works.
    "%TAR%" -tf "%ZIP%" > "%LIST%" 2>nul
    if exist "%LIST%" (
        findstr /R /C:"^run\.py$" "%LIST%" >nul 2>&1
        if not errorlevel 1 set "ISAPP=1"
        if "!ISAPP!"=="0" (
            findstr /I /C:"run\.py" "%LIST%" >nul 2>&1
            if not errorlevel 1 set "ISAPP=1"
        )
        del "%LIST%" >nul 2>&1
    )
)
if "!ISAPP!"=="0" (
    >>"%LOG%" echo tar could not read it - trying PowerShell with the assembly loaded
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "try{Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop}catch{};" ^
      "$z=[System.IO.Compression.ZipFile]::OpenRead('%ZIP%');" ^
      "if($z.Entries | Where-Object {$_.FullName -eq 'run.py'}){ $z.Dispose(); exit 0 };" ^
      "$z.Dispose(); exit 3" >nul 2>nul
    if not errorlevel 1 set "ISAPP=1"
)
if "!ISAPP!"=="0" (
    echo.
    echo   This is a fix pack, and this folder has no .venv yet, so the Python route
    echo   is not available. A fix pack belongs inside a project that already works.
    echo   Download ArcDesk-full-project.zip: one file, the whole app, nothing to guess.
    pause
    exit /b 3
)
echo   the zip contains run.py - it is the whole app
>>"%LOG%" echo zip contains run.py

REM Close only OUR app: ask it, by pid, or over its own lock socket. Never a blanket
REM "kill every pythonw", which takes other python programs down with it.
"%PROJ%\.venv\Scripts\python.exe" "%PROJ%\tools\jarvis_state.py" --any --quiet
if not errorlevel 1 (
    echo   closing the running JARVIS so its files can be replaced ...
    "%PROJ%\.venv\Scripts\python.exe" "%PROJ%\tools\jarvis_state.py" --stop --quiet
    timeout /t 2 >nul
)

set "STAGE=%TEMP%\jarvis-update-%RANDOM%"
if exist "%STAGE%" rd /s /q "%STAGE%" >nul 2>&1
mkdir "%STAGE%" 2>nul
echo   unpacking ...
if defined TAR (
    "%TAR%" -xf "%ZIP%" -C "%STAGE%" 2>>"%LOG%"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
      "[System.IO.Compression.ZipFile]::ExtractToDirectory('%ZIP%','%STAGE%')" >>"%LOG%" 2>&1
)
if not exist "%STAGE%\run.py" goto :unpackfailed

echo   copying the new version over this folder (.venv is left alone) ...
robocopy "%STAGE%" "%PROJ%" /E /XD ".venv" "__pycache__" ".git" ".failures" ^
        /XF "*.pyc" "settings.json" /NFL /NDL /NJH /NJS /NP >>"%LOG%" 2>&1
if errorlevel 8 goto :copyfailed
rd /s /q "%STAGE%" >nul 2>&1
echo   done.

:start
set "VPY=%PROJ%\.venv\Scripts\python.exe"
if exist "%VPY%" (
    set "STAMP="
    for %%F in ("%PROJ%\requirements.txt") do set "STAMP=%%~zF-%%~tF"
    set "OLD="
    if exist "%PROJ%\.venv\.reqstamp" set /p OLD=<"%PROJ%\.venv\.reqstamp"
    if /i not "!STAMP!"=="!OLD!" (
        echo   new libraries in this version - installing them now, a minute, once ...
        "%VPY%" -m pip install --quiet -r "%PROJ%\requirements.txt"
        if errorlevel 1 echo   could not update them - starting anyway
        echo !STAMP!>"%PROJ%\.venv\.reqstamp"
    )
)
echo.
echo   updated. starting JARVIS ...
start "" "%PROJ%\JARVIS.bat"
>>"%LOG%" echo started JARVIS.bat after the update
timeout /t 3 >nul
exit /b 0

:nozip
echo.
echo   I cannot find a new version to install.
echo   Download ArcDesk-full-project.zip (ONE file), leave it in Downloads or on
echo   the Desktop, and double-click this again.
>>"%LOG%" echo no zip found
pause
exit /b 1


:unreadable
echo.
echo   That zip could not be read at all - it may be a partial download.
echo   Delete it, download it again, and run this file again. Nothing was changed.
>>"%LOG%" echo zip unreadable
pause
exit /b 1

:unpackfailed
echo.
echo   Could not unpack that zip. Nothing was changed: the old version still works.
echo   Two ways forward:
echo     1. open the zip in Explorer and copy the folder over this one (Yes to merge)
echo     2. send me %LOG%
>>"%LOG%" echo unpack failed
pause
exit /b 1

:copyfailed
echo.
echo   Copying failed. Nothing is half-broken: the old version is still there.
echo   Run JARVIS.bat as usual, and send me %LOG%.
>>"%LOG%" echo copy failed
pause
exit /b 1

:wrongfolder
echo.
echo   This file must sit inside the JARVIS folder (the one with run.py).
>>"%LOG%" echo wrong folder
pause
exit /b 1
