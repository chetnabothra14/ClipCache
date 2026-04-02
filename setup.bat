@echo off
echo ============================================
echo   ClipCache - Ad Media Manager Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

:: Check pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip not found. Please reinstall Python with pip included.
    pause
    exit /b 1
)
echo [OK] pip found

:: Create folders
echo.
echo Creating folders...
mkdir backend 2>nul
mkdir frontend 2>nul
mkdir temp\frames 2>nul
mkdir trash 2>nul
mkdir reports 2>nul
mkdir uploads 2>nul
echo [OK] Folders created

:: Install Python dependencies
echo.
echo Installing Python packages (this may take a few minutes)...
cd backend
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install packages.
    pause
    exit /b 1
)
cd ..
echo [OK] Python packages installed

echo.
echo ============================================
echo   Setup Complete!
echo ============================================
echo.
echo To START ClipCache:
echo   1. Run:  start_server.bat
echo   2. Open: frontend/index.html in your browser
echo.
pause
