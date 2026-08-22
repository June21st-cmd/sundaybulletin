---
name: systematic-debugging
description: 버그, 테스트 실패, 예상치 못한 동작 발생 시 추측 대신 4단계 체계적 원인 분석을 수행하는 스킬
---

# Systematic Debugging

## 철칙: 원인 조사 없이 수정을 시도하지 않는다
(NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST)

## 4단계 절차
1. **Phase 1: 근본 원인 조사 (Root Cause Investigation)**
   - 에러 메시지와 스택 트레이스 완독
   - 재현 절차 확인 및 데이터 흐름 추적
2. **Phase 2: 패턴 분석 (Pattern Analysis)**
   - 정상 동작 예시와 실패 케이스 비교
3. **Phase 3: 가설 수립 및 최소 검증 (Hypothesis & Minimal Test)**
   - 명확한 단일 가설 수립 후 최소 변경으로 검증
4. **Phase 4: 근본 해결 및 테스트 (Implementation & Verification)**
   - 증상이 아닌 근본 원인 해결 및 회귀 방지 테스트 추가
