@echo off
setlocal
cd /d "%~dp0"

set "APP_ROOT=%~dp0"
set "LAUNCHER=%APP_ROOT%launcher.py"
set "APP_FILE=%APP_ROOT%app.py"

if not exist "%LAUNCHER%" (
    echo [ERROR] launcher.py not found: %LAUNCHER%
    pause
    exit /b 2
)

if not exist "%APP_FILE%" (
    echo [ERROR] app.py not found: %APP_FILE%
    pause
    exit /b 2
)

echo [INFO] Closing old Streamlit/Python processes for this project...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$launcher = [System.IO.Path]::GetFullPath('%LAUNCHER%'); $app = [System.IO.Path]::GetFullPath('%APP_FILE%'); $projectPids = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and (($_.CommandLine -like ('*' + $launcher + '*')) -or ($_.CommandLine -like ('*' + $app + '*'))) } | ForEach-Object { [int]$_.ProcessId }); $portPids = @(Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { [int]$_ }); @($projectPids + $portPids) | Where-Object { $_ -gt 0 -and $_ -ne $PID } | Sort-Object -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop; Write-Host ('[INFO] Stopped old process PID ' + $_) } catch { Write-Host ('[WARN] Could not stop PID ' + $_ + ': ' + $_.Exception.Message) } }"
timeout /t 1 /nobreak >nul

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
