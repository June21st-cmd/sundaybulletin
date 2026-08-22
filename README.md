# 🖨️ 향린교회 주보 제작 자동화 시스템 (Sunday Bulletin)

> [!NOTE]
> **핵심 전제 조건 (Prerequisites & Constraints)**
> 1. **비개발자 친화**: 교역자/사무원이 클릭 한 번으로 매주 주보 완성
> 2. **실행 환경**: 교회 사무실 윈도우(Windows) PC 및 리눅스/macOS 완벽 지원
> 3. **인쇄 환경**: 전문 인쇄소 조판 불필요, **교회 자체 컬러 프린터 A4 출력/인쇄**
> 4. **비용 원칙**: **유료 소프트웨어 구독 제외** (완전 무료 / 오픈소스 / 기본 오피스 활용)
> 5. **서식 품질**: 기존 한글(.hwp/.hwpx)의 **표 레이아웃, 글자 장평(가로 확대), 배분 정렬, A4 2단 접지 서식 100% 보존**

---

## 👶 1. 비전공자를 위한 1분 최초 설치 안내 (Windows PC 기준)

컴퓨터에 처음 프로그램을 설치할 때 딱 한 번만 아래 과정을 진행하시면 됩니다.

### 1단계: 파이썬(Python) 설치
1. [공식 파이썬 다운로드 페이지 (python.org)](https://www.python.org/downloads/)에 접속하여 노란색 **`Download Python`** 버튼을 클릭합니다.
2. 다운로드받은 설치 파일(`python-x.x.x-amd64.exe`)을 실행합니다.
3. ⚠️ **가장 중요한 부분 (핵심)**:
   - 설치 창 맨 아래에 있는 **`[✓] Add python.exe to PATH`** 체크박스를 **반드시 체크**합니다!
   - 그 다음 **`Install Now`**를 클릭하여 설치를 마칩니다.

```text
[설치 창 화면 예시]
┌────────────────────────────────────────────────────────┐
│ Install Python 3.x.x (64-bit)                          │
│                                                        │
│   [✓] Use admin privileges when installing py.exe     │
│   [✓] Add python.exe to PATH  ◀─── [★ 반드시 체크!!]    │
│                                                        │
│   ──> Install Now                                      │
└────────────────────────────────────────────────────────┘
```

### 2단계: 필수 도구 원클릭 자동 설치
- 프로젝트 폴더 내 **`scripts/setup_windows.bat`** 파일을 **더블클릭**합니다.
- 필요한 패키지가 3초 만에 자동으로 설치되며 `🎉 모든 설정이 완료되었습니다!` 메시지가 뜨면 준비 끝입니다.

*(리눅스/macOS 사용자는 터미널에서 `./scripts/setup_linux.sh` 실행)*

---

## 🤖 2. AI 비서(`agy`, Claude, ChatGPT)에게 요청하는 복붙 프롬프트

프로그래밍이나 명령어를 전혀 몰라도, 사용하는 AI 도구(Antigravity `agy`, Claude Code, Cursor, ChatGPT, Gemini 등)에게 아래 프롬프트를 그대로 복사해서 붙여넣으면 AI가 모든 작업을 대신 처리해 줍니다.

---

### 💬 [프롬프트 1] 처음 셋업 및 동작 검증 요청할 때
> ```text
> 이 프로젝트의 Sunday Bulletin 환경을 처음부터 완전히 셋업하고, 단위 테스트를 실행해서 모든 기능이 정상 동작하는지 검증해줘.
> ```

---

### 💬 [프롬프트 2] 매주 원고로 주보를 만들어달라고 할 때 (가장 많이 사용!)
> ```text
> 아래 이번 주 교회 주보 원고를 읽고 Sunday Bulletin 양식에 맞춰 data/inputs/ 폴더에 이번 주 YAML 데이터를 생성한 뒤, [주보] HWPX 파일을 완성해줘:
> 
> [여기에 목사님 설교 메모, 성경 본문, 찬송가, 교회 소식 등을 그대로 붙여넣기]
> ```

---

### 💬 [프롬프트 3] 주보 양식이나 새로운 항목을 추가/수정하고 싶을 때
> ```text
> 주보에 '어린이부 소식'과 '헌금위원 명단' 항목을 새로 추가하려고 해. templates/hwpx/template.hwpx 템플릿과 src/hwpx_engine.py 파서에 안전하게 반영하고 테스트해줘.
> ```

---

### 💬 [프롬프트 4] 오류가 발생했거나 동작이 안 될 때
> ```text
> 주보를 생성하는 도중 아래와 같은 오류가 발생했어. 원인을 분석하고 즉시 고쳐줘:
> 
> [오류 메시지 또는 문제 상황 붙여넣기]
> ```

---

## 🚀 3. 매주 주보 제작 3단계 실전 워크플로우

설정이 끝난 후, 매주 주보를 만들 때는 아래 **3단계**로 진행합니다:

```text
[ 설교 메모 / 행사 원고 ]
           │
           ▼ 1단계: AI 비서에게 원고 전달 (프롬프트 2번 활용)
[ data/inputs/20260823.yaml 자동 생성 ]
           │
           ▼ 2단계: 바탕화면/폴더의 배치파일 더블클릭
[ scripts/generate_bulletin.bat 실행 (1초 완성) ]
           │
           ▼ 3단계: 한글에서 열기
[ 🖨️ output/[주보] 20260823.hwpx 컬러 인쇄 ]
```

1. **1단계 (이번 주 새 원고 입력/준비)**:
   - **방법 A (가장 추천 ⭐ - AI 비서 활용)**: 목사님 카톡/메모 원고를 복사하여 AI에게 위의 **[프롬프트 2번]**으로 전달하면 `data/inputs/YYYYMMDD.yaml` 파일이 1초 만에 자동 생성됩니다.
   - **방법 B (직접 수정)**: `data/samples/sample_hyanglin_20260816.yaml`을 복사하여 `data/inputs/YYYYMMDD.yaml`로 이름을 바꾼 뒤, 메모장에서 설교제목·본문·광고 글자만 수정합니다.
2. **2단계 (원클릭 생성)**:
   - **윈도우**: `scripts/generate_bulletin.bat` **더블클릭** (최신 YAML 자동 감지 + 완료 후 `output/` 폴더 자동 열림)
   - **리눅스/Mac**: `./scripts/generate_bulletin.sh`
   - **CLI**: `python3 src/main.py --data data/inputs/YYYYMMDD.yaml`
3. **3단계 (인쇄)**: `output/[주보] YYYYMMDD.hwpx`를 한글 프로그램에서 열고 `Ctrl + P`를 눌러 교회 컬러 프린터로 인쇄합니다.

<details>
<summary><b>📄 이번 주 원고 YAML 전체 예시 (클릭하여 펼치기)</b></summary>

```yaml
# data/inputs/20260816.yaml 예시
metadata:
  date_compact: "20260816"
  date_korean: "2026년 8월 16일"
  foundation_year: "73"
  unification_year: "82"
  season: "성령강림 후 열두째주일"
  motto: "작은 믿음 다시 모아\n새로 심는 향린 73"
  headline_left: "초청 하늘뜻펴기(허석헌 목사) ╻ 평화통일주일 성만찬예식"
  headline_right: "사회부 수련회 ╻ 8.15자주평화대행진 릴레이발언"

worship_1:
  call_scripture: "시편 67:4-5"
  opening_hymn: "찬송 324장 (예수 나를 오라 하네)"
  choir_song_title: "내가 산을 향하여"
  choir_song_info: "(글: Joseph M. Martin, 곡: Joseph M. Martin & David Angerman)"
  choir_song_lyrics_1: "내가 산을 향하여서 나의 눈을 들리라 나의 도움이 어디서 올꼬"
  choir_song_lyrics_2: "천지를 지으신 여호와에게서로다"
  scripture: "시편 107:23-32 (886쪽), 고린도후서 1:8-11 (305쪽)"
  responsive_scripture_ref: "시편 107:29-31"
  responsive_scripture_1: "폭풍이 잠잠해지고, 물결도 잔잔해진다."
  responsive_scripture_2: "사방이 조용해지니 모두들 기뻐하고, 주님은 그들이 바라는 항구로 그들을 인도하여 주신다."
  responsive_scripture_3: "주님의 인자하심을 감사하여라. 사람에게 베푸신 주님의 놀라운 구원을 감사하여라."
  gospel: "마가복음서 4:35-41"
  sermon_title: "선한 이웃은 누구인가"
  preacher: "허석헌 목사"
  response_hymn: "찬송 218장"
  offering_hymn: "찬송가 50장 1절"
  benediction: "담임목사"

duties:
  w1:
    date: "08/16"
    presider: "최필수 장로"
    pastoral_prayer: "김기수 장로"
    scripture_reader: "정현정 교우"
    preacher: "한문덕 목사"
    thanks_prayer: "박융식 교우"
  w2:
    date: "08/23"
    presider: "피경원 장로"
    pastoral_prayer: "정원혁 교우"
    scripture_reader: "한문덕 목사"
    preacher: "한문덕 목사"
    thanks_prayer: "김경민 집사"
  w3:
    date: "08/30"
    presider: "김기수 장로"
    pastoral_prayer: "하상우 집사"
    scripture_reader: "곽이안 어린이"
    preacher: "유영상 목사"
    thanks_prayer: "김이도 푸른이"

donations:
  thanksgiving: "강정구/노재열(고통에서벗어남), 나영훈(범사), 박융식(생일), 배미원, 백경배, 백승남, 신인옥, 이래현(생일), 이수웅/최영미(아들입대), 이인식, 이정자(범사), 정현정(범사), 허석헌, 장소(통일의길)"

prayer_requests:
  healing_1: "김근호 김남기 김수자 김예선 김윤기 김종일 김"
  healing_2: "혁 노경선 림원섭 백경배 신지유"
  healing_3: "안미숙 오낙영 이숙영 이영일 이유미 이재필 조규혜 조신원 채미희 최충일 한상준"
  military: "이상훈 이정호 홍나모"
  overseas_1: "김강운 김연희 남원정 남택우 손유나 우상균 이혜진A 임한결 정새미 정준모 정준재"
  overseas_2: "조현모 최영미 최한나 추미양 황영준"

announcements:
  - title: "교회 장학금(상반기) 신청"
    content: "8/16(일)~8/30(일) 오전 10시까지 신청 바랍니다. ※접수: 교회 이메일(hyanglin24@gmail.com)"
  - title: "정기 목회운영위원회"
    content: "8/20(목) 19:00, 향린교회 향우실"
  - title: "선교부 신학공부 모임"
    content: "2, 4주 월 20:00, 온라인(줌)"
```
</details>

---

## 🏷️ 4. HWPX 템플릿 지원 태그 일람표 (Tag Reference)

`templates/hwpx/template.hwpx` 양식 파일 내에서 아래의 태그들을 사용하면 YAML 데이터와 1:1 자동 매핑됩니다:

| 구분 | 태그명 (한글/영문 모두 지원) | 설명 | 미입력 시 동작 |
| :--- | :--- | :--- | :--- |
| **표지 헤더 (1면)** | `{{date_korean}}` / `{{주일일자}}` | "2026년 8월 16일" | 빈 문자열 |
| | `{{foundation_year}}` / `{{창립주년}}` | 교회 창립 주년 (예: 73) | 73 |
| | `{{unification_year}}` / `{{통일염원}}` | 통일염원 년도 (예: 82) | 82 |
| | `{{season}}` / `{{절기}}` | 교회력 절기 (예: 성령강림주일) | 빈 문자열 |
| | `{{motto_line1}}`, `{{motto_line2}}` / `{{표어}}` | 표어 1~2행 | 빈 문자열 |
| | `{{headline_left}}`, `{{headline_right}}` | 1면 주요 소식 헤드라인 좌/우 | 빈 문자열 |
| **예배 순서 (2면)** | `{{worship_call_scripture}}` / `{{예배부름_성경}}` | 예배부름 성경 구절 | 빈 문자열 |
| | `{{worship_opening_hymn}}` / `{{여는찬송}}` | 여는 찬송가 장/곡명 | 빈 문자열 |
| | `{{choir_song_title}}` / `{{찬양곡명}}` | 찬양대 찬양곡 제목 | 빈 문자열 |
| | `{{choir_song_info}}` / `{{찬양정보}}` | 작사/작곡가 정보 | 빈 문자열 |
| | `{{choir_song_lyrics_1}}`, `{{choir_song_lyrics_2}}` | 찬양 가사 1~2행 | 빈 문자열 |
| | `{{worship_scripture}}` / `{{성경본문}}` | 성서읽기 구절 | 빈 문자열 |
| | `{{responsive_scripture_ref}}` | 함께 읽는 말씀 성경 장/절 | 빈 문자열 |
| | `{{responsive_scripture_1~3}}` | 함께 읽는 시편 교독 본문 1~3행 | 빈 문자열 |
| | `{{worship_gospel}}` / `{{복음서읽기}}` | 복음서 본문 구절 | 빈 문자열 |
| | `{{worship_sermon_title}}` / `{{설교제목}}` | 하늘뜻펴기(설교) 제목 | 빈 문자열 |
| | `{{worship_preacher}}` / `{{설교자}}` | 설교자 이름 | 빈 문자열 |
| | `{{worship_offering_hymn}}` / `{{봉헌찬송}}` | 봉헌 찬송가 | 빈 문자열 |
| | `{{worship_benediction}}` / `{{축복기도}}` | 축도자 이름 | 담임목사 |
| **예배위원 (3면 상단)** | `{{duty_w1_date}}` ~ `{{duty_w3_date}}` | 1~3주차 예배 날짜 (08/16 등) | 빈 문자열 |
| | `{{duty_w1_presider}}` ~ `{{duty_w3_presider}}` | 1~3주차 인도자 명단 | 빈 문자열 |
| | `{{duty_w1_pastoral_prayer}}` ~ `...` | 1~3주차 목회기도 담당자 | 빈 문자열 |
| | `{{duty_w1_scripture_reader}}` ~ `...` | 1~3주차 성서읽기 담당자 | 빈 문자열 |
| | `{{duty_w1_preacher}}` ~ `...` | 1~3주차 하늘뜻펴기(설교자) | 빈 문자열 |
| | `{{duty_w1_thanks_prayer}}` ~ `...` | 1~3주차 감사기도 담당자 | 빈 문자열 |
| **감사헌금 (3면)** | `{{thanksgiving_donors}}` / `{{감사헌금}}` | 십일조/감사/목적 헌금자 명단 | 빈 문자열 |
| **교회 소식 (3면)** | `{{ad1_title}}` ~ `{{ad15_title}}` | 광고 1~15번 제목 | **공백 자동 소거** |
| | `{{ad1_content}}` ~ `{{ad15_content}}` | 광고 1~15번 상세 내용 | **공백 자동 소거** |
| **기도 나눔 (4면)** | `{{healing_prayer_1~3}}` | 건강 회복을 위한 교우 명단 1~3행 | 빈 문자열 |
| | `{{military_prayer_names}}` | 군 복무 중인 청년 교우 명단 | 빈 문자열 |
| | `{{overseas_prayer_1~2}}` | 해외 체류 중인 교우 명단 1~2행 | 빈 문자열 |

> [!TIP]
> **자동 슬롯 소거 기능**: 광고나 기도 제목 항목이 적은 주간이라도 템플릿에 배치된 미사용 태그는 **빈 문자열로 깨끗하게 자동 삭제**되어 표와 서식의 무결성을 완벽하게 유지합니다.

---

## 🏛️ 5. 문서 및 AI 설정의 SSOT

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

## 📊 6. 도구별 종합 채점 및 적합도 순위 (10점 만점)

| 순위 | 도구 및 방식 | 서식 재현도 (장평/표) | 윈도우/컬러인쇄 적합성 | 비용 (무료 여부) | **최종 평점** | 종합 평가 |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| **1위 🏆** | **HWPX XML 템플릿 치환 (Python)** | **10.0 / 10** | **10.0 / 10** | **무료 (10/10)** | **9.9 / 10** | **기존 HWP 양식을 100% 그대로 쓰면서 1초 만에 완성하는 압도적 1위** |
| **2위 🥇** | **Typst (팁스트 오픈소스 조판)** | **9.5 / 10** | **10.0 / 10** | **무료 (10/10)** | **9.6 / 10** | **0.05초 초고속 컬러 PDF 생성 + AI가 한글 장평/배분 함수 완벽 제공** |
| **3위 🥈** | **HTML/CSS 웹 조판 (Edge/Chrome)** | **9.0 / 10** | **9.5 / 10** | **무료 (10/10)** | **9.3 / 10** | **완전 무료 + 브라우저 컬러 인쇄 + 웹 주보 동시 발행 파이프라인** |

---

## 💻 7. 개발자 및 테스트 가이드

```bash
# 단위 테스트 실행
python3 -m unittest discover tests -v
```
