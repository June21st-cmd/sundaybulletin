"""Cross-week bulletin comparator: compares current bulletin with previous week's golden bulletin."""
import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
import zipfile
import yaml

from .models import IssueLevel, ReviewIssue


GOLDEN_BULLETIN_DIR = Path(r"C:\Users\june2\OneDrive\바탕 화면\주보인수인계\예배주보\주보2026")


def parse_hwpx_text_and_tables(hwpx_path: Path) -> Dict[str, Any]:
    """Lightweight extractor for HWPX text and tables without Word/Hancom COM."""
    result: Dict[str, Any] = {
        "raw_text": "",
        "duties": {},
        "announcement_titles": [],
    }
    if not hwpx_path.is_file():
        return result

    try:
        with zipfile.ZipFile(hwpx_path, "r") as zf:
            if "Contents/section0.xml" not in zf.namelist():
                return result
            xml_bytes = zf.read("Contents/section0.xml")
            xml_str = xml_bytes.decode("utf-8", errors="ignore")

            # Extract all texts
            texts = re.findall(r"<(?:\w+:)?t>([^<]+)</(?:\w+:)?t>", xml_str)
            result["raw_text"] = " ".join(texts)

            # Look for duty table pattern
            # Duties table typically has 3 dates like 09/06, 09/13, 09/20
            # and roles: 인도, 목회기도, 성서읽기, 하늘뜻펴기, 감사기도
            date_matches = re.findall(r"(\d{2}/\d{2})", result["raw_text"])
            if date_matches:
                result["duty_dates"] = date_matches[:3]

    except Exception as e:
        result["error"] = str(e)

    return result


class CrossWeekComparator:
    """Compares current bulletin against previous week's bulletin."""

    def __init__(self, current_data: Dict[str, Any], prev_bulletin_data: Optional[Dict[str, Any]] = None):
        self.current_data = current_data
        self.prev_data = prev_bulletin_data or self._find_and_load_prev_bulletin()

    def _get_target_date(self) -> Optional[datetime.date]:
        meta = self.current_data.get("metadata", {})
        compact = meta.get("date_compact")
        if compact and len(str(compact)) == 8:
            try:
                return datetime.datetime.strptime(str(compact), "%Y%m%d").date()
            except ValueError:
                pass
        korean = meta.get("date_korean", "")
        m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", korean)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None

    def _find_and_load_prev_bulletin(self) -> Optional[Dict[str, Any]]:
        """Automatically discover and load previous week's bulletin data."""
        target_date = self._get_target_date()
        if not target_date:
            return None

        prev_date = target_date - datetime.timedelta(days=7)
        prev_compact = prev_date.strftime("%Y%m%d")

        # 1. Look for input YAML
        candidate_yamls = [
            Path(f"input/bulletin_{prev_compact}.yaml"),
            Path(f"data/inputs/bulletin_{prev_compact}.yaml"),
        ]
        for y_path in candidate_yamls:
            if y_path.is_file():
                try:
                    with open(y_path, "r", encoding="utf-8") as f:
                        return yaml.safe_load(f)
                except Exception:
                    pass

        # 2. Look for Golden Reference HWPX
        golden_hwpx = GOLDEN_BULLETIN_DIR / f"[주보] {prev_compact}.hwpx"
        if golden_hwpx.is_file():
            return parse_hwpx_text_and_tables(golden_hwpx)

        return None

    def compare(self) -> Tuple[List[ReviewIssue], Dict[str, Any]]:
        """Execute cross-week comparison and return issues and summary."""
        issues: List[ReviewIssue] = []
        summary: Dict[str, Any] = {
            "has_prev_data": self.prev_data is not None,
            "duty_relay_matches": [],
            "duty_relay_mismatches": [],
            "expired_events_found": [],
            "carried_over_announcements": [],
        }

        if not self.prev_data:
            issues.append(ReviewIssue(
                level=IssueLevel.INFO,
                category="직전주대조",
                location="시스템",
                title="직전 주 주보 데이터 미발견",
                message="직전 주 주보(YAML/HWPX)를 찾을 수 없어 단독 검토로 진행합니다."
            ))
            return issues, summary

        # 1. 예배위원 3주 릴레이 대조
        duty_issues, duty_summary = self._compare_duties_relay()
        issues.extend(duty_issues)
        summary.update(duty_summary)

        # 2. 공동관심사(소식면) 일정 연속성 및 만료 일정 대조
        ann_issues, ann_summary = self._compare_announcements_continuity()
        issues.extend(ann_issues)
        summary.update(ann_summary)

        return issues, summary

    def _compare_duties_relay(self) -> Tuple[List[ReviewIssue], Dict[str, Any]]:
        """예배위원 3주 릴레이: 지난주 w2 ➔ 이번주 w1, 지난주 w3 ➔ 이번주 w2 대조."""
        issues: List[ReviewIssue] = []
        summary: Dict[str, Any] = {"duty_relay_matches": [], "duty_relay_mismatches": []}

        prev_duties = self.prev_data.get("duties", {})
        curr_duties = self.current_data.get("duties", {})

        if not prev_duties or not curr_duties:
            return issues, summary

        roles = [
            ("presider", "예배인도"),
            ("pastoral_prayer", "목회기도"),
            ("scripture_reader", "성서읽기"),
            ("preacher", "하늘뜻펴기"),
            ("thanks_prayer", "감사기도"),
        ]

        # Check Relay 1: Last week's w2 (next week) -> This week's w1 (this week)
        prev_w2 = prev_duties.get("w2", {})
        curr_w1 = curr_duties.get("w1", {})

        PLACEHOLDER_NAMES = {"예배위원 선택", "예배위원", "교우", "미정", "선택", "준비중", "준비 중"}

        for role_key, role_name in roles:
            expected_person = str(prev_w2.get(role_key, "")).strip()
            current_person = str(curr_w1.get(role_key, "")).strip()

            if expected_person and expected_person not in PLACEHOLDER_NAMES:
                if not current_person:
                    issues.append(ReviewIssue(
                        level=IssueLevel.ERROR,
                        category="예배위원릴레이",
                        location="이번 주 예배위원",
                        title=f"{role_name} 담당자 누락 (지난주 예고)",
                        message=f"지난주 주보에는 이번 주 {role_name} 담당자로 '{expected_person}'(이)가 예고되었으나, 현재 비어 있습니다.",
                        suggestion=f"{expected_person}",
                        is_temporary_marker=True
                    ))
                    summary["duty_relay_mismatches"].append(f"이번 주 {role_name}: 누락 (예고: {expected_person})")
                elif current_person != expected_person:
                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="예배위원릴레이",
                        location="이번 주 예배위원",
                        title=f"{role_name} 담당자 변경 확인",
                        message=f"지난주 주보 예고('{expected_person}')와 이번 주 기입('{current_person}')이 다릅니다. 담당자 변경이 맞는지 확인하세요.",
                        suggestion=f"확인 필요 (지난주 예고: {expected_person} ➔ 현재: {current_person})"
                    ))
                    summary["duty_relay_mismatches"].append(f"이번 주 {role_name}: 변경 ({expected_person} ➔ {current_person})")
                else:
                    summary["duty_relay_matches"].append(f"이번 주 {role_name}: {current_person} (일치)")
            elif current_person:
                summary["duty_relay_matches"].append(f"이번 주 {role_name}: {current_person} (확정)")

        # Check Relay 2: Last week's w3 -> This week's w2
        prev_w3 = prev_duties.get("w3", {})
        curr_w2 = curr_duties.get("w2", {})

        for role_key, role_name in roles:
            expected_person = str(prev_w3.get(role_key, "")).strip()
            current_person = str(curr_w2.get(role_key, "")).strip()

            if expected_person and expected_person not in PLACEHOLDER_NAMES and current_person and current_person != expected_person:
                issues.append(ReviewIssue(
                    level=IssueLevel.WARNING,
                    category="예배위원릴레이",
                    location="다음 주 예배위원",
                    title=f"다음 주 {role_name} 담당자 변경 확인",
                    message=f"지난주 다다음주 예고('{expected_person}')와 이번 주 다음주 기입('{current_person}')이 다릅니다.",
                    suggestion=f"확인 필요 ({expected_person} vs {current_person})"
                ))

        return issues, summary

    def _compare_announcements_continuity(self) -> Tuple[List[ReviewIssue], Dict[str, Any]]:
        """공동관심사 소식: 지난 일정 방치 적발 및 지난주 '이후 일정'의 이번주 승격 확인."""
        issues: List[ReviewIssue] = []
        summary: Dict[str, Any] = {"expired_events_found": [], "carried_over_announcements": []}

        target_date = self._get_target_date()
        if not target_date:
            return issues, summary

        # 1. 만료된 과거 일정 방치 검출 (오늘 이전 날짜가 소식에 그대로 남아있는 경우)
        year = target_date.year
        curr_sections = self.current_data.get("announcements_sections", [])

        for section in curr_sections:
            sec_title = section.get("title", "")
            for item in section.get("items", []):
                if isinstance(item, dict):
                    it_title = item.get("title", "")
                    it_content = item.get("content", "")
                else:
                    it_title = ""
                    it_content = str(item)
                combined = it_title + " " + it_content

                # Find dates like M월 D일 or M/D
                date_matches = re.finditer(r"(\d{1,2})월\s*(\d{1,2})일", combined)
                for m in date_matches:
                    mo, da = int(m.group(1)), int(m.group(2))
                    try:
                        event_date = datetime.date(year, mo, da)
                        # If event was before this Sunday, and not in today's context
                        if event_date < target_date:
                            # Allow if it's a retroactive notice or report
                            if "보고" not in combined and "감사" not in combined and "마감" not in combined:
                                issues.append(ReviewIssue(
                                    level=IssueLevel.WARNING,
                                    category="과거일정방치",
                                    location=f"공동관심사 {sec_title}",
                                    title=f"지나간 일정 방치 의심: '{it_title or it_content[:20]}'",
                                    message=f"{mo}월 {da}일 행사는 이미 지난 일정입니다. 지난주 소식이 복사되어 그대로 남아있는지 확인하세요.",
                                    suggestion=f"삭제하거나 새 일정으로 업데이트"
                                ))
                                summary["expired_events_found"].append(f"{it_title or it_content[:20]} ({mo}월 {da}일)")
                    except ValueError:
                        pass

        # 2. 지난주 '이후 일정' ➔ 이번 주 '오늘/이번주 일정' 승격 확인
        prev_sections = self.prev_data.get("announcements_sections", [])
        prev_future_items = []
        for sec in prev_sections:
            if "이후 일정" in sec.get("title", ""):
                prev_future_items = sec.get("items", [])
                break

        curr_titles = []
        for sec in curr_sections:
            for it in sec.get("items", []):
                if isinstance(it, dict):
                    curr_titles.append(it.get("title", ""))
                else:
                    curr_titles.append(str(it))

        curr_blob = " ".join(curr_titles)

        for f_item in prev_future_items:
            f_title = f_item.get("title", "")
            # If the future item mentioned this Sunday's date or matches title
            target_m_d = f"{target_date.month}월 {target_date.day}일"
            target_slash = f"{target_date.month}/{target_date.day}"
            f_content = f_item.get("content", "")

            if target_m_d in f_content or target_slash in f_content or "다음 주" in f_content:
                if f_title in curr_blob:
                    summary["carried_over_announcements"].append(f"✅ '{f_title}' (지난주 이후일정 ➔ 이번주 반영 확인)")
                else:
                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="일정연속성",
                        location="공동관심사",
                        title=f"지난주 예고 행사('{f_title}') 누락 가능성",
                        message=f"지난주 '이후 일정 안내'에 이번 주({target_m_d}) 행사로 예고되었던 '{f_title}'(이)가 이번 주 소식에서 보이지 않습니다.",
                        suggestion="이번 주 소식에 포함 검토"
                    ))

        return issues, summary
