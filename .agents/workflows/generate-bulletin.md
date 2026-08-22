---
description: 주간 예배 원고 데이터를 기반으로 주보 HWPX 및 Typst PDF를 자동 생성하는 워크플로우
---

# 주보 생성 워크플로우 (generate-bulletin)

1. `data/inputs/` 또는 `data/samples/`에서 주보 입력 데이터(YAML)를 확인합니다.
2. CLI를 통해 주보 생성을 실행합니다:
   ```bash
   python3 src/main.py --data data/samples/sample_20260816.yaml --engine all --output output/
   ```
3. 생성된 `output/` 폴더 내 결과물 파일(.hwpx, .pdf)의 생성 여부와 크기를 확인합니다.
