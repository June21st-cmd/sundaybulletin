@echo off
rem Sunday Bulletin Initial Setup Script for Windows
chcp 65001 >nul
cd /d "%~dp0\.."

echo ===================================================
echo   Sunday Bulletin Initial Setup Helper
echo ===================================================
echo.

set PYTHON_CMD=python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%~dp0..\python-embed\python.exe" (
        set PYTHON_CMD="%~dp0..\python-embed\python.exe"
    ) else (
        echo.
        echo [ERROR] Python is not installed.
        echo.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% --version
echo Python check completed.
echo.

echo [2/2] Installing requirements...
set PYTHONUTF8=1
%PYTHON_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   Setup completed successfully!
echo   Run scripts\generate_bulletin.bat
echo ===================================================
exit /b 0
