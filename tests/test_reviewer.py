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

    def test_scripture_page_rules(self):
        """성경 쪽수 점검: 미정, 임시(예상), 2개 본문 중 1개 누락 적발."""
        # 1. '예상' 등 미확정 키워드 포함
        tentative_data = dict(self.sample_data)
        tentative_data["worship_1"] = dict(self.sample_data["worship_1"])
        tentative_data["worship_1"]["scripture"] = "예레미야서 29:4-9 (1111쪽 예상), 베드로전서 2:9-12 (400쪽)"
        checker = BulletinRuleChecker(tentative_data)
        issues = checker.check_temporary_markers()
        self.assertTrue(any("확인 요망" in i.title for i in issues))

        # 2. 본문 2개 중 1개 쪽수 누락
        missing_one_data = dict(self.sample_data)
        missing_one_data["worship_1"] = dict(self.sample_data["worship_1"])
        missing_one_data["worship_1"]["scripture"] = "예레미야서 29:4-9, 베드로전서 2:9-12 (400쪽)"
        checker2 = BulletinRuleChecker(missing_one_data)
        issues2 = checker2.check_temporary_markers()
        self.assertTrue(any("일부 쪽수 누락" in i.title for i in issues2))

    def test_ecumenical_and_ongoing_same_day_no_conflicting_today_warning(self):
        """에큐메니칼 소식 및 함께 만드는 향린에 배치된 당일 행사에 대해 '오늘 일정 추가' 상충 경고가 발생하지 않아야 함."""
        synth_data = {
            "metadata": {"date_compact": "20261115", "date_korean": "2026년 11월 15일"},
            "worship_1": {"choir_song_title": "가상찬양", "scripture": "창세기 1:1 (1쪽)"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": []},
                {"title": "2. 함께 만드는 향린", "items": [{"title": "가상도서모임", "content": "11/15(일) 오늘 도서 나눔 모임"}]},
                {"title": "3. 이번주 일정 안내", "items": []},
                {"title": "4. 이후 일정 안내", "items": []},
                {"title": "5. 에큐메니칼 소식", "items": [{"title": "NCCK 가상연합예배", "content": "11/15(일) 오늘 15:00 연합예배"}]},
                {"title": "6. 감사헌금", "items": []},
            ],
        }
        checker = BulletinRuleChecker(synth_data)
        today_warns = [i for i in checker.check_all() if i.category == "오늘일정누락"]
        self.assertEqual(today_warns, [])

    def test_first_section_not_assumed_today_and_internal_today_missing_still_warns(self):
        """첫 섹션을 무조건 오늘 일정으로 간주하지 않으며, 내부 일정 코너에 당일 행사가 있으면 정상 경고함."""
        # 1. 첫 섹션이 '3. 이번주 일정 안내'인 비정상 입력에서 첫 섹션을 '오늘 일정'으로 오인하지 않음
        no_today_sec = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "3. 이번주 일정 안내", "items": [{"title": "가상내부회의", "content": "11/15(일) 13:00 회의"}]},
            ],
        }
        issues_a = BulletinRuleChecker(no_today_sec).check_today_schedule_missing()
        self.assertEqual(len(issues_a), 1)
        self.assertEqual(issues_a[0].category, "오늘일정누락")

        # 2. 정상 6단 구조에서 '3. 이번주 일정 안내'에 당일 내부 행사가 잘못 들어간 경우 경고 유지
        misplaced_internal = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": []},
                {"title": "2. 함께 만드는 향린", "items": []},
                {"title": "3. 이번주 일정 안내", "items": [{"title": "가상내부회의", "content": "11/15(일) 14:00 회의"}]},
                {"title": "4. 이후 일정 안내", "items": []},
                {"title": "5. 에큐메니칼 소식", "items": []},
                {"title": "6. 감사헌금", "items": []},
            ],
        }
        issues_b = BulletinRuleChecker(misplaced_internal).check_today_schedule_missing()
        self.assertEqual(len(issues_b), 1)

    def test_year_end_date_weekday_rollover(self):
        """연말 주보(2026-12-27)에서 연도 표기 없는 새해 날짜(1/3(일), 1/4(월))의 요일을 2027년 기준으로 판별."""
        year_end_ok = {
            "metadata": {"date_compact": "20261227"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": [{"title": "가상모임", "content": "12/27(일) 13:00"}]},
                {"title": "2. 함께 만드는 향린", "items": []},
                {"title": "3. 이번주 일정 안내", "items": [{"title": "가상신년모임", "content": "1/3(일) 13:00"}]},
                {"title": "4. 이후 일정 안내", "items": [{"title": "가상수련회", "content": "1/4(월) 10:00"}]},
                {"title": "5. 에큐메니칼 소식", "items": []},
                {"title": "6. 감사헌금", "items": []},
            ],
        }
        self.assertEqual(BulletinRuleChecker(year_end_ok).check_date_weekdays(), [])

        year_end_bad = {
            "metadata": {"date_compact": "20261227"},
            "announcements_sections": [
                {"title": "3. 이번주 일정 안내", "items": [{"title": "가상신년모임", "content": "1/3(토) 13:00"}]},
            ],
        }
        self.assertEqual(len(BulletinRuleChecker(year_end_bad).check_date_weekdays()), 1)

    def test_past_year_and_unconfirmed_year_weekday_consistency(self):
        """발행일 2026-11-15 기준 '작년 11/18(화)' 존중, 연도 미확정 날짜 임의 연도 ERROR 금지, 명시적 ISO date 지원 검증."""
        # 1. '작년 11/18(화)'는 2025-11-18(화요일)로 판별되어 ERROR가 없어야 함
        past_ok = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": [{"title": "가상모임", "content": "작년 11/18(화) 19:00 기록"}]},
            ],
        }
        self.assertEqual(BulletinRuleChecker(past_ok).check_date_weekdays(), [])

        # '작년 11/18(수)'는 2025-11-18이 화요일이므로 요일 불일치 ERROR 검출
        past_bad = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": [{"title": "가상모임", "content": "작년 11/18(수) 19:00 기록"}]},
            ],
        }
        past_bad_issues = BulletinRuleChecker(past_bad).check_date_weekdays()
        self.assertEqual(len(past_bad_issues), 1)
        self.assertEqual(past_bad_issues[0].level, IssueLevel.ERROR)
        self.assertIn("2025년 11월 18일", past_bad_issues[0].message)

        # 2. 문맥만으로 연도를 확정할 수 없는 '9/2(화)', '2/10(화)'는 임의 연도로 확정해 ERROR를 만들지 않고 WARNING으로 표시
        unconfirmed = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {
                    "title": "4. 이후 일정 안내",
                    "items": [
                        {"title": "가상모임A", "content": "9/2(화) 19:00"},
                        {"title": "가상모임B", "content": "2/10(화) 10:00"},
                    ],
                },
            ],
        }
        unc_issues = BulletinRuleChecker(unconfirmed).check_date_weekdays()
        self.assertEqual([i for i in unc_issues if i.level == IssueLevel.ERROR], [])
        self.assertEqual(len([i for i in unc_issues if i.level == IssueLevel.WARNING]), 2)

        # 3. 항목에 명시적 ISO date('2027-02-10')가 있으면 해당 연도로 요일 검증 수행
        iso_ok = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "4. 이후 일정 안내", "items": [{"title": "가상수련회", "date": "2027-02-10", "content": "2/10(수) 10:00"}]},
            ],
        }
        self.assertEqual(BulletinRuleChecker(iso_ok).check_date_weekdays(), [])

        iso_bad = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "4. 이후 일정 안내", "items": [{"title": "가상수련회", "date": "2027-02-10", "content": "2/10(화) 10:00"}]},
            ],
        }
        iso_bad_issues = BulletinRuleChecker(iso_bad).check_date_weekdays()
        self.assertEqual(len(iso_bad_issues), 1)
        self.assertEqual(iso_bad_issues[0].level, IssueLevel.ERROR)
        self.assertIn("2027년 2월 10일", iso_bad_issues[0].message)


if __name__ == "__main__":
    unittest.main()
