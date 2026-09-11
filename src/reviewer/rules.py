"""Rule-based proofreading and validation engine based on hyanglin-admin 15 rules and Sunday bulletin conventions."""
import datetime
import re
from typing import Any, Dict, List, Optional
from .models import IssueLevel, ReviewIssue


# Standard church floor mapping (공간 층수 기준)
FLOOR_MAPPING = {
    "향우실": "1층",
    "어린이부실": "1층",
    "방재실": "1층",
    "대예배실": "2층",
    "성가대실": "2층",
    "성찬준비실": "2층",
    "안병무도서관": "3층",
    "스튜디오": "3층",
    "방송실": "3층",
    "상담실": "4층",
    "세미나실": "4층",
    "유아·유치부실": "4층",
    "담임목사실": "4층",
    "선교나눔공간": "4층",
    "친교실": "5층",
    "식당": "5층",
    "서고": "5층",
    "청소년부실": "5층",
    "옥상정원": "6층",
}

# Standard Korean weekday names
WEEKDAYS_KOREAN = ["월", "화", "수", "목", "금", "토", "일"]

# Forbidden women's fellowship names (2026.08.30 이후 개정)
FORBIDDEN_WOMENS_FELLOWSHIP = {
    "청여": "청녀",
    "희여": "희녀",
    "장여": "장녀",
}


def extract_all_texts(data: Any) -> List[str]:
    """Recursively extract all text strings from a nested dictionary or list."""
    texts = []
    if isinstance(data, dict):
        for v in data.values():
            texts.extend(extract_all_texts(v))
    elif isinstance(data, list):
        for item in data:
            texts.extend(extract_all_texts(item))
    elif isinstance(data, str):
        texts.append(data)
    return texts


class BulletinRuleChecker:
    """Validator executing all 15 Hyanglin proofreading rules and structural checks."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.meta = data.get("metadata", {})
        self.worship = data.get("worship_1", data.get("worship", {}))
        self.announcements = data.get("announcements_sections", [])
        self.duties = data.get("duties", {})
        self.all_texts = extract_all_texts(data)

        # Parse target date
        self.target_date = self._parse_target_date()

    def _parse_target_date(self) -> Optional[datetime.date]:
        compact = self.meta.get("date_compact")
        if compact and len(str(compact)) == 8:
            try:
                return datetime.datetime.strptime(str(compact), "%Y%m%d").date()
            except ValueError:
                pass
        korean = self.meta.get("date_korean", "")
        m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", korean)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None

    def check_all(self) -> List[ReviewIssue]:
        """Run all proofreading checks and return aggregated issues."""
        issues: List[ReviewIssue] = []
        issues.extend(self.check_telephone_order())
        issues.extend(self.check_womens_fellowship_names())
        issues.extend(self.check_foreign_words())
        issues.extend(self.check_room_floors())
        issues.extend(self.check_date_weekdays())
        issues.extend(self.check_new_member_date())
        issues.extend(self.check_sunday_title_match())
        issues.extend(self.check_liturgical_cycle())
        issues.extend(self.check_announcement_numbers())
        issues.extend(self.check_today_schedule_missing())
        issues.extend(self.check_temporary_markers())
        issues.extend(self.check_duties_completeness())
        issues.extend(self.check_scripture_rules())
        return issues

    def check_telephone_order(self) -> List[ReviewIssue]:
        """규칙 1: 전화번호 순서 '776-9141, 3806' 우선 표기 (9141 대표번호 우선)."""
        issues = []
        for text in self.all_texts:
            if "776-3806" in text and "9141" in text:
                issues.append(ReviewIssue(
                    level=IssueLevel.ERROR,
                    category="고유규칙",
                    location="연락처/안내",
                    title="전화번호 순서 오류",
                    message="교회 전화번호는 '776-9141, 3806' 순서(9141 우선)로 표기해야 합니다.",
                    suggestion="'776-9141, 3806'으로 수정"
                ))
                break
        return issues

    def check_womens_fellowship_names(self) -> List[ReviewIssue]:
        """규칙 2: 여성 신도회 표기 '청녀, 희녀, 장녀' (청여, 희여, 장여 금지)."""
        issues = []
        for text in self.all_texts:
            for old_name, new_name in FORBIDDEN_WOMENS_FELLOWSHIP.items():
                if re.search(rf"\b{old_name}\b", text) or f"{old_name}신도회" in text or f"{old_name}회" in text:
                    issues.append(ReviewIssue(
                        level=IssueLevel.ERROR,
                        category="고유규칙",
                        location="신도회/소식",
                        title="여성 신도회 구 표기 사용",
                        message=f"'{old_name}'는 구 표기입니다. 2026년 8월 30일 개정 규칙에 따라 '{new_name}'로 표기해야 합니다.",
                        suggestion=f"'{old_name}' ➔ '{new_name}' 변경"
                    ))
        return issues

    def check_foreign_words(self) -> List[ReviewIssue]:
        """규칙 3: 코너 소제목은 '에큐메니칼 소식' 필수 (단, 본문 외부 소식명은 허용)."""
        issues = []
        for section in self.announcements:
            title = section.get("title", "")
            if "에큐메니컬" in title:
                issues.append(ReviewIssue(
                    level=IssueLevel.ERROR,
                    category="고유규칙",
                    location="5면 공동관심사 소제목",
                    title="외래어 소제목 표기 오류",
                    message="공동관심사 코너 소제목은 교회 기준에 따라 '에큐메니칼 소식'으로 표기해야 합니다.",
                    suggestion="'에큐메니칼 소식'으로 수정"
                ))
        return issues

    def check_room_floors(self) -> List[ReviewIssue]:
        """규칙 4: 공간 층수 표기 검증 (향우실 1층, 대예배실 2층, 친교실 5층 등)."""
        issues = []
        pattern = r"([가-힣·]+)\s*\(([1-6])층\)"
        for text in self.all_texts:
            for match in re.finditer(pattern, text):
                room_name, floor_num = match.group(1), match.group(2) + "층"
                if room_name in FLOOR_MAPPING:
                    correct_floor = FLOOR_MAPPING[room_name]
                    if floor_num != correct_floor:
                        issues.append(ReviewIssue(
                            level=IssueLevel.ERROR,
                            category="공간/층수",
                            location="일정 및 안내",
                            title=f"{room_name} 층수 표기 오류",
                            message=f"{room_name}은(는) {correct_floor}에 위치해 있으나 '{floor_num}'(으)로 잘못 표기되었습니다.",
                            suggestion=f"{room_name}({correct_floor})"
                        ))
        return issues

    def check_date_weekdays(self) -> List[ReviewIssue]:
        """규칙 5: 날짜 뒤 괄호 요일이 실제 달력 요일과 일치하는지 전수 검증."""
        issues = []
        year = self.target_date.year if self.target_date else 2026
        # Matches M월 D일(요일) or M/D(요일)
        patterns = [
            r"(\d{1,2})월\s*(\d{1,2})일\s*\(([월화수목금토일])\)",
            r"(\d{1,2})/(\d{1,2})\s*\(([월화수목금토일])\)",
        ]
        for text in self.all_texts:
            for pat in patterns:
                for match in re.finditer(pat, text):
                    m, d, written_w = int(match.group(1)), int(match.group(2)), match.group(3)
                    try:
                        cal_date = datetime.date(year, m, d)
                        actual_w = WEEKDAYS_KOREAN[cal_date.weekday()]
                        if written_w != actual_w:
                            issues.append(ReviewIssue(
                                level=IssueLevel.ERROR,
                                category="일정/달력",
                                location="본문 일정",
                                title="날짜 및 요일 불일치",
                                message=f"{m}월 {d}일은 실제 '{actual_w}요일'인데 '({written_w})'로 잘못 적혀 있습니다.",
                                suggestion=f"{m}월 {d}일({actual_w})"
                            ))
                    except ValueError:
                        issues.append(ReviewIssue(
                            level=IssueLevel.ERROR,
                            category="일정/달력",
                            location="본문 일정",
                            title="유효하지 않은 날짜",
                            message=f"달력에 존재하지 않는 날짜입니다: {m}월 {d}일"
                        ))
        return issues

    def check_new_member_date(self) -> List[ReviewIssue]:
        """규칙 6: 등록 새교우 일자는 반드시 일요일(주일)이어야 함."""
        issues = []
        year = self.target_date.year if self.target_date else 2026

        def verify_date(m: int, d: int, context_label: str):
            try:
                c_date = datetime.date(year, m, d)
                if c_date.weekday() != 6:  # 6 is Sunday
                    w_name = WEEKDAYS_KOREAN[c_date.weekday()]
                    issues.append(ReviewIssue(
                        level=IssueLevel.ERROR,
                        category="새교우",
                        location=f"새교우 안내 ({context_label})",
                        title="새교우 등록일 주일 불일치",
                        message=f"새교우 등록일은 주일예배 중 진행되므로 반드시 일요일이어야 합니다. ({m}월 {d}일은 {w_name}요일)",
                        suggestion="해당 주간 주일 날짜로 확인 및 수정"
                    ))
            except ValueError:
                pass

        # 1. 공동관심사 내 새교우 안내
        for section in self.announcements:
            for item in section.get("items", []):
                content = item.get("content", "") if isinstance(item, dict) else str(item)
                title = item.get("title", "") if isinstance(item, dict) else ""
                if "새교우" in title or "새교우" in content:
                    for match in re.finditer(r"(\d{1,2})월\s*(\d{1,2})일", content):
                        verify_date(int(match.group(1)), int(match.group(2)), "공동관심사")

        # 2. new_members 필드 (예: M/DD)
        new_members = self.data.get("new_members", [])
        for entry in new_members:
            entry_str = str(entry)
            for match in re.finditer(r"(\d{1,2})/(\d{1,2})", entry_str):
                verify_date(int(match.group(1)), int(match.group(2)), "새교우명단")

        return issues

    def check_sunday_title_match(self) -> List[ReviewIssue]:
        """규칙 7: 표지 주일 명칭과 2면 1부 예배 헤더 주일 명칭 글자 단위 일치."""
        issues = []
        cover_season = str(self.meta.get("season", "")).strip()
        worship_season = str(self.worship.get("season", cover_season)).strip()

        if cover_season and worship_season and cover_season != worship_season:
            issues.append(ReviewIssue(
                level=IssueLevel.ERROR,
                category="주일명칭",
                location="표지 / 예배순서 헤더",
                title="주일 명칭 불일치",
                message=f"1면 표지 절기명('{cover_season}')과 2면 예배 순서 절기명('{worship_season}')이 일치하지 않습니다.",
                suggestion=f"'{cover_season}'으로 통일"
            ))
        return issues

    def check_liturgical_cycle(self) -> List[ReviewIssue]:
        """규칙 8: 예전 찬송(주기도송/신앙고백송) 및 생활실천다짐 순환 규칙 점검."""
        issues = []
        if not self.target_date:
            return issues

        month = self.target_date.month

        # 예전 찬송 월별 규칙 (1,5,9월: 주기도송 245장 / 3,7,11월: 주기도송 246장 / 2,4,6,8,10,12월: 신앙고백송 254장)
        confession = str(self.worship.get("confession_or_lord_prayer", ""))
        if month in [1, 5, 9]:
            expected_title = "주기도송"
            expected_hymn = "245장"
        elif month in [3, 7, 11]:
            expected_title = "주기도송"
            expected_hymn = "246장"
        else:
            expected_title = "신앙고백송"
            expected_hymn = "254장"

        if confession:
            if expected_title not in confession or expected_hymn not in confession:
                issues.append(ReviewIssue(
                    level=IssueLevel.WARNING,
                    category="예전찬송",
                    location="2면 예배순서",
                    title=f"{month}월 예전 찬송 규칙 불일치",
                    message=f"{month}월은 '{expected_title}' (국악찬송 {expected_hymn}) 순서입니다. 현재 입력: '{confession}'",
                    suggestion=f"{expected_title} ({expected_hymn})"
                ))

        # 생활실천다짐 순환 번호 점검 (2026-09-06: 9번 기준)
        base_date = datetime.date(2026, 9, 6)
        weeks_diff = (self.target_date - base_date).days // 7
        expected_pledge = ((8 + weeks_diff) % 10) + 1  # 0-indexed 8 corresponds to 9th pledge

        # Check if pledge is specified in data
        pledge_num = self.meta.get("lifestyle_pledge_num") or self.data.get("lifestyle_pledge_num")
        if pledge_num and int(pledge_num) != expected_pledge:
            issues.append(ReviewIssue(
                level=IssueLevel.WARNING,
                category="생활실천다짐",
                location="5면 생활실천다짐",
                title="생활실천다짐 순환 번호 확인",
                message=f"순환 주기 계산상 이번 주는 {expected_pledge}번 조항 주간입니다. (현재 지정: {pledge_num}번)",
                suggestion=f"{expected_pledge}번 조항 적용"
            ))

        return issues

    def check_announcement_numbers(self) -> List[ReviewIssue]:
        """규칙 9: 공동관심사 1번부터 순차적 번호 연결성 점검."""
        issues = []
        if not self.announcements:
            return issues

        for i, section in enumerate(self.announcements, start=1):
            title = section.get("title", "")
            m = re.match(r"^(\d+)[\.\)]", title.strip())
            if m:
                num = int(m.group(1))
                if num != i:
                    clean_title = re.sub(r"^\d+[\.\)]\s*", "", title)
                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="소식번호",
                        location="공동관심사 소제목",
                        title="소식 코너 번호 불일치/건너뜀",
                        message=f"{i}번째 소식 코너 번호가 '{num}.'로 표기되었습니다. 순차 연결 확인이 필요합니다.",
                        suggestion=f"{i}. {clean_title}"
                    ))
        return issues

    def check_today_schedule_missing(self) -> List[ReviewIssue]:
        """규칙 10: 하위 코너(에큐메니칼 등)에 당일 행사가 적혀있는데 1번 오늘 일정에 누락되었는지 확인."""
        issues = []
        if not self.announcements or not self.target_date:
            return issues

        first_section = self.announcements[0]
        today_titles = []
        today_text_blob_parts = []
        for item in first_section.get("items", []):
            if isinstance(item, dict):
                today_titles.append(item.get("title", ""))
                today_text_blob_parts.append(item.get("title", "") + " " + item.get("content", ""))
            else:
                today_text_blob_parts.append(str(item))

        today_text_blob = " ".join(today_text_blob_parts)
        target_m_d = f"{self.target_date.month}월 {self.target_date.day}일"
        target_slash = f"{self.target_date.month}/{self.target_date.day}"

        # Search in other sections
        for section in self.announcements[1:]:
            sec_title = section.get("title", "")
            for item in section.get("items", []):
                if isinstance(item, dict):
                    it_title = item.get("title", "")
                    it_content = item.get("content", "")
                else:
                    it_title = ""
                    it_content = str(item)

                combined = it_title + " " + it_content

                if ("오늘" in combined or target_m_d in combined or target_slash in combined) and ("예배" in combined or "모임" in combined or "행사" in combined or "회의" in combined):
                    # Check if it is represented in today's section
                    if it_title and it_title not in today_titles and it_title not in today_text_blob:
                        issues.append(ReviewIssue(
                            level=IssueLevel.WARNING,
                            category="오늘일정누락",
                            location=f"공동관심사 {sec_title}",
                            title=f"'{it_title}' 오늘 일정(1번) 누락 가능성",
                            message=f"하위 코너에 당일({target_m_d}) 관련 행사가 적혀 있으나, 1번 '오늘 일정 안내' 목록에는 보이지 않습니다.",
                            suggestion="1번 오늘 일정에 추가 게재 검토"
                        ))
        return issues

    def check_temporary_markers(self) -> List[ReviewIssue]:
        """규칙 13: '내용 확인 요망', '준비 중', 빈 괄호 '()' 등 미완성 문구 점검 (빨간색 알림 대상)."""
        issues = []
        temp_keywords = [
            ("확인 요망", "내용 확인 요망 문구가 남아있습니다."),
            ("준비 중", "준비 중 문구가 남아있습니다."),
            ("준비중", "준비중 문구가 남아있습니다."),
            ("사진 준비", "사진 준비 관련 임시 문구가 남아있습니다."),
            ("미정", "미정 상태의 항목이 있습니다."),
        ]

        # 1. 2면 찬양 순서 점검
        choir_title = str(self.worship.get("choir_song_title", "")).strip()
        if not choir_title or choir_title in ["“미정”", "“준비중”", "“찬양곡 준비 중”"]:
            issues.append(ReviewIssue(
                level=IssueLevel.WARNING,
                category="미완성항목",
                location="2면 찬양순서",
                title="1부 찬양 곡명 미정",
                message="성가대 찬양 곡명이 아직 확정되지 않았습니다.",
                suggestion="[찬양곡 준비 중] (빨간색 표시)",
                is_temporary_marker=True
            ))

        # 2. 성서 쪽수 미정 점검
        scripture = str(self.worship.get("scripture", ""))
        if "쪽" not in scripture and scripture:
            issues.append(ReviewIssue(
                level=IssueLevel.WARNING,
                category="미완성항목",
                location="4면 성서읽기",
                title="성경 본문 쪽수 미정",
                message=f"성경 본문({scripture})에 쪽수(예: 000쪽)가 표기되지 않았습니다.",
                suggestion="과거 주보 기준 예상 쪽수 확인 필요",
                is_temporary_marker=True
            ))

        # 3. 본문 내 임시 키워드 검색
        for text in self.all_texts:
            for kw, msg in temp_keywords:
                if kw in text:
                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="임시문구",
                        location="본문",
                        title=f"임시 문구 잔존: '{kw}'",
                        message=msg,
                        suggestion="최종 인쇄 전 확정 내용으로 교체",
                        is_temporary_marker=True
                    ))

        return issues

    def check_duties_completeness(self) -> List[ReviewIssue]:
        """규칙 14: 예배위원 표 3주간 공란 및 빈 괄호 점검."""
        issues = []
        duty_roles = [
            ("presider", "예배인도"),
            ("pastoral_prayer", "목회기도"),
            ("scripture_reader", "성서읽기"),
            ("preacher", "하늘뜻펴기"),
            ("thanks_prayer", "감사기도"),
        ]

        for w_key, w_name in [("w1", "이번 주(당주)"), ("w2", "다음 주(차주)"), ("w3", "다다음 주")]:
            w_duty = self.duties.get(w_key, {})
            for role_key, role_name in duty_roles:
                val = str(w_duty.get(role_key, "")).strip()
                if not val:
                    level = IssueLevel.ERROR if w_key == "w1" else IssueLevel.WARNING
                    issues.append(ReviewIssue(
                        level=level,
                        category="예배위원",
                        location=f"예배위원 {w_name}",
                        title=f"{w_name} {role_name} 미정/공란",
                        message=f"{w_name}의 {role_name} 담당자가 비어 있습니다.",
                        suggestion=f"{role_name} 담당자 확인",
                        is_temporary_marker=(w_key == "w1")
                    ))

        # 주일 봉사자 빈 괄호 점검
        service = self.data.get("service_duties", {})
        for k, v in service.items():
            if str(v).strip() == "()" or str(v).strip() == "":
                issues.append(ReviewIssue(
                    level=IssueLevel.WARNING,
                    category="주일봉사",
                    location="주일 봉사자 안내",
                    title=f"봉사 항목({k}) 담당자 미정",
                    message=f"{k} 봉사자 명단이 비어 있습니다.",
                    suggestion="담당 신도회/부서 확인"
                ))

        return issues

    def check_scripture_rules(self) -> List[ReviewIssue]:
        """규칙 11: 성서 책 이름 누락 방지 (예: '119:33' 대신 '시편 119:33')."""
        issues = []
        call_scrip = str(self.worship.get("call_scripture", ""))
        if call_scrip and re.match(r"^\d+[:장]", call_scrip):
            issues.append(ReviewIssue(
                level=IssueLevel.ERROR,
                category="성서표기",
                location="예배부름 성서",
                title="성서 책 이름 누락",
                message=f"책 이름 없이 장절만 표기되었습니다: '{call_scrip}'",
                suggestion="예: '시편 119:12-13'"
            ))
        return issues
