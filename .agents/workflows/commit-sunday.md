---
description: 최신 내용을 pull 받고 clean 상태까지 커밋한 뒤 원격에 push하는 주보 전용 커밋 워크플로우
---

# 주보 커밋 & 푸시 워크플로우 (commit-sunday)

1. 원격 저장소 동기화: `git pull`
2. 변경 사항 확인: `git status`
3. 논리적 그룹별 명시적 스테이징 및 커밋: `git add <files...>` & `git commit -m "<type>: <description>"`
4. clean 상태 확인 후 푸시: `git push`
