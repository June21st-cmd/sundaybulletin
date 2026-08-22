---
name: karpathy-guidelines
description: LLM 코딩 실수를 줄이기 위한 행동 지침. 과잉 설계를 피하고 외과적 수정과 단순성을 유지한다.
---

# Karpathy Guidelines

## 1. 과잉 엔지니어링 방지 (Don't Over-Engineer)
- 지금 필요한 것만 구현한다. 미래의 모호한 요구사항을 위해 불필요한 계층이나 추상화를 도입하지 않는다.

## 2. 외과적 변경 (Surgical Changes)
- 수정하려는 버그나 기능에 직접 관련된 코드만 변경한다. 주변 코드를 임의로 리팩토링하지 않는다.

## 3. 단순성과 가독성 (Simplicity First)
- 복잡한 메타프로그래밍보다 누구나 읽기 쉬운 명시적이고 단순한 코드를 작성한다.
