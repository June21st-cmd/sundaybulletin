---
name: writing-skills
description: 프로젝트 로컬 스킬(.agents/skills/)을 새로 설계하고 추가하는 스킬
---

# Writing Skills

## 로컬 스킬 구조
```text
.agents/skills/<skill-name>/
├── SKILL.md              ← 필수: YAML Frontmatter + 지침
├── scripts/              ← 선택: 실행 스크립트
└── references/           ← 선택: 참조 문서
```

## SKILL.md 작성 규칙
1. **YAML Frontmatter**:
   - `name`: kebab-case 영문명
   - `description`: 스킬 목적을 한 문장으로 설명
2. **본문 구성**:
   - 트리거 조건 (언제 사용하는가)
   - 실행 절차 (단계별 가이드)
   - 산출물 및 주의사항
3. **독립성 유지**: 다른 개발자가 바로 쓸 수 있도록 글로벌 경로 의존성 없이 작성.
