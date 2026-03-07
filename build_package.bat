@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
echo [1/5] Checking Python...
python --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Please install Python 3.10+ first.
  pause
  exit /b 1
)

echo [2/5] Installing packager...
python -m pip install --upgrade pip
python -m pip install pyinstaller
if errorlevel 1 (
  echo [ERROR] Failed to install pyinstaller.
  pause
  exit /b 1
)

echo [3/5] Building executable...
pyinstaller --noconfirm --clean --onedir --name OTC-Risk-App launcher.py ^
  --collect-all streamlit ^
  --collect-all pandas ^
  --collect-all matplotlib ^
  --collect-all chinese_calendar
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo [4/5] Copying runtime files...
copy /Y "app.py" "dist\OTC-Risk-App\app.py" >nul
if exist "otc_gui.db" copy /Y "otc_gui.db" "dist\OTC-Risk-App\otc_gui.db" >nul
if exist "manifest.json" copy /Y "manifest.json" "dist\OTC-Risk-App\manifest.json" >nul

echo [5/5] Done.
echo Output folder: dist\OTC-Risk-App
echo Share the whole folder to others, then run OTC-Risk-App.exe
pause

