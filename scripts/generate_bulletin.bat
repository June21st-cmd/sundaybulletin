@echo off
rem Sunday Bulletin Generation Script (Windows Batch)
cd /d "%~dp0\.."

set DATA_FILE=%1
if "%DATA_FILE%"=="" set DATA_FILE=data\samples\sample_20260816.yaml

echo [INFO] Running Sunday Bulletin generation for: %DATA_FILE%
python src\main.py --data "%DATA_FILE%" --engine all --output output\

pause
