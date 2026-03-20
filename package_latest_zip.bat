@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

set "APP_NAME=OTC-Risk-App"
set "DIST_DIR=dist\%APP_NAME%"
set "OUT_DIR=dist_release"
set "ZIP_NAME=CH-OTC-Risk-App.zip"

echo [1/4] Checking Python...
python --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python is not installed or not in PATH.
  pause
  exit /b 1
)

echo [2/4] Releasing old dist folder...
call :prepare_dist_dir
if errorlevel 1 (
  pause
  exit /b 1
)

echo [3/4] Verifying packaging dependencies...
python -c "import streamlit, pandas, matplotlib, chinese_calendar, akshare, pyarrow, PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Missing packaging dependencies in the current Python environment.
  echo [ERROR] Please install them manually before building:
  echo         python -m pip install streamlit pandas matplotlib chinese_calendar akshare pyarrow pyinstaller
  pause
  exit /b 1
)

python -m PyInstaller --noconfirm --clean OTC-Risk-App.spec
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo [4/4] Creating zip package...
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%DIST_DIR%' -DestinationPath '%OUT_DIR%\%ZIP_NAME%' -CompressionLevel Optimal -Force"
if errorlevel 1 (
  echo [ERROR] Failed to create zip package.
  pause
  exit /b 1
)

echo [DONE] Package created.
for %%I in ("%OUT_DIR%\%ZIP_NAME%") do (
  echo Output: %%~fI
  echo Size: %%~zI bytes
  echo Updated: %%~tI
)
echo.
echo Double-click complete. Share the zip file directly.
pause
exit /b 0

:prepare_dist_dir
taskkill /IM "%APP_NAME%.exe" /F >nul 2>nul
if not exist "%DIST_DIR%" exit /b 0

for /L %%I in (1,1,5) do (
  rmdir /s /q "%DIST_DIR%" >nul 2>nul
  if not exist "%DIST_DIR%" exit /b 0
  timeout /t 2 /nobreak >nul
)

echo [ERROR] Failed to clear %DIST_DIR%
echo [ERROR] Another process is still using files under that folder.
echo [ERROR] Close any running OTC-Risk-App.exe, File Explorer window, or antivirus scan on that folder, then retry.
exit /b 1
