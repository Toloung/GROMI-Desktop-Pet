@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo GROMI Desktop Pet - EXE Builder
echo ========================================

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo [2/3] Building GROMI...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "GROMI桌面宠物" ^
    --icon "gromi.ico" ^
    --add-data "gromi_spritesheet.webp;." ^
    --hidden-import pystray._win32 ^
    gromi_desktop_pet.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [3/3] Finished: dist\GROMI桌面宠物.exe
pause
