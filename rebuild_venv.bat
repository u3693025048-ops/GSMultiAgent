@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Rebuild project .venv only (does not touch Conda / system)
echo  Directory: %CD%
echo ============================================================
echo.

if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found. Run this from the project root.
    exit /b 1
)

if exist ".venv" (
    echo Removing old .venv ...
    rmdir /s /q ".venv"
)

set "PY="
where py >nul 2>&1 && (
    py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
)
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"

if not defined PY (
    echo [ERROR] No Python found. Install Python 3.12 and retry, or: py -3.12 ...
    exit /b 1
)

echo Using: %PY%
%PY% -m venv .venv
if errorlevel 1 (
    echo [ERROR] venv creation failed.
    exit /b 1
)

echo Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    exit /b 1
)

echo.
echo [OK] .venv ready.
echo Activate:  .venv\Scripts\activate
echo Run CLI:   .venv\Scripts\python.exe cli_agent.py --file prompt.txt
echo.
endlocal
