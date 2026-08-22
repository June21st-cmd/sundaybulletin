#!/usr/bin/env bash
set -e

# Sunday Bulletin Generation Script (Linux/macOS)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

DATA_FILE="${1:-data/samples/sample_20260816.yaml}"
echo "🚀 Running Sunday Bulletin generation for: $DATA_FILE"

python3 src/main.py --data "$DATA_FILE" --engine all --output output/
