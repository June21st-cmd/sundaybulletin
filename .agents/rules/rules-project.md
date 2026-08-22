---
trigger: always_on
---

# 프로젝트 개발 및 AI 행동 규칙 (Project Development & AI Rules)

## 1. 프로젝트 개요 및 SSOT 원칙
- 본 프로젝트는 교회 주보 제작 자동화 시스템입니다.
- **SSOT (Single Source of Truth)**: 전체 아키텍처 및 기획은 `README.md` 및 `docs/`에 관리하며, 진입점 파일(`AGENTS.md`, `CLAUDE.md`, `.cursorrules`)은 얇은 래퍼(Thin Wrapper)로 유지합니다.
- 스킬 원본은 `.agents/skills/`, 워크플로우 원본은 `.agents/workflows/`에만 둡니다.

## 2. 크로스 플랫폼 호환성 (Windows & Linux/macOS)
- **실행 환경**: 사용자의 실 운영 환경(Windows PC + 한컴오피스/프린터)과 개발/배포 환경(Linux/WSL/macOS) 모두에서 동작해야 합니다.
- **경로 처리**: 하드코딩된 슬래시/백슬래시 대신 반드시 Python `pathlib.Path` 또는 `os.path.join`을 사용합니다.
- **인코딩**: 모든 텍스트/YAML/JSON 입출력은 UTF-8(`encoding='utf-8'`)을 명시합니다.

## 3. 계획 수립 및 변경 전 설명 (Explain Before Act)
- 복잡한 작업이나 파일 수정 전, 현재 상황과 원인을 파악하고 변경 계획을 먼저 사용자에게 브리핑합니다.
- 임의로 추측하여 과도한 설계를 하지 않으며, 최소한의 외과적 수정(Surgical Changes)을 원칙으로 합니다.

## 4. TDD 및 검증 원칙 (Verification Before Completion)
- 새로운 기능 구현이나 버그 수정 시 `tests/`에 테스트를 먼저 작성하거나 함께 작성합니다.
- 작업 완료 주장 전, 반드시 테스트 및 실행 명령을 직접 수행하여 결과(성공 여부, 에러 코드 0)를 확인한 후 보고합니다.

## 5. 커밋 및 Git 관리 규칙
- **선택적 스테이징**: `git add .`를 금지하고, 수정한 파일만 명시적으로 `git add <file>` 합니다.
- **루트 디렉터리 청결**: 임시 파일이나 생성된 주보 결과물은 루트가 아닌 `output/` 또는 `tmp/`에 저장합니다.
- **메인 브랜치 보호**: `main` 또는 `dev` 브랜치 푸시 전 승인 단계를 거칩니다.
- **커밋 메시지 형식**: `<type>: <description>` (예: `feat: add Typst Korean layout helper`, `fix: resolve HWPX XML tag parsing error`)

## 6. 언어 정책
- 문서, 주석, 이슈 및 사용자 소통은 한국어를 기본으로 합니다.
