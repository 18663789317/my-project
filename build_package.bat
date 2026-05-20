@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "APP_NAME=OTC-Risk-App"
set "DIST_DIR=dist\%APP_NAME%"

echo [1/4] Checking Python...
python --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Please install Python 3.10+ first.
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

echo [4/4] Building executable...
python -m PyInstaller --noconfirm --clean OTC-Risk-App.spec
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo [DONE] Done.
echo Output folder: dist\OTC-Risk-App
echo Share the whole folder to others, then run OTC-Risk-App.exe
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
