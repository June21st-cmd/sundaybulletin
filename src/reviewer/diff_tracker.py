"""Version diff tracker: tracks changes between revision versions (_v1 -> _v2)."""
from typing import Any, Dict, List, Tuple
from .models import IssueLevel, ReviewIssue


class VersionDiffTracker:
    """Detects added, modified, and accidentally removed items between revisions."""

    def __init__(self, current_data: Dict[str, Any], prev_version_data: Dict[str, Any]):
        self.curr = current_data
        self.prev = prev_version_data

    def track_diff(self) -> Tuple[List[ReviewIssue], Dict[str, Any]]:
        """Compare current version with previous version."""
        issues: List[ReviewIssue] = []
        summary: Dict[str, Any] = {
            "added": [],
            "modified": [],
            "removed": [],
        }

        # 1. 예배 순서 변경 추적
        curr_w = self.curr.get("worship_1", {})
        prev_w = self.prev.get("worship_1", {})

        worship_fields = [
            ("sermon_title", "하늘뜻펴기(설교) 제목"),
            ("preacher", "설교자"),
            ("scripture", "성경 본문"),
            ("choir_song_title", "성가대 찬양 곡명"),
            ("choir_song_info", "찬양 작사/작곡 정보"),
            ("opening_hymn", "여는찬송"),
            ("offering_hymn", "봉헌/결단 찬송"),
        ]

        for field_key, field_name in worship_fields:
            c_val = str(curr_w.get(field_key, "")).strip()
            p_val = str(prev_w.get(field_key, "")).strip()

            if not p_val and c_val:
                summary["added"].append(f"{field_name}: '{c_val}' 반영됨")
            elif p_val and not c_val:
                summary["removed"].append(f"{field_name}: 이전에 있던 '{p_val}' 삭제됨(공란)")
                issues.append(ReviewIssue(
                    level=IssueLevel.WARNING,
                    category="버전변경",
                    location="2면 예배순서",
                    title=f"{field_name} 삭제/공란화 감지",
                    message=f"이전 버전에는 '{p_val}'(으)로 기재되어 있었으나 현재 비어 있습니다.",
                    suggestion="의도된 삭제인지 확인 필요"
                ))
            elif p_val and c_val and p_val != c_val:
                summary["modified"].append(f"{field_name}: '{p_val}' ➔ '{c_val}'")

        # 2. 예배위원 변경 추적
        curr_d = self.curr.get("duties", {})
        prev_d = self.prev.get("duties", {})

        duty_roles = [
            ("presider", "예배인도"),
            ("pastoral_prayer", "목회기도"),
            ("scripture_reader", "성서읽기"),
            ("preacher", "하늘뜻펴기"),
            ("thanks_prayer", "감사기도"),
        ]

        for w_key, w_name in [("w1", "이번 주"), ("w2", "다음 주"), ("w3", "다다음 주")]:
            c_w = curr_d.get(w_key, {})
            p_w = prev_d.get(w_key, {})

            for r_key, r_name in duty_roles:
                c_person = str(c_w.get(r_key, "")).strip()
                p_person = str(p_w.get(r_key, "")).strip()

                if not p_person and c_person:
                    summary["added"].append(f"{w_name} {r_name}: '{c_person}' 확정")
                elif p_person and not c_person:
                    summary["removed"].append(f"{w_name} {r_name}: '{p_person}' 삭제됨")
                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="버전변경",
                        location=f"예배위원 {w_name}",
                        title=f"{w_name} {r_name} 삭제됨",
                        message=f"이전 버전의 '{p_person}'(이)가 현재 버전에서 비워졌습니다.",
                        suggestion="의도된 삭제인지 확인 필요"
                    ))
                elif p_person and c_person and p_person != c_person:
                    summary["modified"].append(f"{w_name} {r_name}: '{p_person}' ➔ '{c_person}'")

        # 3. 공동관심사 소식 추가/삭제 추적
        curr_ann = self.curr.get("announcements_sections", [])
        prev_ann = self.prev.get("announcements_sections", [])

        curr_titles = set()
        for sec in curr_ann:
            for it in sec.get("items", []):
                t = it.get("title", "") if isinstance(it, dict) else str(it)
                if t:
                    curr_titles.add(t)

        prev_titles = set()
        for sec in prev_ann:
            for it in sec.get("items", []):
                t = it.get("title", "") if isinstance(it, dict) else str(it)
                if t:
                    prev_titles.add(t)

        added_news = curr_titles - prev_titles
        removed_news = prev_titles - curr_titles

        for n in added_news:
            summary["added"].append(f"새 소식 추가: '{n}'")
        for n in removed_news:
            summary["removed"].append(f"소식 항목 삭제: '{n}'")
            issues.append(ReviewIssue(
                level=IssueLevel.INFO,
                category="버전변경",
                location="5면 공동관심사",
                title=f"소식 항목 삭제: '{n}'",
                message=f"이전 버전에 있던 '{n}' 항목이 삭제되었습니다.",
                suggestion="삭제 의도 확인"
            ))

        return issues, summary
