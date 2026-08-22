---
name: verification-before-completion
description: 작업 완료 주장 전, 직접 검증 명령어를 실행하고 결과를 확인하는 필수 검증 스킬
---

# Verification Before Completion

## 철칙: 증거 없는 완료 주장은 금지된다
(NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE)

## 게이트 절차
1. **식별 (IDENTIFY)**: 완료를 입증할 명령어 확인 (예: `pytest`, `python -m unittest`, 템플릿 렌더링 CLI 실행)
2. **실행 (RUN)**: 전체 명령어를 직접 실행
3. **확인 (READ)**: 출력 결과, 종료 코드(Exit Code 0), 에러 로그 확인
4. **보고 (REPORT)**: 검증 증거와 함께 작업 완료 보고
