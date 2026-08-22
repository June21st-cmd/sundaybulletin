#!/usr/bin/env bash
set -e

# Sunday Bulletin Generation Script (Linux/macOS)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

# 1. Check if argument provided, otherwise search data/inputs/, fallback to sample
if [ -n "$1" ]; then
    DATA_FILE="$1"
else
    LATEST_INPUT=$(find data/inputs -maxdepth 1 -name "*.yaml" -o -name "*.yml" 2>/dev/null | sort -r | head -n 1)
    if [ -n "$LATEST_INPUT" ]; then
        DATA_FILE="$LATEST_INPUT"
    else
        DATA_FILE="data/samples/sample_hyanglin_20260816.yaml"
    fi
fi

echo "🚀 Sunday Bulletin 자동 생성을 시작합니다: $DATA_FILE"
python3 src/main.py --data "$DATA_FILE" --output output/
