#!/usr/bin/env bash
set -e

# Sunday Bulletin Initial Setup Script for Linux/macOS
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

echo "==================================================="
echo "  🖨️ 향린교회 주보 자동화 - 최초 환경 설정 도우미"
echo "==================================================="

if ! command -v python3 &> /dev/null; then
    echo "❌ [오류] python3가 설치되어 있지 않습니다. Python 3.9 이상을 설치해주세요."
    exit 1
fi

echo "[1/2] Python 확인: $(python3 --version)"
echo "[2/2] 필수 패키지 설치 중 (requirements.txt)..."
pip install -r requirements.txt || pip3 install -r requirements.txt

echo "==================================================="
echo "  🎉 모든 설정이 완료되었습니다! (./scripts/generate_bulletin.sh 실행)"
echo "==================================================="
