---
name: bulletin-generator
description: 주간 주보 원고 데이터를 기반으로 HWPX 및 Typst 템플릿을 치환하여 최종 인쇄본(HWPX/PDF)을 생성하는 도메인 스킬
---

# 주보 생성 전문가 (bulletin-generator)

매주 바뀌는 주보 원고 데이터(예배 순서, 설교 정보, 찬송가, 교회 소식 등)를 읽어 정형 템플릿에 주입하고, 컬러 인쇄용 HWPX 및 초고속 고화질 Typst PDF를 생성합니다.

## ⚠️ 실행 가드
* **주보 조판(HWP/PDF)은 사용자가 명시적으로 요청("주보 작업해", "HWP 만들어줘")할 때만 실행합니다.**
* 단순 원고 입력이나 텍스트 정리 단계에서는 절대 임의로 생성 명령을 먼저 수행하지 않습니다.

## 예전 찬송 규칙
* **응답 찬송 / 고백송 교체 규칙**:
  * **9월**: 주기도송 (`주기도송(1) 245장`)
  * **10월**: 신앙고백송 (`국악찬송 254장`)
* **결단 찬송**: 국악찬송 등 지정 곡을 `decision_hymn` 및 `worship_offering_hymn`에 매핑합니다.

## 지원 엔진
1. **HWPX 엔진 (`src/hwpx_engine.py`)**: 기존 한글 서식(표, 글자 장평, 배분 정렬)을 100% 보존하며 텍스트 태그 치환.
2. **Typst 엔진 (`src/typst_engine.py`)**: 0.05초 초고속 벡터 컬러 PDF 생성 (A4 2단 가로 인쇄).

## 실행 절차
1. **원고 데이터 준비**: `data/inputs/bulletin_YYYYMMDD.yaml` 작성 또는 AI 정제.
2. **생성 명령 실행**:
   ```bash
   python3 src/main.py --data data/inputs/bulletin_YYYYMMDD.yaml --engine all --output output/
   ```
3. **결과 확인**: `output/` 폴더에 생성된 `.hwpx` 및 `.pdf` 파일 확인.
