@echo off
rem Sunday Bulletin Generation Script (Windows Batch)
cd /d "%~dp0\.."

set DATA_FILE=%1

if "%DATA_FILE%"=="" (
    for /f "delims=" %%F in ('dir /b /o-d data\inputs\*.yaml data\inputs\*.yml 2^>nul') do (
        set DATA_FILE=data\inputs\%%F
        goto :FOUND
    )
)

if "%DATA_FILE%"=="" (
    set DATA_FILE=data\samples\sample_hyanglin_20260816.yaml
)

:FOUND
echo [INFO] Sunday Bulletin 자동 생성을 시작합니다: %DATA_FILE%
python src\main.py --data "%DATA_FILE%" --output output\

if exist output\ (
    echo [INFO] output 폴더를 엽니다...
    explorer output\
)

pause
