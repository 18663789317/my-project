@echo off
setlocal
cd /d "%~dp0"

set "APP_ROOT=%~dp0"
set "LAUNCHER=%APP_ROOT%launcher.py"

if not exist "%LAUNCHER%" (
    echo [ERROR] launcher.py not found: %LAUNCHER%
    pause
    exit /b 2
)

where py >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Trying: py -3 launcher.py
    py -3 "%LAUNCHER%"
    if not errorlevel 1 (
        exit /b 0
    )
    echo [WARN] py -3 failed, fallback to python.
)

where python >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Trying: python launcher.py
    python "%LAUNCHER%"
    if not errorlevel 1 (
        exit /b 0
    )
    echo [WARN] python launcher failed too.
)

echo [ERROR] Python launcher not found.
echo Please install Python or make sure `py` / `python` is in PATH.
pause
exit /b 9009
