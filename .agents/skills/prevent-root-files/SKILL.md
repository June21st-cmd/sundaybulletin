---
name: prevent-root-files
description: 프로젝트 루트 디렉터리에 불필요한 파일이 직접 생성되거나 커밋되는 것을 감지하고 차단하는 가이드 및 스크립트
---

# 프로젝트 루트 파일 생성 방지 스킬 (prevent-root-files)

프로젝트 루트 디렉터리는 프로젝트 설정 파일 및 핵심 문서(`README.md`, `requirements.txt`, `.gitignore`, 진입점 등)로만 한정하여 깨끗하게 유지해야 합니다.

## 디렉터리 배치 원칙
- **소스 코드**: `src/`
- **템플릿 파일**: `templates/`
- **입력/샘플 데이터**: `data/`
- **생성된 결과물**: `output/`
- **문서**: `docs/`
- **테스트**: `tests/`
- **일회성/임시 파일**: `tmp/`
