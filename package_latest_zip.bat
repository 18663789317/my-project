@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

set "APP_NAME=OTC-Risk-App"
set "DIST_DIR=dist\%APP_NAME%"
set "OUT_DIR=dist_release"
set "ZIP_NAME=CH-OTC-Risk-App.zip"

echo [1/4] Checking runtime folder...
if not exist "%DIST_DIR%\%APP_NAME%.exe" (
  echo [INFO] Runtime not found. Building executable first...
  python --version >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
  )

  python -m pip install --upgrade pip
  python -m pip install pyinstaller
  if errorlevel 1 (
    echo [ERROR] Failed to install pyinstaller.
    pause
    exit /b 1
  )

  python -m PyInstaller --noconfirm --clean --onedir --name %APP_NAME% launcher.py ^
    --collect-all streamlit ^
    --collect-all pandas ^
    --collect-all matplotlib ^
    --collect-all chinese_calendar
  if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
  )
)

echo [2/4] Syncing latest runtime files...
copy /Y "app.py" "%DIST_DIR%\app.py" >nul
if exist "otc_gui.db" copy /Y "otc_gui.db" "%DIST_DIR%\otc_gui.db" >nul
if exist "manifest.json" copy /Y "manifest.json" "%DIST_DIR%\manifest.json" >nul

echo [3/4] Creating zip package...
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%DIST_DIR%' -DestinationPath '%OUT_DIR%\%ZIP_NAME%' -CompressionLevel Optimal -Force"
if errorlevel 1 (
  echo [ERROR] Failed to create zip package.
  pause
  exit /b 1
)

echo [4/4] Done.
for %%I in ("%OUT_DIR%\%ZIP_NAME%") do (
  echo Output: %%~fI
  echo Size: %%~zI bytes
  echo Updated: %%~tI
)
echo.
echo Double-click complete. Share the zip file directly.
pause

