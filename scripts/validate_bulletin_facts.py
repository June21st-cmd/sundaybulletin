"""
향린교회 주보 팩트 및 임의 추정 원천 차단 검증기 (validate_bulletin_facts.py)

검증 영역:
1. 향린교회 정례 모임 골든 기준표(Golden DB) 대조
   - 목회운영위원회: 통상 16:00, 친교실(5층)
   - 교육부 월례회: 통상 12:40, 세미나실(4층)
   - 전체여신도회 임원모임: 통상 13:00, 담임목사실(4층)
2. 인접 항목 복붙 오염(Leaked Value) 감지
   - 윗줄 항목의 시간/장소와 완전히 동일한 값이 아랫줄에 연달아 나타날 때 경고
3. 원고 출처 격리 감사 (Source Leaking Audit)
   - 사용자가 제공한 원고 파일에 없는 모임/행사가 임의로 끼어들어갔는지 대조
"""

import datetime
import re
import sys
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser import (
    classify_announcement_section,
    extract_date_mentions,
    is_rule34_monthly_meeting_item,
    parse_bulletin_date,
    parse_explicit_date,
    validate_announcements_sections,
)

# 향린교회 주요 정례 모임 표준 기준표 (2026 골든 레퍼런스 기준)
GOLDEN_MEETING_RULES = {
    "목회운영위원회": {
        "expected_time": "16:00",
        "expected_place": "친교실(5층)",
        "warning": "목회운영위원회는 2026년 기준 통상 16:00, 친교실(5층)에서 열립니다."
    },
    "정기 목회운영위원회": {
        "expected_time": "16:00",
        "expected_place": "친교실(5층)",
        "warning": "정기 목회운영위원회는 2026년 기준 통상 16:00, 친교실(5층)에서 열립니다."
    },
    "교육부 월례회": {
        "expected_time": "12:40",
        "expected_place": "세미나실(4층)",
        "warning": "교육부 월례회는 통상 12:40, 세미나실(4층)에서 열립니다."
    },
    "전체여신도회 임원 모임": {
        "expected_time": "13:00",
        "expected_place": "담임목사실(4층)",
        "warning": "전체여신도회 임원 모임은 통상 13:00, 담임목사실(4층)에서 열립니다."
    },
    "전체여신도회 임원모임": {
        "expected_time": "13:00",
        "expected_place": "담임목사실(4층)",
        "warning": "전체여신도회 임원 모임은 통상 13:00, 담임목사실(4층)에서 열립니다."
    }
}

ECUMENICAL_KEYWORDS = [
    "노회", "시찰", "종로시찰",
    "NCCK", "한국기독교교회협의회", "한국그리스도교", "신앙과직제", "일치포럼",
    "공동행동", "촛불교회", "민중법정",
    "길목인의 날", "향린공동체협의회",
    "이웃 종교인", "이웃종교인", "종교 대화"
]

INTERNAL_HOST_PATTERN = re.compile(
    r"(?:향린교회|(?:관리|봉사|사회|선교|성평등|예배|친교|재정|교육)부|"
    r"(?:새청|청신|희청|청녀|청남|희녀|희남|장녀|장남)(?:신도회)?)\s*(?:주관|주최)"
    r"|(?:주관|주최)\s*[:：]\s*(?:향린교회|(?:관리|봉사|사회|선교|성평등|예배|친교|재정|교육)부|"
    r"(?:새청|청신|희청|청녀|청남|희녀|희남|장녀|장남)(?:신도회)?)"
)


def _parse_bulletin_date(data: dict, fallback_stem: str = "") -> datetime.date | None:
    return parse_bulletin_date(data, fallback_stem)


def _date_matches_role(d: datetime.date, role: str, pub_sunday: datetime.date) -> bool:
    if role == "today":
        return d == pub_sunday
    if role == "this_week":
        return (pub_sunday + datetime.timedelta(days=1)) <= d <= (pub_sunday + datetime.timedelta(days=7))
    if role == "future":
        return d >= (pub_sunday + datetime.timedelta(days=8))
    return True


def _expected_section_label(d: datetime.date, pub_sunday: datetime.date) -> str:
    if d < pub_sunday:
        return "과거 일정(게재 불가)"
    if d == pub_sunday:
        return "오늘 일정 안내(D)"
    if d <= pub_sunday + datetime.timedelta(days=7):
        return "이번주 일정 안내(D+1~D+7)"
    return "이후 일정 안내(D+8 이후)"


def _is_ambiguous_ecumenical_overlap(
    title: str, content: str, title_kws: list[str], content_kws: list[str]
) -> tuple[bool, str]:
    """Distinguish confirmed external/ecumenical events from genuinely ambiguous internal-host/external-venue cases."""
    if title_kws:
        return False, ""

    # 외부 기관이 직접 주관/주최하는 경우는 확실한 외부 행사
    for kw in content_kws:
        if re.search(rf"{re.escape(kw)}[^,.;\n]{{0,12}}(?:주관|주최)", content) or re.search(
            rf"(?:주관|주최)\s*[:：]?\s*{re.escape(kw)}", content
        ):
            return False, ""

    combined = f"{title} {content}"
    if INTERNAL_HOST_PATTERN.search(combined):
        return True, "교회 내부 부서/주체 주관 표기와 외부 연대 키워드가 함께 기재되어 있습니다."

    for kw in content_kws:
        if re.search(
            rf"(?:장소\s*[:：]\s*[^,.\n]*{re.escape(kw)}|{re.escape(kw)}\s*(?:회관|빌딩|건물|센터)|"
            rf"{re.escape(kw)}\s*(?:참관|참석|파송)?\s*(?:보고|나눔))",
            content,
        ):
            return True, "외부 기관 장소/보고 언급과 내부 일정이 혼재되어 있습니다."

    return False, ""


def validate_bulletin_facts_data(
    data,
    raw_text: str = "",
    fallback_stem: str = "",
    check_online_scripture: bool = False,
):
    """Validate structure, classification, date boundaries, golden meetings, and Rule 34 on in-memory data."""
    issues = []

    if not isinstance(data, dict):
        return [{
            "level": "ERROR",
            "category": "입력 형식 오류",
            "section": "root",
            "item": "",
            "content": "",
            "message": "주보 데이터 루트는 딕셔너리(dict) 형식이어야 합니다.",
        }]

    bulletin_date = _parse_bulletin_date(data, fallback_stem)

    # [S] 6대/7대 공동관심사 구조 및 legacy announcements 검증
    if "announcements" in data:
        issues.append({
            "level": "ERROR",
            "category": "지원되지 않는 레거시 소식 구조 (Rule 22)",
            "section": "announcements",
            "item": "",
            "content": "",
            "message": "레거시 'announcements' 단일 목록 입력은 6대/7대 공동관심사 분류·범주 검증을 보장할 수 없으므로 지원되지 않습니다. 'announcements_sections'(6대/7대 체계)를 사용하세요.",
        })

    if "announcements_sections" in data:
        try:
            validate_announcements_sections(data["announcements_sections"])
        except ValueError as exc:
            issues.append({
                "level": "ERROR",
                "category": "공동관심사 소주제 구조 위반 (Rule 22)",
                "section": "announcements_sections",
                "item": "",
                "content": "",
                "message": str(exc),
            })

    # 1. announcements_sections 및(존재 시) legacy announcements 항목 순회 검증
    raw_sections = data.get("announcements_sections", [])
    sections_to_inspect = [s for s in raw_sections if isinstance(s, dict)] if isinstance(raw_sections, list) else []
    if isinstance(data.get("announcements"), list) and data["announcements"]:
        sections_to_inspect = list(sections_to_inspect) + [
            {"title": "legacy:announcements", "items": data["announcements"], "_is_legacy": True}
        ]
    all_items = []

    for sec in sections_to_inspect:
        sec_title = str(sec.get("title", ""))
        sec_role = None if sec.get("_is_legacy") else classify_announcement_section(sec_title)
        items = sec.get("items", [])
        if not isinstance(items, list):
            continue

        # 이번주 일정 안내 헤더의 date_range(존재 시) D+1~D+7 정합성 검증
        if sec_role == "this_week" and bulletin_date and isinstance(sec.get("date_range"), str) and sec["date_range"].strip():
            dr_mentions = extract_date_mentions(sec["date_range"], bulletin_date)
            dr_confirmed = [
                m.resolved_date
                for m in dr_mentions
                if m.status == "confirmed" and not m.is_historical_ref and m.resolved_date is not None
            ]
            if any(m.status == "invalid" for m in dr_mentions):
                issues.append({
                    "level": "ERROR",
                    "category": "주간 일정 분류 오류 (Rule 22)",
                    "section": sec_title,
                    "item": "date_range",
                    "content": sec["date_range"],
                    "message": f"'{sec_title}'의 주간 범위({sec['date_range']})에 유효하지 않은 날짜가 포함되어 있습니다.",
                })
            elif len(dr_confirmed) == 2:
                exp_start = bulletin_date + datetime.timedelta(days=1)
                exp_end = bulletin_date + datetime.timedelta(days=7)
                if dr_confirmed[0] != exp_start or dr_confirmed[1] != exp_end:
                    issues.append({
                        "level": "ERROR",
                        "category": "주간 일정 분류 오류 (Rule 22)",
                        "section": sec_title,
                        "item": "date_range",
                        "content": sec["date_range"],
                        "message": f"'{sec_title}'의 주간 범위({sec['date_range']})가 발행 주일({bulletin_date}) 기준 D+1~D+7({exp_start.month}/{exp_start.day}~{exp_end.month}/{exp_end.day})과 일치하지 않습니다.",
                    })

        prev_time = None
        prev_place = None
        prev_title = None
        
        for item in items:
            if isinstance(item, dict):
                title = str(item.get("title", "")).strip()
                content = str(item.get("content", "")).strip()
                explicit_item_date = item.get("date")
            elif isinstance(item, str):
                title = ""
                content = item.strip()
                explicit_item_date = None
            else:
                continue
            all_items.append((sec_role, sec_title, title, content))
            
            # [E] 에큐메니칼 소식 비허용 섹션 침범 및 포괄 예외 검증 (Rule 22)
            ecumenical_blocked = False
            if sec_role != "ecumenical":
                title_kws = [kw for kw in ECUMENICAL_KEYWORDS if kw in title]
                content_kws = [kw for kw in ECUMENICAL_KEYWORDS if kw in content]
                if title_kws or content_kws:
                    is_amb, amb_reason = _is_ambiguous_ecumenical_overlap(title, content, title_kws, content_kws)
                    if is_amb:
                        issues.append({
                            "level": "WARNING",
                            "category": "에큐메니칼 분류 확인 요망 (Rule 22)",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": f"'{title or content}' 항목에 {amb_reason} 임의로 자동 이동하지 않으니 원고 근거에 따라 내부 일정 유지 또는 '에큐메니칼 소식' 배치 여부를 확인하세요.",
                        })
                    else:
                        ecumenical_blocked = True
                        issues.append({
                            "level": "ERROR",
                            "category": "에큐메니칼 소식 오분류 (Rule 22)",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": f"'{title or content}'은(는) 에큐메니칼/외부 연대 소식입니다! 당일/주간 여부와 무관하게 반드시 '에큐메니칼 소식' 코너에만 배치되어야 하며, '{sec_title}'에 들어갈 수 없습니다.",
                        })

            # [F] 발행 주일(D) 기준 내부 일정 날짜 분류 검증 (오늘=D, 이번주=D+1..D+7, 이후>=D+8)
            # 에큐메니칼·함께 만드는 향린·교우 소식·감사헌금 등 성격 우선 범주는 날짜 이동 대상에서 제외
            if not ecumenical_blocked and bulletin_date and sec_role in ("today", "this_week", "future"):
                combined_text = f"{title} {content}".strip()
                date_matches: list[tuple[int, int, datetime.date]] = []

                if isinstance(explicit_item_date, str) and explicit_item_date.strip():
                    parsed_exp = parse_explicit_date(explicit_item_date.strip())
                    if parsed_exp is None:
                        issues.append({
                            "level": "ERROR",
                            "category": "주간 일정 분류 오류 (Rule 22)",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": (
                                f"'{title or content}' 항목의 명시적 date 값('{explicit_item_date}')을 "
                                "4자리 연도가 포함된 유효한 날짜(YYYY-MM-DD)로 해석할 수 없습니다."
                            ),
                        })
                    else:
                        date_matches = [(0, len(explicit_item_date), parsed_exp)]
                else:
                    mentions = extract_date_mentions(combined_text, bulletin_date)
                    for m in mentions:
                        if m.status == "invalid":
                            issues.append({
                                "level": "ERROR",
                                "category": "주간 일정 분류 오류 (Rule 22)",
                                "section": sec_title,
                                "item": title,
                                "content": content,
                                "message": m.reason or f"'{title or content}'에 유효하지 않은 날짜('{m.raw}')가 포함되어 있습니다.",
                            })
                        elif m.status in ("unconfirmed", "ambiguous_token"):
                            issues.append({
                                "level": "WARNING",
                                "category": "일정 날짜 확인 요망 (Rule 22)",
                                "section": sec_title,
                                "item": title,
                                "content": content,
                                "message": m.reason,
                            })
                        elif m.status == "confirmed" and not m.is_historical_ref and m.resolved_date is not None:
                            date_matches.append((m.start, m.end, m.resolved_date))

                    has_historical_only = (
                        not date_matches
                        and any(m.is_historical_ref for m in mentions)
                        and not (
                            sec_role == "today"
                            and any(tok in combined_text for tok in ("오늘", "공동식사 후", "예배 후"))
                        )
                    )
                    if has_historical_only:
                        issues.append({
                            "level": "WARNING",
                            "category": "일정 날짜 확인 요망 (Rule 22)",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": (
                                f"'{title or content}' 항목에 과거 연도('작년' 등) 참조 날짜만 있고 확정된 행사 일정이 없습니다. "
                                "실제 행사 일정이라면 날짜 또는 항목의 명시적 ISO date(YYYY-MM-DD)를 확인하세요."
                            ),
                        })

                if date_matches:
                    is_explicit_range = (
                        len(date_matches) == 2
                        and date_matches[0][2] <= date_matches[1][2]
                        and bool(re.match(r"^\s*[~\-∼〜]\s*$", combined_text[date_matches[0][1]:date_matches[1][0]]))
                    )
                    if is_explicit_range:
                        d_start, d_end = date_matches[0][2], date_matches[1][2]
                        if sec_role == "today":
                            valid_window = d_start <= bulletin_date <= d_end
                        elif sec_role == "this_week":
                            valid_window = (
                                bulletin_date + datetime.timedelta(days=1)
                                <= d_start
                                <= bulletin_date + datetime.timedelta(days=7)
                            )
                        else:
                            valid_window = d_start >= bulletin_date + datetime.timedelta(days=8)
                        offending_date = d_start
                    else:
                        valid_window = any(_date_matches_role(d, sec_role, bulletin_date) for _, _, d in date_matches)
                        offending_date = date_matches[0][2]

                    if not valid_window:
                        exp_label = _expected_section_label(offending_date, bulletin_date)
                        issues.append({
                            "level": "ERROR",
                            "category": "주간 일정 분류 오류 (Rule 22)",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": (
                                f"발행 주일({bulletin_date}) 기준 '{title or content}'의 확정 일정({offending_date})은 "
                                f"'{exp_label}' 범주에 해당하므로 '{sec_title}'에 배치할 수 없습니다."
                            ),
                        })

            # [A] 골든 미팅 기준표 검증
            for meeting_key, rule in GOLDEN_MEETING_RULES.items():
                if meeting_key in title:
                    exp_time = rule["expected_time"]
                    exp_place = rule["expected_place"]
                    
                    if exp_time not in content:
                        issues.append({
                            "level": "ERROR",
                            "category": "정례 모임 시간 불일치",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": f"'{title}'의 시간이 표준({exp_time})과 다릅니다! {rule['warning']}"
                        })
                    if exp_place not in content:
                        place_match = re.search(r'([가-힣]+실\([0-9]+층\)|\([0-9]+층\)|[가-힣]+실)', content)
                        if place_match:
                            issues.append({
                                "level": "ERROR",
                                "category": "정례 모임 장소 불일치",
                                "section": sec_title,
                                "item": title,
                                "content": content,
                                "message": f"'{title}'의 장소({place_match.group(0)})가 표준 장소({exp_place})와 다릅니다!"
                            })
                        else:
                            issues.append({
                                "level": "WARNING",
                                "category": "정례 모임 장소 누락",
                                "section": sec_title,
                                "item": title,
                                "content": content,
                                "message": f"'{title}'에 표준 장소({exp_place})가 명시되지 않았습니다."
                            })

            # [B] 인접 항목 복붙 오염 검증
            # 시간 추출 (HH:MM)
            time_match = re.search(r'\b\d{1,2}:\d{2}\b', content)
            curr_time = time_match.group(0) if time_match else None
            
            # 장소 추출 (...층, ...실)
            place_match = re.search(r'([가-힣]+실\([0-9]+층\)|\([0-9]+층\))', content)
            curr_place = place_match.group(0) if place_match else None
            
            if prev_time and curr_time and prev_time == curr_time and prev_title:
                # 같은 시간에 연속된 회의가 열리는지 확인 경고
                issues.append({
                    "level": "INFO",
                    "category": "인접 항목 동일 시간 감지 (복붙 확인 요망)",
                    "section": sec_title,
                    "item": title,
                    "content": content,
                    "message": f"윗 항목('{prev_title}')과 시간이 동일하게 '{curr_time}'입니다. 단순 복사 실수가 아닌지 확인하세요."
                })
                
            prev_time = curr_time
            prev_place = curr_place
            prev_title = title

            # [C] 원고 텍스트 대비 임의 추가(환각) 감사
            if raw_text and title:
                clean_title = re.sub(r'[^가-힣a-zA-Z0-9]', '', title)
                clean_raw_text = re.sub(r'[^가-힣a-zA-Z0-9]', '', raw_text)
                # 중요한 모임명인데 원고에 전혀 언급이 없는 경우
                if len(clean_title) >= 3 and clean_title not in clean_raw_text:
                    # 성서일과, 월례회, 고정 광고는 제외
                    if not any(k in title for k in ["성서일과", "신학공부", "우리가락", "국악학교", "심방", "생활실천", "월례회"]):
                        issues.append({
                            "level": "WARNING",
                            "category": "원고 미언급 항목 (외부자료 임의 추가 의심)",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": f"'{title}'은(는) 사용자가 전달한 원고 텍스트에 없습니다. 외부 회의자료에서 임의로 추가된 것이 아닌지 반드시 확인하세요."
                        })

    # [D] Rule 34: 매월 1주(부서 월례회), 2주(신도회 월례회) 필수 포함 검증
    target_date_str = bulletin_date.isoformat() if bulletin_date else None
    if bulletin_date is not None:
        day = bulletin_date.day
        today_raw_items = [
            it
            for sec in sections_to_inspect
            if not sec.get("_is_legacy") and classify_announcement_section(str(sec.get("title", ""))) == "today"
            for it in (sec.get("items", []) if isinstance(sec.get("items"), list) else [])
        ]

        if day <= 7:
            # 매월 첫째 주: 부서 월례회 필수 (관련 단어만 포함된 다른 공지는 충족으로 인정하지 않음)
            has_dept_meeting = any(is_rule34_monthly_meeting_item(it, "부서 월례회") for it in today_raw_items)
            if not has_dept_meeting:
                issues.append({
                    "level": "ERROR",
                    "category": "매월 1주 정례 모임 누락 (Rule 34)",
                    "section": "1. 오늘 일정 안내",
                    "item": "부서 월례회",
                    "content": "",
                    "message": "매월 첫째 주는 '부서 월례회: 공동식사 후, 각 부서 공간' 및 8개 부서 공간 안내 박스가 필수입니다! 원고 메모에 없더라도 절대 생략할 수 없습니다."
                })
        elif 8 <= day <= 14:
            # 매월 둘째 주: 신도회 월례회 필수 (관련 단어만 포함된 다른 공지는 충족으로 인정하지 않음)
            has_fellowship_meeting = any(is_rule34_monthly_meeting_item(it, "신도회 월례회") for it in today_raw_items)
            if not has_fellowship_meeting:
                issues.append({
                    "level": "ERROR",
                    "category": "매월 2주 정례 모임 누락 (Rule 34)",
                    "section": "1. 오늘 일정 안내",
                    "item": "신도회 월례회",
                    "content": "",
                    "message": "매월 둘째 주는 '신도회 월례회: 공동식사 후, 각 신도회 모임 공간' 및 9개 신도회 공간 안내 박스가 필수입니다! 원고 메모에 없더라도 절대 생략할 수 없습니다."
                })

    # 4. 홈페이지 공식 성서읽기(board_hVTK46) 원문 1:1 대조 검증 (제작 세션 경계 전용 온라인 출처 검증)
    meta_dict = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
    skip_online = bool(meta_dict.get("skip_scripture_verification") or data.get("skip_scripture_verification"))
    if check_online_scripture and not skip_online:
        worship_dict = data.get("worship_1", data.get("worship", {}))
        if not isinstance(worship_dict, dict):
            worship_dict = {}
        resp_lines = []
        for k in ["responsive_scripture_1", "responsive_scripture_2", "responsive_scripture_3", "responsive_scripture_4"]:
            v = str(worship_dict.get(k, "")).strip()
            if v:
                resp_lines.append(v)
        if not resp_lines and worship_dict.get("responsive_scripture"):
            rs = worship_dict.get("responsive_scripture")
            if isinstance(rs, list):
                resp_lines = [str(x).strip() for x in rs if str(x).strip()]
            elif isinstance(rs, str):
                resp_lines = [l.strip() for l in rs.split("\n") if l.strip()]

        if resp_lines and target_date_str:
            try:
                try:
                    from scripts.fetch_sunday_scripture import fetch_post_url, fetch_scripture_content, parse_scriptures
                except ImportError:
                    from fetch_sunday_scripture import fetch_post_url, fetch_scripture_content, parse_scriptures
                post_url = fetch_post_url(target_date_str)
                if post_url:
                    raw_scripture = fetch_scripture_content(post_url)
                    if raw_scripture:
                        # 성서읽기 게시판의 모든 텍스트 정규화
                        clean_official = re.sub(r'\s+', ' ', raw_scripture)
                        # YAML의 함께읽는말씀 본문 검증
                        for idx, line in enumerate(resp_lines, 1):
                            # 숫자 및 특수문자 정돈 후 핵심 어구 대조
                            core_text = re.sub(r'^\d+\s*', '', line).strip()
                            # 최소 10글자 이상인 핵심 구절 추출하여 대조
                            tokens = [t for t in core_text.split() if len(t) >= 2]
                            match_count = sum(1 for t in tokens if t in clean_official)
                            ratio = match_count / max(1, len(tokens))
                            if ratio < 0.6: # 공식 본문 단어 일치율 60% 미만이면 AI 임의 작문/타 번역본으로 차단
                                issues.append({
                                    "level": "ERROR",
                                    "category": "성서 본문 출처 위반 및 임의 작문 감지 (Rule 0)",
                                    "section": "2면 함께읽는말씀",
                                    "item": f"본문 {idx}행",
                                    "content": line,
                                    "message": f"함께읽는말씀 본문이 교회 홈페이지 공식 성서읽기(URL: {post_url}) 본문과 일치율({ratio:.1%}) 미달로 불일치합니다! AI 자체 파라미터 기억에 의한 자의적 작문 또는 비공식 번역본 인용은 엄격히 차단됩니다."
                                })
            except Exception:
                # 오프라인이거나 네트워크 단절 시는 검증 건너뜀 (단위테스트 fallback)
                pass

        # 7. 교독송 4글자 하이픈 오적용 검증 (Rule 18)
        worship = data.get("worship_1", data.get("worship", {}))
        rh = worship.get("responsive_hymn", {}) if isinstance(worship, dict) else {}
        if rh and isinstance(rh, dict):
            for k, v in rh.items():
                if isinstance(v, str) and v:
                    # 1) 4글자 이상 단어 내 하이픈 삽입 감지 (예: 하-나님은 등)
                    for m in re.finditer(r'([가-힣]{1,3})-([가-힣]{1,3})', v):
                        word_no_hyphen = m.group(1) + m.group(2)
                        if len(word_no_hyphen) >= 4:
                            issues.append({
                                "level": "ERROR",
                                "category": "교독송 4글자 구절 하이픈 오적용 (Rule 18)",
                                "section": "2면 교독송",
                                "item": k,
                                "content": v,
                                "message": f"교독송 '{v}' 중 '{m.group(0)}'는 이미 {len(word_no_hyphen)}글자(음절)이므로 하이픈(-)을 넣을 수 없습니다. 4박자(4음보) 체계에서 4음절은 하이픈 없이 표기해야 합니다."
                            })
                    # 2) 4글자 이상 단어 뒤 행 끝단 하이픈 삽입 감지 (예: 크시도다 -, 모든자들 -, 불쌍하니 -)
                    for m in re.finditer(r'([가-힣]{4,})\s*-\s*$', v):
                        issues.append({
                            "level": "ERROR",
                            "category": "교독송 4글자 구절 하이픈 오적용 (Rule 18)",
                            "section": "2면 교독송",
                            "item": k,
                            "content": v,
                            "message": f"교독송 '{v}'의 '{m.group(1)}'는 이미 {len(m.group(1))}글자이므로 뒤에 하이픈(-)을 덧붙일 수 없습니다. 원고에 없는 임의 하이픈 부가는 금지됩니다."
                        })

    return issues


def validate_facts(bulletin_yaml_path, raw_input_path=None):
    """CLI-compatible file wrapper delegating to validate_bulletin_facts_data."""
    yaml_file = Path(bulletin_yaml_path)
    if not yaml_file.exists():
        return [{
            "level": "ERROR",
            "category": "입력 파일 누락",
            "section": "root",
            "item": "",
            "content": "",
            "message": f"YAML 파일을 찾을 수 없습니다: {bulletin_yaml_path}",
        }]

    with open(yaml_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    raw_text = ""
    if raw_input_path and Path(raw_input_path).exists():
        with open(raw_input_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

    return validate_bulletin_facts_data(
        data,
        raw_text=raw_text,
        fallback_stem=yaml_file.stem,
        check_online_scripture=True,
    )

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "data/inputs/bulletin_20260920.yaml"
    raw_path = sys.argv[2] if len(sys.argv) > 2 else "data/inputs/2026-09-20_주보원고.md"
    
    print(f"=== 주보 팩트 및 임의 추정 검증 시작 ===")
    print(f"대상 파일: {yaml_path}")
    if raw_path:
        print(f"원고 파일: {raw_path}")
    print("-" * 50)
    
    results = validate_facts(yaml_path, raw_path)
    
    if not results:
        print("🟢 [검증 통과] 팩트 불일치나 임의 추정 항목이 발견되지 않았습니다.")
        sys.exit(0)
        
    error_cnt = sum(1 for r in results if r["level"] == "ERROR")
    warn_cnt = sum(1 for r in results if r["level"] == "WARNING")
    info_cnt = sum(1 for r in results if r["level"] == "INFO")
    
    print(f"발견된 문제: ERROR {error_cnt}건, WARNING {warn_cnt}건, INFO {info_cnt}건\n")
    
    for r in results:
        icon = "🔴" if r["level"] == "ERROR" else ("🟠" if r["level"] == "WARNING" else "ℹ️")
        print(f"{icon} [{r['level']}] [{r['category']}] {r['section']} > {r['item']}")
        print(f"   내용: {r['content']}")
        print(f"   지침: {r['message']}")
        print()
        
    if error_cnt > 0:
        sys.exit(1)
    sys.exit(0)
