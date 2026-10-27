@echo off
REM ============================================================
REM  Arc Desk - FREE local AI setup.  No account. No key. No card.
REM  Installs Ollama (open source, MIT) and pulls a small model,
REM  then verifies Arc Desk can see it on 127.0.0.1:11434
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Arc Desk - free local AI

echo.
echo   Arc Desk - free local AI
echo   ========================
echo   Everything here stays on this laptop. Nothing is uploaded.
echo.

REM ---- is Ollama already there? -------------------------------
where ollama >nul 2>nul
if %errorlevel%==0 goto :have_ollama

echo [1/3] Ollama not found. Trying winget (free, open source, MIT) ...
winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
if %errorlevel%==0 goto :installed

echo.
echo   Automatic install did not work.
echo   Do this manually - it is still completely free:
echo     1. open  https://ollama.com/download
echo     2. download the Windows installer, run it
echo     3. close this window, run setup_free_ai.bat again
echo.
pause
exit /b 1

:installed
echo.
echo   Installed. You may need to close and reopen this window so PATH updates.
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
where ollama >nul 2>nul
if %errorlevel% neq 0 (
    echo   Close this window, then run setup_free_ai.bat again.
    pause
    exit /b 1
)

:have_ollama
echo [1/3] Ollama found.
echo.
echo [2/3] Pulling a small model (llama3.2:3b, about 2 GB, one time only) ...
ollama pull llama3.2:3b
if %errorlevel% neq 0 (
    echo.
    echo   Pull failed. Check your internet, then rerun. The model is free.
    pause
    exit /b 1
)

echo.
echo [3/3] Checking that Arc Desk can see it ...
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)
%PY% tools\free_ai_check.py

echo.
echo   Done. In Arc Desk:  Settings -^> Local AI ^& tools -^> Scan -^> "Use this brain"
echo   That brain costs nothing, needs no account, and works offline.
echo.
pause
exit /b 0
