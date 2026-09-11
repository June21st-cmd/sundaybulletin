"""Unit tests for the bulletin continuous review and QA system."""
import datetime
from pathlib import Path
import unittest

from src.reviewer.models import IssueLevel
from src.reviewer.rules import BulletinRuleChecker
from src.reviewer.cross_week import CrossWeekComparator
from src.reviewer.diff_tracker import VersionDiffTracker
from src.reviewer.engine import BulletinReviewer


class TestBulletinReviewer(unittest.TestCase):

    def setUp(self):
        self.sample_data = {
            "metadata": {
                "date_compact": "20260913",
                "date_korean": "2026년 9월 13일",
                "season": "창조절 둘째주일",
            },
            "worship_1": {
                "call_scripture": "시편 119:12-13",
                "choir_song_title": "새로운 만남",
                "choir_song_info": "글: 이현주, 곡: 백창우",
                "scripture": "미가서 4:1-4 (1306쪽), 고린도후서 5:16-20 (310쪽)",
                "sermon_title": "정의와 평화가 입을 맞출 때",
                "confession_or_lord_prayer": "주기도송(1) 245장",
            },
            "duties": {
                "w1": {"presider": "김기수 장로", "pastoral_prayer": "강은성 장로", "scripture_reader": "이지유 교우", "preacher": "한문덕 목사", "thanks_prayer": "정선영 집사"},
                "w2": {"presider": "정상희 집사", "pastoral_prayer": "김자영 집사", "scripture_reader": "김지현 교우", "preacher": "송진순 박사", "thanks_prayer": "이나래 교우"},
                "w3": {"presider": "채운석 장로", "pastoral_prayer": "김정미 장로", "scripture_reader": "", "preacher": "한문덕 목사", "thanks_prayer": ""},
            },
            "announcements_sections": [
                {
                    "title": "1. 오늘 일정 안내",
                    "items": [{"title": "신도회 월례회", "content": "공동식사 후"}]
                },
                {
                    "title": "2. 함께 만드는 향린",
                    "items": [{"title": "안병무도서관", "content": "향우실(1층) 도서 전시"}]
                }
            ]
        }

    def test_telephone_rule(self):
        """전화번호 순서 규칙: 776-3806, 9141는 오류 검출되고 9141 우선으로 제안되어야 함."""
        bad_data = dict(self.sample_data)
        bad_data["announcements_sections"] = [{
            "title": "1. 오늘 일정 안내",
            "items": [{"title": "문의", "content": "교회 전화: 776-3806, 9141"}]
        }]
        checker = BulletinRuleChecker(bad_data)
        issues = checker.check_telephone_order()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, IssueLevel.ERROR)
        self.assertIn("776-9141, 3806", issues[0].suggestion)

    def test_womens_fellowship_rule(self):
        """여성 신도회 구 표기(청여, 희여, 장여) 오류 검출."""
        bad_data = dict(self.sample_data)
        bad_data["announcements_sections"] = [{
            "title": "1. 오늘 일정 안내",
            "items": [{"title": "모임", "content": "청여 월례회는 1층에서 모입니다."}]
        }]
        checker = BulletinRuleChecker(bad_data)
        issues = checker.check_womens_fellowship_names()
        self.assertEqual(len(issues), 1)
        self.assertIn("청녀", issues[0].suggestion)

    def test_room_floor_rule(self):
        """공간 층수 오류(향우실 4층 X -> 1층) 검출."""
        bad_data = dict(self.sample_data)
        bad_data["announcements_sections"] = [{
            "title": "1. 오늘 일정 안내",
            "items": [{"title": "모임", "content": "향우실(4층)에서 모입니다."}]
        }]
        checker = BulletinRuleChecker(bad_data)
        issues = checker.check_room_floors()
        self.assertEqual(len(issues), 1)
        self.assertIn("1층", issues[0].message)

    def test_date_weekday_validation(self):
        """날짜 뒤 괄호 요일 불일치 검출 (2026-09-13은 일요일인데 토요일로 적힌 경우)."""
        bad_data = dict(self.sample_data)
        bad_data["announcements_sections"] = [{
            "title": "1. 오늘 일정 안내",
            "items": [{"title": "예배", "content": "9월 13일(토) 11:00 대예배"}]
        }]
        checker = BulletinRuleChecker(bad_data)
        issues = checker.check_date_weekdays()
        self.assertEqual(len(issues), 1)
        self.assertIn("일요일", issues[0].message)

    def test_cross_week_duties_relay(self):
        """직전 주 주보의 차주(w2) 예고와 이번 주 당주(w1) 불일치 감지."""
        prev_data = {
            "duties": {
                "w2": {"presider": "김향린 장로", "pastoral_prayer": "강은성 장로", "scripture_reader": "이지유 교우", "preacher": "한문덕 목사", "thanks_prayer": "정선영 집사"},
                "w3": {"presider": "정상희 집사", "pastoral_prayer": "김자영 집사", "scripture_reader": "김지현 교우", "preacher": "송진순 박사", "thanks_prayer": "이나래 교우"},
            }
        }
        comparator = CrossWeekComparator(self.sample_data, prev_data)
        issues, summary = comparator.compare()
        # 인도자가 지난주 예고(김향린)와 이번주(김기수) 불일치
        presider_issues = [i for i in issues if "예배인도" in i.title]
        self.assertTrue(len(presider_issues) >= 1)

    def test_version_diff_tracker(self):
        """버전 간 변경사항 추적: 찬양곡 확정 및 설교제목 변경 감지."""
        prev_version = {
            "worship_1": {
                "sermon_title": "초안 설교 제목",
                "choir_song_title": "",  # 이전엔 미정
            }
        }
        tracker = VersionDiffTracker(self.sample_data, prev_version)
        issues, summary = tracker.track_diff()
        self.assertTrue(any("새로운 만남" in a for a in summary["added"]))
        self.assertTrue(any("정의와 평화가 입을 맞출 때" in m for m in summary["modified"]))


if __name__ == "__main__":
    unittest.main()
