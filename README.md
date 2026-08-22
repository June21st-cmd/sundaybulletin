# 🖨️ 윈도우 환경 주보 제작 자동화 종합 가이드 (Sunday Bulletin)

> [!NOTE]
> **핵심 전제 조건 (Prerequisites & Constraints)**
> 1. **실행 환경**: 윈도우(Windows) PC 및 리눅스/macOS 개발 환경 지원
> 2. **인쇄 환경**: 전문 인쇄소 조판 불필요, **교회 자체 컬러 프린터 A4 출력/인쇄**
> 3. **비용 원칙**: **유료 소프트웨어 구독 제외** (완전 무료 / 오픈소스 / 기본 오피스 활용)
> 4. **서식 품질**: 기존 한글(.hwp/.hwpx)의 **표 레이아웃, 글자 장평(가로 확대), 배분 정렬, A4 2단 접지 서식 100% 보존**
> 5. **자동화 목표**: 매주 바뀌는 원고를 AI가 정리하여 **원클릭으로 1초 만에 인쇄본 생성**

---

## 📖 주보 제작 실전 사용법 (Quick Start & Usage Guide)

매주 주보를 제작할 때 아래의 **3단계 워크플로우**로 1초 만에 인쇄본을 완성합니다.

```text
[ 설교 메모 / 행사 원고 ]
           │
           ▼ 1단계 (AI 비서에게 원고 전달)
[ data/inputs/20260823.yaml 저장 ]
           │
           ▼ 2단계 (배치파일 더블클릭 또는 스크립트 실행)
[ 1초 만에 HWPX XML 치환 생성 ]
           │
           ▼ 3단계 (한글에서 열어 인쇄)
[ 🖨️ 교회 컬러 프린터 A4 인쇄 ]
```

---

### 1단계 — 주간 원고 YAML 준비 (AI 비서 활용)

매주 교역자/사무원이 작성한 설교 제목, 성경 본문, 교회 소식 메모를 AI(ChatGPT, Claude, Antigravity 등)에게 아래 프롬프트와 함께 전달합니다:

> **AI 전달 프롬프트:**
> ```text
> 아래 주보 원고를 읽고 Sunday Bulletin용 YAML 포맷으로 정제해줘:
> 
> [원고 내용 붙여넣기]
> ```

생성된 내용을 **`data/inputs/20260823.yaml`** (해당 주일 날짜) 파일로 저장합니다.

<details>
<summary><b>📄 YAML 파일 예시 (data/samples/sample_hyanglin_20260816.yaml 참고)</b></summary>

```yaml
metadata:
  date_compact: "20260823"
  date_korean: "2026년 8월 23일"
  foundation_year: "73"
  unification_year: "82"
  season: "성령강림 후 열셋째주일"
  motto: "작은 믿음 다시 모아 새로 심는 향린 73"
  headline_left: "환경선교주일 연합예배"
  headline_right: "청년부 여름 농촌봉사활동 보고"

worship_1:
  call_scripture: "시편 104:24-30"
  opening_hymn: "찬송 478장"
  scripture: "창세기 1:26-31"
  sermon_title: "창조의 숨결을 회복하라"
  preacher: "담임목사"
  response_hymn: "찬송 470장"
  offering_hymn: "찬송가 50장 1절"
  benediction: "담임목사"

announcements:
  - title: "환경선교주일 녹색 헌금 안내"
    content: "생명과 환경을 지키는 선교 사역에 사용됩니다."
  - title: "정기 당회"
    content: "오늘 오후 1시 30분 당회실"
  - title: "구역장 모임"
    content: "8/27(목) 19:00 향우실"

prayer_requests:
  - name: "김향린 교우"
    content: "건강 회복과 치료를 위해 기도해 주세요."
```
</details>

---

### 2단계 — 원클릭 주보 생성 실행

- **윈도우 사용자 (권장)**:
  - `scripts/generate_bulletin.bat` 파일을 **더블클릭**합니다.
  - `data/inputs/` 폴더 내 가장 최신 YAML 파일을 자동 감지하여 주보를 생성하고, 생성이 완료되면 `output/` 폴더를 자동으로 열어줍니다.
- **리눅스 / macOS 사용자**:
  ```bash
  ./scripts/generate_bulletin.sh
  ```
- **CLI 직접 실행**:
  ```bash
  python3 src/main.py --data data/inputs/20260823.yaml --output output/
  ```

---

### 3단계 — 출력 결과 확인 및 인쇄

- `output/` 폴더에 생성된 **`[주보] 20260823.hwpx`** 파일을 한컴오피스 한글에서 엽니다.
- 기존 주보와 100% 동일한 서식(표, 글자 장평, 배분 정렬)이 유지되었는지 확인한 후, **`Ctrl + P` (인쇄)**를 눌러 컬러 프린터로 출력합니다.

---

## 🏷️ HWPX 템플릿 지원 태그 일람표 (Tag Reference)

`templates/hwpx/template.hwpx` 양식 파일 내에서 아래의 태그들을 사용하면 YAML 데이터와 1:1 자동 매핑됩니다:

| 구분 | 태그명 (한글/영문 모두 지원) | 설명 | 미입력 시 동작 |
| :--- | :--- | :--- | :--- |
| **표지 헤더** | `{{date_korean}}` / `{{주일일자}}` | "2026년 8월 16일" | 빈 문자열 |
| | `{{foundation_year}}` / `{{창립주년}}` | 교회 창립 주년 (예: 73) | 73 |
| | `{{unification_year}}` / `{{통일염원}}` | 통일염원 년도 (예: 82) | 82 |
| | `{{season}}` / `{{절기}}` | 교회력 절기 (예: 성령강림주일) | 빈 문자열 |
| | `{{motto_line1}}`, `{{motto_line2}}` / `{{표어}}` | 표어 1~2행 | 빈 문자열 |
| | `{{headline_left}}`, `{{headline_right}}` | 1면 주요 소식 헤드라인 | 빈 문자열 |
| **예배 순서** | `{{worship_call_scripture}}` / `{{예배부름_성경}}` | 예배부름 성경 구절 | 빈 문자열 |
| | `{{worship_opening_hymn}}` / `{{여는찬송}}` | 여는 찬송가 장/곡명 | 빈 문자열 |
| | `{{worship_scripture}}` / `{{성경본문}}` | 성서읽기 구절 | 빈 문자열 |
| | `{{worship_gospel}}` / `{{복음서읽기}}` | 복음서 본문 구절 | 빈 문자열 |
| | `{{worship_sermon_title}}` / `{{설교제목}}` | 하늘뜻펴기(설교) 제목 | 빈 문자열 |
| | `{{worship_preacher}}` / `{{설교자}}` | 설교자 이름 | 빈 문자열 |
| | `{{worship_offering_hymn}}` / `{{봉헌찬송}}` | 봉헌 찬송가 | 빈 문자열 |
| | `{{worship_benediction}}` / `{{축복기도}}` | 축도자 이름 | 담임목사 |
| **교회 소식** | `{{ad1_title}}` ~ `{{ad15_title}}` | 광고 1~15번 제목 | **공백 자동 소거** |
| | `{{ad1_content}}` ~ `{{ad15_content}}` | 광고 1~15번 상세 내용 | **공백 자동 소거** |
| **기도 나눔** | `{{prayer1_name}}` ~ `{{prayer10_name}}` | 기도나눔 1~10번 교우명 | **공백 자동 소거** |
| | `{{prayer1_content}}` ~ `{{prayer10_content}}` | 기도나눔 1~10번 내용 | **공백 자동 소거** |

> [!TIP]
> **자동 슬롯 소거 기능**: 광고가 3개만 있는 주간이라도 템플릿에 배치된 `{{ad4_title}}`~`{{ad15_title}}` 태그는 화면에 태그 문자열이 남지 않고 **빈 문자열로 깨끗하게 자동 삭제**되어 표와 서식의 무결성을 완벽하게 유지합니다.

---

## 🏛️ 문서 및 AI 설정의 SSOT

이 프로젝트는 하나의 파일에 모든 정보를 모으지 않습니다. 각 정보 영역은 아래 위치만 원본으로 관리하며, Codex·Claude Code·Cursor의 진입점 파일은 이 원본을 참조하는 얇은 래퍼로 유지합니다.

| 정보 영역 | 원본 위치 |
| :--- | :--- |
| 프로젝트 목적 및 전체 워크플로우 | `README.md` |
| 개발 환경 및 실행 방법 | `docs/setup-guide.md` |
| 아키텍처 및 데이터 흐름 | `docs/architecture.md` |
| 모든 AI의 공통 행동 및 보안 규칙 | `.agents/rules/` |
| 반복 작업 절차 | `.agents/workflows/` |
| 전문 작업 스킬 | `.agents/skills/` |

---

## 📊 도구별 종합 채점 및 적합도 순위 (10점 만점)

| 순위 | 도구 및 방식 | 서식 재현도 (장평/표) | 윈도우/컬러인쇄 적합성 | 비용 (무료 여부) | **최종 평점** | 종합 평가 |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| **1위 🏆** | **HWPX XML 템플릿 치환 (Python)** | **10.0 / 10** | **10.0 / 10** | **무료 (10/10)** | **9.9 / 10** | **기존 HWP 양식을 100% 그대로 쓰면서 1초 만에 완성하는 압도적 1위** |
| **2위 🥇** | **Typst (팁스트 오픈소스 조판)** | **9.5 / 10** | **10.0 / 10** | **무료 (10/10)** | **9.6 / 10** | **0.05초 초고속 컬러 PDF 생성 + AI가 한글 장평/배분 함수 완벽 제공** |
| **3위 🥈** | **HTML/CSS 웹 조판 (Edge/Chrome)** | **9.0 / 10** | **9.5 / 10** | **무료 (10/10)** | **9.3 / 10** | **완전 무료 + 브라우저 컬러 인쇄 + 웹 주보 동시 발행 파이프라인** |

---

## 💻 개발 및 테스트 가이드

### 가상환경 설정 및 패키지 설치
```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 단위 테스트 실행
```bash
python3 -m unittest discover tests -v
```
