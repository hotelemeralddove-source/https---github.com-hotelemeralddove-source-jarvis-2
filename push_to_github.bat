@echo off
REM ===========================================================================
REM  Pushes this folder to your own GitHub repo and lets GitHub build the
REM  Windows installer (you do not need a Windows build machine for that).
REM
REM      push_to_github.bat  https://github.com/<you>/arcdesk.git
REM
REM  Needs git for Windows once:  winget install Git.Git
REM  No account is stored by this script; git asks you to sign in the first time.
REM ===========================================================================
setlocal
if "%~1"=="" (
  echo.
  echo   Usage:  push_to_github.bat  https://github.com/^<you^>/arcdesk.git
  echo.
  echo   Create the empty repo first:  https://github.com/new
  echo   Do NOT add a README there - an empty repo is easier to push into.
  exit /b 2
)
set REPO=%~1
where git >nul 2>&1 || (
  echo   git is not installed. One command:
  echo       winget install Git.Git
  exit /b 1
)
cd /d "%~dp0"

if not exist .git (
  git init || exit /b 1
  git branch -M main
)
git add -A || exit /b 1
git commit -m "arcdesk" || echo   (nothing new to commit)
git remote remove origin >nul 2>&1
git remote add origin "%REPO%"
echo.
echo   pushing... git may ask you to sign in to GitHub.
git push -u origin main || (
  echo.
  echo   Push failed. Two usual causes:
  echo     * the repo is not empty  -^> create it without a README
  echo     * wrong URL              -^> it must end in .git
  exit /b 1
)
echo.
echo   ============================================================
echo    Pushed. GitHub is building the installer now:
echo      %REPO%
echo    -^> Actions  -^> "build windows installer"
echo    -^> when it turns green, download the artifact ArcDeskSetup
echo   ============================================================
