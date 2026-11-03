"""Parser and validator for weekly bulletin input data (YAML/JSON/Raw Text)."""
import copy
from dataclasses import dataclass
import datetime
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import yaml


@dataclass(frozen=True)
class DateMention:
    """Unified date extraction and year-resolution result shared across preflight and reviewer."""
    raw: str
    start: int
    end: int
    month: int
    day: int
    written_weekday: Optional[str]
    status: str  # "confirmed" | "unconfirmed" | "ambiguous_token" | "invalid"
    resolved_date: Optional[datetime.date] = None
    is_historical_ref: bool = False
    year_source: str = ""
    reason: str = ""


_COST_RATIO_BEFORE_RE = re.compile(
    r"(?:참가비|회비|등록비|수강료|교육비|식비|교통비|숙박비|간식비|자료비|비용|경비|금액|요금|자부담|부담금|"
    r"비율|비중|정족수|재적|출석|찬성|동의|과반|정원)(?:[은는이가의을를]\s*|\s*[:：]?\s*)$"
)

_COST_RATIO_AFTER_RE = re.compile(
    r"^\s*(?:분기|층|호|편|장|절|쪽|권|부|명|인|개|회|차|기)(?![가-힣])"
    r"|^\s*(?:[을를이가의은는]|까지|만|씩)?\s*(?:지원|보조|부담|감면|할인|면제|환불|납부|지급|찬성|동의|출석|참석|이상|이하|미만|초과|가량|정도)"
)

_POSITIVE_SLASH_DATE_BEFORE_RE = re.compile(
    r"(?:(?:일시|날짜|일정|기간|기한|마감)\s*[:：]?|"
    r"(?:20\d{2}\s*(?:년|[./\-])|작년|지난해|전년도|올해|금년|당해|내년|다음\s*해|명년))\s*$"
)

_POSITIVE_SLASH_RANGE_BEFORE_RE = re.compile(
    r"\d{1,2}/\d{1,2}(?:\s*\((?:[월화수목금토일]|주일)\))?\s*[~\-∼〜]\s*$"
)

_POSITIVE_SLASH_DATE_AFTER_RE = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}|(?:오전|오후|낮|밤|저녁|새벽)\s*\d{1,2}\s*시|"
    r"\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?(?![가-힣])|"
    r"[~\-∼〜]\s*\d{1,2}/\d{1,2})"
)


def parse_explicit_date(raw: Any) -> Optional[datetime.date]:
    """Parse a date string only when an explicit 4-digit year (20XX) is present and valid."""
    if not raw:
        return None
    s = str(raw).strip()
    m_kor = re.search(r"(?<!\d)(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일(?!\d)", s)
    if m_kor:
        try:
            return datetime.date(int(m_kor.group(1)), int(m_kor.group(2)), int(m_kor.group(3)))
        except ValueError:
            return None
    m_iso = re.search(r"(?<!\d)(20\d{2})(?:[-./](\d{1,2})[-./](\d{1,2})|(\d{2})(\d{2}))(?!\d)", s)
    if m_iso:
        yr = int(m_iso.group(1))
        mo = int(m_iso.group(2) or m_iso.group(4))
        da = int(m_iso.group(3) or m_iso.group(5))
        try:
            return datetime.date(yr, mo, da)
        except ValueError:
            return None
    return None


def _resolve_mention_year(
    raw: str,
    start: int,
    end: int,
    month: int,
    day: int,
    raw_weekday: Optional[str],
    explicit_year: Optional[int],
    clause_prefix: str,
    ref_date: Optional[datetime.date],
    explicit_iso_date: Optional[datetime.date],
) -> DateMention:
    norm_w = ("일" if raw_weekday == "주일" else raw_weekday) if raw_weekday else None

    if not (1 <= month <= 12 and 1 <= day <= 31):
        return DateMention(
            raw=raw,
            start=start,
            end=end,
            month=month,
            day=day,
            written_weekday=norm_w,
            status="invalid",
            reason=f"달력에 존재하지 않는 날짜입니다: {month}월 {day}일",
        )
    try:
        # 2024 is a leap year; rejects impossible calendar days like 2/30, 4/31, 11/31
        datetime.date(2024, month, day)
    except ValueError:
        return DateMention(
            raw=raw,
            start=start,
            end=end,
            month=month,
            day=day,
            written_weekday=norm_w,
            status="invalid",
            reason=f"달력에 존재하지 않는 날짜입니다: {month}월 {day}일",
        )

    yr: Optional[int] = None
    year_source = ""
    is_historical_ref = False

    if explicit_year is not None:
        yr = explicit_year
        year_source = "explicit_year"
    else:
        y_prefix = re.search(r"(?<!\d)(20\d{2})\s*(?:년|[./\-])?\s*$", clause_prefix)
        if y_prefix:
            yr = int(y_prefix.group(1))
            year_source = "explicit_year"
        elif re.search(r"(?:작년|지난해|전년도)\s*$", clause_prefix):
            if ref_date is None:
                return DateMention(
                    raw=raw,
                    start=start,
                    end=end,
                    month=month,
                    day=day,
                    written_weekday=norm_w,
                    status="unconfirmed",
                    reason=f"기준 발행일이 없어 상대 연도 표현('{raw}')의 연도를 확정할 수 없습니다.",
                )
            yr = ref_date.year - 1
            year_source = "relative_past_year"
            is_historical_ref = True
        elif re.search(r"(?:올해|금년|당해)\s*$", clause_prefix):
            if ref_date is None:
                return DateMention(
                    raw=raw,
                    start=start,
                    end=end,
                    month=month,
                    day=day,
                    written_weekday=norm_w,
                    status="unconfirmed",
                    reason=f"기준 발행일이 없어 상대 연도 표현('{raw}')의 연도를 확정할 수 없습니다.",
                )
            yr = ref_date.year
            year_source = "relative_current_year"
        elif re.search(r"(?:내년|다음\s*해|명년)\s*$", clause_prefix):
            if ref_date is None:
                return DateMention(
                    raw=raw,
                    start=start,
                    end=end,
                    month=month,
                    day=day,
                    written_weekday=norm_w,
                    status="unconfirmed",
                    reason=f"기준 발행일이 없어 상대 연도 표현('{raw}')의 연도를 확정할 수 없습니다.",
                )
            yr = ref_date.year + 1
            year_source = "relative_next_year"
        elif explicit_iso_date is not None and (month, day) == (explicit_iso_date.month, explicit_iso_date.day):
            yr = explicit_iso_date.year
            year_source = "item_iso_date"
        elif re.search(r"(?:지난|지난달|전월)\s*$", clause_prefix):
            return DateMention(
                raw=raw,
                start=start,
                end=end,
                month=month,
                day=day,
                written_weekday=norm_w,
                status="unconfirmed",
                reason=f"과거 지시 문맥('{raw}')만으로는 연도를 안전하게 확정할 수 없습니다. 연도 또는 명시적 ISO date(YYYY-MM-DD)를 확인하세요.",
            )
        elif ref_date is not None:
            next_month = 1 if ref_date.month == 12 else ref_date.month + 1
            next_month_year = ref_date.year + 1 if ref_date.month == 12 else ref_date.year
            if month == ref_date.month and day >= ref_date.day:
                yr = ref_date.year
                year_source = "current_month"
            elif month == next_month:
                yr = next_month_year
                year_source = "adjacent_next_month"

    if yr is None:
        return DateMention(
            raw=raw,
            start=start,
            end=end,
            month=month,
            day=day,
            written_weekday=norm_w,
            status="unconfirmed",
            reason=f"연도 표기 없는 '{raw}'의 연도를 문맥만으로 확정할 수 없습니다. 연도 표기 또는 항목의 명시적 ISO date(YYYY-MM-DD)를 확인하세요.",
        )

    try:
        resolved = datetime.date(yr, month, day)
    except ValueError:
        return DateMention(
            raw=raw,
            start=start,
            end=end,
            month=month,
            day=day,
            written_weekday=norm_w,
            status="invalid",
            reason=f"달력에 존재하지 않는 날짜입니다: {yr}년 {month}월 {day}일",
        )

    return DateMention(
        raw=raw,
        start=start,
        end=end,
        month=month,
        day=day,
        written_weekday=norm_w,
        status="confirmed",
        resolved_date=resolved,
        is_historical_ref=is_historical_ref,
        year_source=year_source,
    )


def extract_date_mentions(
    text: str,
    ref_date: Optional[datetime.date] = None,
    explicit_iso_date: Optional[datetime.date] = None,
) -> List[DateMention]:
    """Extract date mentions with unified year resolution and cost/ratio disambiguation."""
    if not text:
        return []

    mentions: List[DateMention] = []
    occupied: List[tuple[int, int]] = []

    def is_overlapping(s: int, e: int) -> bool:
        return any(not (e <= os_ or s >= oe_) for os_, oe_ in occupied)

    def get_clause_prefix(pos: int) -> str:
        window = text[max(0, pos - 20):pos]
        return re.split(r"[,.;\n()\[\]]", window)[-1]

    # 1. Explicit 4-digit year dates: YYYY년 M월 D일, YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
    pat_full = re.compile(
        r"(?<!\d)(20\d{2})\s*(?:년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일|[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{1,2})\.?)"
        r"(?:\s*\(([월화수목금토일]|주일)\))?(?!\d)"
    )
    for m in pat_full.finditer(text):
        yr = int(m.group(1))
        mo = int(m.group(2) or m.group(4))
        da = int(m.group(3) or m.group(5))
        raw_w = m.group(6)
        occupied.append((m.start(), m.end()))
        mentions.append(
            _resolve_mention_year(
                raw=m.group(0),
                start=m.start(),
                end=m.end(),
                month=mo,
                day=da,
                raw_weekday=raw_w,
                explicit_year=yr,
                clause_prefix="",
                ref_date=ref_date,
                explicit_iso_date=explicit_iso_date,
            )
        )

    # 2. Korean M월 D일 without attached 4-digit year
    pat_kor = re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\(([월화수목금토일]|주일)\))?")
    for m in pat_kor.finditer(text):
        if is_overlapping(m.start(), m.end()):
            continue
        mo, da, raw_w = int(m.group(1)), int(m.group(2)), m.group(3)
        occupied.append((m.start(), m.end()))
        mentions.append(
            _resolve_mention_year(
                raw=m.group(0),
                start=m.start(),
                end=m.end(),
                month=mo,
                day=da,
                raw_weekday=raw_w,
                explicit_year=None,
                clause_prefix=get_clause_prefix(m.start()),
                ref_date=ref_date,
                explicit_iso_date=explicit_iso_date,
            )
        )

    # 3. Slash M/D(요일) or contextual M/D (separating cost/ratio expressions from schedule dates)
    pat_slash = re.compile(
        r"(?<![0-9/.\-])(\d{1,2})/(\d{1,2})(?:\s*\(([월화수목금토일]|주일)\))?(?![0-9/])"
    )
    for m in pat_slash.finditer(text):
        if is_overlapping(m.start(), m.end()):
            continue
        mo, da, raw_w = int(m.group(1)), int(m.group(2)), m.group(3)
        clause_before = get_clause_prefix(m.start())
        if raw_w is None:
            if not (1 <= mo <= 12 and 1 <= da <= 31):
                continue
            clause_after = re.split(r"[,.;\n()\[\]]", text[m.end():m.end() + 20])[0]
            if _COST_RATIO_BEFORE_RE.search(clause_before) or _COST_RATIO_AFTER_RE.search(clause_after):
                continue
            raw_before = text[max(0, m.start() - 24):m.start()]
            has_schedule_ctx = bool(
                _POSITIVE_SLASH_DATE_BEFORE_RE.search(clause_before)
                or _POSITIVE_SLASH_RANGE_BEFORE_RE.search(raw_before)
                or _POSITIVE_SLASH_DATE_AFTER_RE.search(clause_after)
            )
            occupied.append((m.start(), m.end()))
            if not has_schedule_ctx:
                mentions.append(
                    DateMention(
                        raw=m.group(0),
                        start=m.start(),
                        end=m.end(),
                        month=mo,
                        day=da,
                        written_weekday=None,
                        status="ambiguous_token",
                        reason=(
                            f"슬래시 표현 '{m.group(0)}'에 요일·시간·일시 근거가 부족하여 행사 날짜로 확정할 수 없습니다. "
                            "행사 일정이라면 요일(예: M/D(요일)) 또는 명시적 ISO date(YYYY-MM-DD)를 확인하세요."
                        ),
                    )
                )
                continue
        else:
            occupied.append((m.start(), m.end()))

        mentions.append(
            _resolve_mention_year(
                raw=m.group(0),
                start=m.start(),
                end=m.end(),
                month=mo,
                day=da,
                raw_weekday=raw_w,
                explicit_year=None,
                clause_prefix=clause_before,
                ref_date=ref_date,
                explicit_iso_date=explicit_iso_date,
            )
        )

    # 4. Dot M.D.(요일) (requires explicit parenthesized weekday to distinguish from decimals)
    pat_dot = re.compile(r"(?<![0-9/.\-])(\d{1,2})\.\s*(\d{1,2})\.?\s*\(([월화수목금토일]|주일)\)")
    for m in pat_dot.finditer(text):
        if is_overlapping(m.start(), m.end()):
            continue
        mo, da, raw_w = int(m.group(1)), int(m.group(2)), m.group(3)
        occupied.append((m.start(), m.end()))
        mentions.append(
            _resolve_mention_year(
                raw=m.group(0),
                start=m.start(),
                end=m.end(),
                month=mo,
                day=da,
                raw_weekday=raw_w,
                explicit_year=None,
                clause_prefix=get_clause_prefix(m.start()),
                ref_date=ref_date,
                explicit_iso_date=explicit_iso_date,
            )
        )

    mentions.sort(key=lambda x: x.start)
    return mentions


CANONICAL_SECTIONS_6 = (
    "1. 오늘 일정 안내",
    "2. 함께 만드는 향린",
    "3. 이번주 일정 안내",
    "4. 이후 일정 안내",
    "5. 에큐메니칼 소식",
    "6. 감사헌금",
)

CANONICAL_SECTIONS_7 = (
    "1. 오늘 일정 안내",
    "2. 교우 소식",
    "3. 함께 만드는 향린",
    "4. 이번주 일정 안내",
    "5. 이후 일정 안내",
    "6. 에큐메니칼 소식",
    "7. 감사헌금",
)

SECTION_ROLE_BY_BASE_TITLE = {
    "오늘 일정 안내": "today",
    "오늘 일정": "today",
    "교우 소식": "member_news",
    "함께 만드는 향린": "together",
    "이번주 일정 안내": "this_week",
    "이번주 일정": "this_week",
    "이후 일정 안내": "future",
    "이후 일정": "future",
    "에큐메니칼 소식": "ecumenical",
    "감사헌금": "offering",
}

ALLOWED_CANONICAL_BASE_TITLES = {
    "오늘 일정 안내",
    "교우 소식",
    "함께 만드는 향린",
    "이번주 일정 안내",
    "이후 일정 안내",
    "에큐메니칼 소식",
    "감사헌금",
}


def classify_announcement_section(title: str) -> Optional[str]:
    """Map an announcement section header title to its canonical semantic role."""
    if not isinstance(title, str):
        return None
    base = re.sub(r"^\d+[\.\)]\s*", "", title.strip())
    base = re.sub(r"\s+", " ", base).strip()
    return SECTION_ROLE_BY_BASE_TITLE.get(base)


def _validate_announcement_items(items: Any, context: str) -> None:
    """Validate that an announcement items collection is a list of valid str/dict entries."""
    if not isinstance(items, list):
        raise ValueError(f"{context}의 items는 리스트(list)여야 합니다.")

    for idx, item in enumerate(items, start=1):
        if isinstance(item, str):
            continue
        if isinstance(item, dict):
            if "title" not in item and "content" not in item:
                raise ValueError(f"{context} {idx}번째 항목에 'title' 또는 'content' 키가 필요합니다.")
            for key in ("title", "content", "date", "image"):
                if key in item and not isinstance(item[key], str):
                    raise ValueError(f"{context} {idx}번째 항목의 '{key}' 값은 문자열(str)이어야 합니다.")
            continue
        raise ValueError(
            f"{context} {idx}번째 항목 타입이 올바르지 않습니다({type(item).__name__}). dict 또는 str만 허용됩니다."
        )


def validate_announcements_sections(sections: Any) -> bool:
    """Validate 6-tier / 7-tier section names, order, sequential numbering, and item types."""
    if not isinstance(sections, list):
        raise ValueError("Invalid 'announcements_sections': 리스트(list) 형식이어야 합니다.")

    norm_titles = []
    for idx, sec in enumerate(sections, start=1):
        if not isinstance(sec, dict):
            raise ValueError(f"announcements_sections {idx}번째 요소는 딕셔너리(dict)여야 합니다.")
        raw_title = sec.get("title")
        if not isinstance(raw_title, str) or not raw_title.strip():
            raise ValueError(f"announcements_sections {idx}번째 섹션에 유효한 문자열 'title'이 없습니다.")
        if "date_range" in sec and not isinstance(sec["date_range"], str):
            raise ValueError(f"섹션 '{raw_title}'의 'date_range'는 문자열(str)이어야 합니다.")
        if "items" not in sec:
            raise ValueError(f"섹션 '{raw_title}'에 'items' 필드가 누락되었습니다.")
        _validate_announcement_items(sec["items"], f"섹션 '{raw_title}'")
        norm_titles.append(re.sub(r"\s+", " ", raw_title.strip()))

    titles_tuple = tuple(norm_titles)
    if titles_tuple in (CANONICAL_SECTIONS_6, CANONICAL_SECTIONS_7):
        return True

    base_titles = [re.sub(r"^\d+[\.\)]\s*", "", t) for t in norm_titles]
    for raw_t, base_t in zip(norm_titles, base_titles):
        if base_t not in ALLOWED_CANONICAL_BASE_TITLES:
            raise ValueError(
                f"허용되지 않는 공동관심사 소주제명이 포함되어 있습니다: '{raw_t}' (Rule 22 6대/7대 체계 위반)"
            )

    if "이후 일정 안내" not in base_titles:
        raise ValueError(
            "필수 소주제 '이후 일정 안내' 헤더가 누락되었습니다. 일정이 없더라도 빈 목록(items: [])으로 헤더를 유지해야 합니다 (Rule 22)."
        )

    for idx, raw_t in enumerate(norm_titles, start=1):
        if not raw_t.startswith(f"{idx}. "):
            raise ValueError(
                f"공동관심사 소주제 번호 불일치: {idx}번째 섹션이 '{raw_t}'입니다. 1번부터 순차 번호여야 합니다 (Rule 22)."
            )

    raise ValueError(
        f"공동관심사 소주제 순서·구성이 기존 6대/7대 체계와 일치하지 않습니다: {list(norm_titles)}"
    )


def parse_bulletin_date(data: Any, fallback_stem: str = "") -> Optional[datetime.date]:
    """Extract the publication Sunday date from bulletin metadata or filename stem."""
    if not isinstance(data, dict):
        return parse_explicit_date(fallback_stem)
    meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
    candidates = [
        meta.get("date_compact"),
        meta.get("date"),
        data.get("date"),
        meta.get("date_korean"),
        data.get("date_korean"),
        fallback_stem,
    ]
    for raw in candidates:
        parsed = parse_explicit_date(raw)
        if parsed is not None:
            return parsed
    return None


def parse_rule34_monthly_meeting_item(item: Any, meeting_title: str) -> tuple[str, str] | None:
    """Parse an announcement item iff its actual item title is `meeting_title` ('부서 월례회' or '신도회 월례회').

    Matches dict items whose title is `meeting_title` (ignoring whitespace/leading bullet) and
    string items of form `'부서 월례회: ...'` or `'부서 월례회'`.
    Does NOT match related-words-only notices such as `'부서 월례회 자료 안내'`.
    """
    target_compact = re.sub(r"\s+", "", meeting_title)
    if not target_compact:
        return None

    if isinstance(item, dict):
        raw_title = str(item.get("title", "")).strip()
        cleaned_title = re.sub(r"^[∙•\-*]\s*", "", raw_title).strip()
        if re.sub(r"\s+", "", cleaned_title) == target_compact:
            return meeting_title, str(item.get("content", "")).strip()
        return None

    if isinstance(item, str):
        cleaned = re.sub(r"^[∙•\-*]\s*", "", item.strip()).strip()
        if not cleaned:
            return None
        parts = re.split(r"\s*[:：]\s*", cleaned, maxsplit=1)
        if re.sub(r"\s+", "", parts[0]) == target_compact:
            tail = parts[1].strip() if len(parts) > 1 else ""
            return meeting_title, tail
        return None

    return None


def is_rule34_monthly_meeting_item(item: Any, meeting_title: str) -> bool:
    """Return True iff `item` represents an actual Rule 34 monthly meeting notice for `meeting_title`."""
    return parse_rule34_monthly_meeting_item(item, meeting_title) is not None


def prepare_bulletin_data(data: Any, fallback_stem: str = "") -> Any:
    """Return a deep-copied bulletin dict with permitted Rule 34 monthly meeting AUTO applied.

    Never mutates the caller's input object. Rule 34 AUTO inserts the mandatory 1st-week
    ('부서 월례회') or 2nd-week ('신도회 월례회') notice only when a valid 'today' section
    with a list 'items' exists and does not already contain the notice.
    String-formatted monthly meeting items (e.g. '부서 월례회: 공동식사 후, 각 부서 공간')
    are normalized on the deep copy so both the notice and its space-guide box render.
    """
    if not isinstance(data, dict):
        return data

    prepared = copy.deepcopy(data)
    bulletin_date = parse_bulletin_date(prepared, fallback_stem)
    if bulletin_date is None or bulletin_date.day > 14:
        return prepared

    ann_sections = prepared.get("announcements_sections")
    if not isinstance(ann_sections, list) or not ann_sections:
        return prepared

    today_sec = next(
        (
            sec
            for sec in ann_sections
            if isinstance(sec, dict) and classify_announcement_section(sec.get("title", "")) == "today"
        ),
        None,
    )
    if today_sec is None:
        return prepared

    items_list = today_sec.get("items")
    if not isinstance(items_list, list):
        return prepared

    item_texts = [
        f"{it.get('title', '')} {it.get('content', '')}".strip() if isinstance(it, dict) else str(it).strip()
        for it in items_list
    ]
    insert_idx = 1 if (item_texts and "제직회" in item_texts[0]) else 0

    if bulletin_date.day <= 7:
        target_title = "부서 월례회"
        default_content = "공동식사 후, 각 부서 공간"
    else:
        target_title = "신도회 월례회"
        default_content = "공동식사 후, 각 신도회 모임 공간"

    has_target_meeting = False
    for idx, it in enumerate(items_list):
        parsed_mm = parse_rule34_monthly_meeting_item(it, target_title)
        if parsed_mm is not None:
            has_target_meeting = True
            items_list[idx] = {
                "title": target_title,
                "content": parsed_mm[1] or default_content,
            }

    if not has_target_meeting:
        items_list.insert(
            insert_idx,
            {
                "title": target_title,
                "content": default_content,
            },
        )

    return prepared


def validate_bulletin_data(data: Dict[str, Any]) -> bool:
    """Validate structure of loaded bulletin data dictionary.
    
    Args:
        data: Parsed dictionary.
        
    Returns:
        True if valid.
        
    Raises:
        ValueError: If essential fields are missing or announcement schema is invalid.
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid bulletin data format: root must be a dictionary.")

    # Check metadata or date
    meta = data.get("metadata", {})
    if not meta and not data.get("date") and not data.get("date_korean"):
        raise ValueError("Bulletin data missing date/metadata information.")

    if "announcements" in data:
        _validate_announcement_items(data["announcements"], "legacy 'announcements'")
        if "announcements_sections" in data and data["announcements"]:
            raise ValueError(
                "레거시 'announcements'와 'announcements_sections'를 동시에 사용할 수 없습니다. 'announcements_sections'로 일원화하세요."
            )

    if "announcements_sections" in data:
        validate_announcements_sections(data["announcements_sections"])

    return True


def load_bulletin_data(file_path: Path | str, validate: bool = True) -> Dict[str, Any]:
    """Load and parse bulletin data from a YAML or JSON file.
    
    Args:
        file_path: Path to the input file.
        validate: Whether to run strict schema validation immediately on load.
        
    Returns:
        Dict containing structured bulletin data.
        
    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is unsupported or invalid.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    content = path.read_text(encoding="utf-8")
    
    if path.suffix.lower() in [".yaml", ".yml"]:
        data = yaml.safe_load(content)
    elif path.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}. Expected .yaml or .json")

    if not isinstance(data, dict):
        raise ValueError("Invalid bulletin data format: root must be a dictionary.")

    if validate:
        validate_bulletin_data(data)
    return data


def parse_raw_text_to_dict(raw_text: str) -> Dict[str, Any]:
    """Helper to parse unstructured raw memo text into bulletin data dictionary.
    
    Supports basic patterns like:
    설교: [제목] / [본문] / [설교자]
    날짜: [일자]
    광고:
    1. ...
    2. ...
    """
    data: Dict[str, Any] = {
        "metadata": {},
        "worship_1": {},
        "announcements": [],
        "prayer_requests": [],
    }

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    current_section = None

    for line in lines:
        if line.startswith("날짜:"):
            data["metadata"]["date_korean"] = line.replace("날짜:", "").strip()
        elif line.startswith("절기:"):
            data["metadata"]["season"] = line.replace("절기:", "").strip()
        elif line.startswith("설교:") or line.startswith("말씀:"):
            sermon_part = line.split(":", 1)[1].strip()
            parts = [p.strip() for p in sermon_part.split("/")]
            if len(parts) >= 1:
                data["worship_1"]["sermon_title"] = parts[0]
            if len(parts) >= 2:
                data["worship_1"]["scripture"] = parts[1]
            if len(parts) >= 3:
                data["worship_1"]["preacher"] = parts[2]
        elif line.startswith("광고:") or line.startswith("알림:"):
            current_section = "announcements"
        elif line.startswith("기도:") or line.startswith("기도나눔:"):
            current_section = "prayers"
        elif current_section == "announcements":
            # Match 1. Title - Content or 1. Title
            clean_item = re.sub(r"^\d+[\.\)]\s*", "", line)
            if " - " in clean_item:
                title, content = clean_item.split(" - ", 1)
                data["announcements"].append({"title": title.strip(), "content": content.strip()})
            else:
                data["announcements"].append({"title": clean_item.strip(), "content": ""})
        elif current_section == "prayers":
            data["prayer_requests"].append({"name": line, "content": ""})

    return data
