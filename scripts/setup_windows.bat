@echo off
rem Sunday Bulletin Initial Setup Script for Windows
chcp 65001 >nul
cd /d "%~dp0\.."

echo ===================================================
echo   🖨️ 향린교회 주보 자동화 - 최초 환경 설정 도우미
echo ===================================================
echo.

echo [1/2] 파이썬(Python) 설치 여부를 확인합니다...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ❌ [오류] Python이 설치되어 있지 않거나 환경변수(PATH)에 등록되지 않았습니다.
    echo.
    echo 💡 해결 방법:
    echo  1. https://www.python.org/downloads/ 접속 후 최신 Python 다운로드
    echo  2. 설치 프로그램 실행 시 맨 아래 [Add python.exe to PATH] 를 반드시 체크하고 설치!
    echo.
    pause
    exit /b 1
)

python --version
echo  ✓ 파이썬이 정상적으로 확인되었습니다.
echo.

echo [2/2] 주보 제작에 필요한 필수 패키지(PyYAML, lxml 등)를 설치합니다...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ❌ 패키지 설치 중 오류가 발생했습니다. 인터넷 연결을 확인해주세요.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   🎉 모든 설정이 성공적으로 완료되었습니다!
echo   이제 scripts\generate_bulletin.bat 를 실행하세요.
echo ===================================================
pause
