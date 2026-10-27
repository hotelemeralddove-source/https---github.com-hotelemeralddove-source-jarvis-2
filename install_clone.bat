@echo off
REM Arc Desk - "speak in MY voice" + "only MY voice wakes it".
REM Everything here is free and download-once. Nothing is installed silently:
REM every step prints what it is about to fetch, how big it is, and why.
setlocal
echo.
if exist "%~dp0VERSION.txt" type "%~dp0VERSION.txt"
echo.

REM This file is one piece of the project, not the project. Find the real folder
REM first (the one holding run.py and requirements.txt) - see tools\find_project.bat.
call "%~dp0tools\find_project.bat"
if not defined PROJ goto :wrongfolder
cd /d "%PROJ%"
echo [Arc Desk] project folder: %PROJ%
set "PDIR=%PROJ%"
if /i "%PDIR:Downloads=%"=="%PDIR%" goto :notdownloads
echo.
echo   NOTE: this copy lives in Downloads. Windows and cleaners empty that folder, and a
echo   second copy next to it is how two JARVIS folders start. Move it once:
echo     %PROJ%\ONE-PLACE.bat      keeps one copy in %USERPROFILE%\JARVIS
echo.
:notdownloads

REM Fail BEFORE building anything: a venv made in the wrong folder is a mess to
REM clean up, and this check is the difference between a clear message and
REM "Could not open requirements file".
if not exist "requirements.txt" goto :wrongfolder
if not exist "run.py" goto :wrongfolder

if exist .venv\Scripts\python.exe (
  set "PY=.venv\Scripts\python.exe"
) else (
  REM No environment yet: find Python, or fetch it. Never assume it is there.
  call "%~dp0tools\pybootstrap.bat"
  if errorlevel 1 goto :fail
)

set "LANGPICK=ta"
if /i "%~1"=="en" set "LANGPICK=en"
if /i "%~1"=="english" set "LANGPICK=en"
if /i "%~1"=="hi" set "LANGPICK=hi"
if /i "%~1"=="hindi" set "LANGPICK=hi"
if /i "%~1"=="ta" set "LANGPICK=ta"
if /i "%~1"=="tamil" set "LANGPICK=ta"

echo ============================================================
echo  Arc Desk - voice cloning and voice lock
echo ============================================================

echo.
echo  Scope: TAMIL, HINDI, ENGLISH. Those three are the promise and the tests.
echo  The other Indic languages usually work, but are not claimed.
echo.
echo  What this installs, and how big:
echo    sherpa-onnx + 30 MB speaker model   voice lock (only your voice)
echo    piper + ta/hi/en voices             free fallback voice, about 60 MB, no GPU
echo    IndicF5 (optional, ~1.5 GB)         clone your voice in TAMIL + HINDI
echo    XTTS-v2 (optional, ~1.9 GB)         clone your voice in ENGLISH
echo.
echo  Already installed it yourself, in a terminal or a conda environment?
echo  Then nothing here is downloaded twice: JARVIS finds that python by itself and
echo  speaks through it. The last step below prints exactly what is ready.
echo.
echo  Voice cloning needs a GPU to feel instant. On a CPU it works, but slowly -
echo  the app will say so rather than hide it.
echo.
pause

echo.
echo [1/3] voice lock engine (small) ...
%PY% -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('sherpa_onnx') else 1)" >nul 2>&1
if not errorlevel 1 echo   sherpa-onnx is already here - nothing to download
if errorlevel 1 %PY% -m pip install --quiet sherpa-onnx || goto :fail
%PY% tools\voice_setup.py lock-model || echo   (model download failed - you can retry later)

echo.
echo [2/3] piper, the free fallback voice (Tamil, Hindi, English) ...
%PY% -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('piper') else 1)" >nul 2>&1
if not errorlevel 1 echo   the piper engine is already here - nothing to download
if errorlevel 1 %PY% -m pip install --quiet piper-tts || echo   (piper failed; SAPI will be used instead)
%PY% tools\engine_get.py status | findstr /i "Piper" && echo   ^(the voice files are fetched by the app: Settings -^> Voice^)

echo.
echo [3/3] the clone engine - downloaded for you, no questions
echo.
echo   Tamil or Hindi   IndicF5   about 1.5 GB   clones YOUR voice, 11 Indian languages
echo   English          XTTS-v2   about 1.9 GB   clones YOUR voice in English
echo.
echo   The right one for the language below starts by itself, in this window, with a
echo   moving progress line. Pull the plug with Ctrl+C - nothing half-done is ever used.
echo.
echo   Already downloaded it in a terminal? Then nothing is downloaded twice: JARVIS
echo   uses your huggingface-cli login token and the copy already in your HF cache.
echo.
echo   Language: %LANGPICK%   ^(change it:  install_clone.bat en   or   install_clone.bat hi^)
echo.
echo   Starting in 6 seconds ...
timeout /t 6 /nobreak >nul 2>&1
%PY% tools\engine_get.py auto %LANGPICK%
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" goto :clone_ok
if "%RC%"=="2" goto :clone_gated
goto :clone_trouble

:clone_ok
echo.
echo   The clone engine is ready. Nothing else to download.
goto :next_steps

:clone_gated
echo.
echo   No token was pasted, so no download happened. That is a decision, not an error:
echo   everything else in this window is already done, and the token can be pasted later
echo   in the app: Settings -^> Voice -^> engines.
goto :next_steps

:clone_trouble
echo.
echo   The download did not finish. The reason is the last line above, and it is one of
echo   three things: no internet, not enough free disk space, or a gated model that needs
echo   the free token. Nothing was wasted - running this file again resumes from where it
echo   stopped, because the packages and the model are cached.
goto :next_steps

:next_steps
echo.
echo [check] what this computer can speak with right now ...
%PY% tools\engine_get.py status
echo.
echo ============================================================
echo  Now teach it YOUR voice (one clip, 10-12 s of just you talking):
echo.
echo    %PY% tools\voice_setup.py import "C:\path\to\your-clip.mp4"
echo    %PY% tools\voice_setup.py try "vanakkam macha, ellam ready"
echo.
echo  Clean a noisy clip first if you have one (measures SNR before and after):
echo    %PY% tools\clean_voice.py "C:\path\to\clip.mp3" --import --transcript "the words"
echo.
echo  Then lock it to your voice on THIS machine (3 short recordings):
echo.
echo    %PY% tools\voice_setup.py lock-enroll me rec1.wav rec2.wav rec3.wav
echo    %PY% tools\voice_setup.py lock-test rec4.wav
echo    %PY% tools\voice_setup.py lock-on
echo.
echo  A different laptop keeps its own enrolled voice - nothing is shared unless
echo  you copy %APPDATA%\ArcDesk\voiceid yourself.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo [Arc Desk] setup stopped. Python 3.10+ and internet are needed.
echo             Nothing was left half-installed; run this file again any time.
pause
exit /b 1

:wrongfolder
echo.
echo [Arc Desk] This is not the project folder, so there is nothing to install here.
echo.
echo   What happened: a fix pack is a few files that belong INSIDE the ArcDesk
echo   project. Unzipped on its own there is no requirements.txt next to this .bat,
echo   so pip can only complain that the file is missing.
echo.
echo   Pick one:
echo     1) You have ArcDesk.exe (installer or portable zip)? You need none of this.
echo     2) You have the project folder (run.py + requirements.txt)? Unzip the fix
echo        pack INTO it and double-click this file again.
echo     3) Neither? Clone it with GitHub Desktop, then run this file inside it.
echo.
pause
exit /b 1
