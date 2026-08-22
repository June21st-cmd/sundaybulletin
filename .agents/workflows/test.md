---
description: 프로젝트 단위 테스트 및 템플릿 검증을 실행하는 워크플로우
---

# 테스트 실행 워크플로우 (test)

1. 테스트 명령어를 실행합니다:
   ```bash
   pytest tests/ -v || python3 -m unittest discover tests
   ```
2. 모든 테스트가 통과(Green)하는지 확인합니다.
