"""Unit tests for bulletin data parser and validator."""
import datetime
import tempfile
import unittest
from pathlib import Path

from src.parser import (
    extract_date_mentions,
    load_bulletin_data,
    parse_raw_text_to_dict,
    validate_bulletin_data,
)


class TestBulletinParser(unittest.TestCase):
    def test_load_valid_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, encoding="utf-8") as f:
            f.write("metadata:\n  date_compact: '20260816'\n  season: '성령강림주일'\n")
            temp_path = f.name
        
        try:
            data = load_bulletin_data(temp_path)
            self.assertEqual(data["metadata"]["date_compact"], "20260816")
            self.assertEqual(data["metadata"]["season"], "성령강림주일")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_bulletin_data("non_existent_file.yaml")

    def test_invalid_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("hello")
            temp_path = f.name
        
        try:
            with self.assertRaises(ValueError):
                load_bulletin_data(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_parse_raw_text(self):
        raw = """날짜: 2026년 8월 16일
설교: 선한 이웃은 누구인가 / 누가복음 10:25-37 / 허석헌 목사
광고:
1. 장학금 신청 - 이메일 접수
2. 정기 목회운영위원회
"""
        data = parse_raw_text_to_dict(raw)
        self.assertEqual(data["metadata"]["date_korean"], "2026년 8월 16일")
        self.assertEqual(data["worship_1"]["sermon_title"], "선한 이웃은 누구인가")
        self.assertEqual(data["worship_1"]["scripture"], "누가복음 10:25-37")
        self.assertEqual(data["worship_1"]["preacher"], "허석헌 목사")
        self.assertEqual(len(data["announcements"]), 2)
        self.assertEqual(data["announcements"][0]["title"], "장학금 신청")
        self.assertEqual(data["announcements"][0]["content"], "이메일 접수")

    def test_valid_6_and_7_tier_announcements_sections(self):
        valid_6 = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": [{"title": "가상모임", "content": "13:00"}]},
                {"title": "2. 함께 만드는 향린", "items": [{"title": "가상안내", "content": "상시"}]},
                {"title": "3. 이번주 일정 안내", "date_range": "11/16(월)-11/22(일)", "items": []},
                {"title": "4. 이후 일정 안내", "items": []},  # 빈 이후 일정 헤더 유지 허용
                {"title": "5. 에큐메니칼 소식", "items": []},
                {"title": "6. 감사헌금", "items": ["가상교우A 가상교우B"]},
            ],
        }
        self.assertTrue(validate_bulletin_data(valid_6))

        valid_7 = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": []},
                {"title": "2. 교우 소식", "items": [{"title": "가상소식", "content": "가상내용"}]},
                {"title": "3. 함께 만드는 향린", "items": []},
                {"title": "4. 이번주 일정 안내", "items": []},
                {"title": "5. 이후 일정 안내", "items": []},
                {"title": "6. 에큐메니칼 소식", "items": []},
                {"title": "7. 감사헌금", "items": []},
            ],
        }
        self.assertTrue(validate_bulletin_data(valid_7))

    def test_invalid_announcements_sections_and_legacy_types_rejected(self):
        # 1. sections 타입 오류
        with self.assertRaises(ValueError):
            validate_bulletin_data({"metadata": {"date_compact": "20261115"}, "announcements_sections": "invalid"})

        # 2. 이후 일정 안내 헤더 생략
        missing_future = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": []},
                {"title": "2. 함께 만드는 향린", "items": []},
                {"title": "3. 이번주 일정 안내", "items": []},
                {"title": "4. 에큐메니칼 소식", "items": []},
                {"title": "5. 감사헌금", "items": []},
            ],
        }
        with self.assertRaises(ValueError):
            validate_bulletin_data(missing_future)

        # 3. 임의 섹션명
        unknown_sec = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 임의범주", "items": []},
                {"title": "2. 함께 만드는 향린", "items": []},
                {"title": "3. 이번주 일정 안내", "items": []},
                {"title": "4. 이후 일정 안내", "items": []},
                {"title": "5. 에큐메니칼 소식", "items": []},
                {"title": "6. 감사헌금", "items": []},
            ],
        }
        with self.assertRaises(ValueError):
            validate_bulletin_data(unknown_sec)

        # 4. 순서 뒤바뀜
        wrong_order = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": []},
                {"title": "2. 이번주 일정 안내", "items": []},
                {"title": "3. 함께 만드는 향린", "items": []},
                {"title": "4. 이후 일정 안내", "items": []},
                {"title": "5. 에큐메니칼 소식", "items": []},
                {"title": "6. 감사헌금", "items": []},
            ],
        }
        with self.assertRaises(ValueError):
            validate_bulletin_data(wrong_order)

        # 5. 번호 불일치 (7단 삽입 후 번호 미밀림)
        wrong_numbering = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": []},
                {"title": "2. 교우 소식", "items": []},
                {"title": "2. 함께 만드는 향린", "items": []},
                {"title": "3. 이번주 일정 안내", "items": []},
                {"title": "4. 이후 일정 안내", "items": []},
                {"title": "5. 에큐메니칼 소식", "items": []},
                {"title": "6. 감사헌금", "items": []},
            ],
        }
        with self.assertRaises(ValueError):
            validate_bulletin_data(wrong_numbering)

        # 6. 항목(item) 타입 오류
        bad_item_type = {
            "metadata": {"date_compact": "20261115"},
            "announcements_sections": [
                {"title": "1. 오늘 일정 안내", "items": [12345]},
                {"title": "2. 함께 만드는 향린", "items": []},
                {"title": "3. 이번주 일정 안내", "items": []},
                {"title": "4. 이후 일정 안내", "items": []},
                {"title": "5. 에큐메니칼 소식", "items": []},
                {"title": "6. 감사헌금", "items": []},
            ],
        }
        with self.assertRaises(ValueError):
            validate_bulletin_data(bad_item_type)

        # 7. legacy announcements와 announcements_sections 동시 혼용 또는 잘못된 타입
        with self.assertRaises(ValueError):
            validate_bulletin_data({"metadata": {"date_compact": "20261115"}, "announcements": "invalid"})

        with self.assertRaises(ValueError):
            validate_bulletin_data({
                "metadata": {"date_compact": "20261115"},
                "announcements": [{"title": "가상광고", "content": "내용"}],
                "announcements_sections": [
                    {"title": "1. 오늘 일정 안내", "items": []},
                    {"title": "2. 함께 만드는 향린", "items": []},
                    {"title": "3. 이번주 일정 안내", "items": []},
                    {"title": "4. 이후 일정 안내", "items": []},
                    {"title": "5. 에큐메니칼 소식", "items": []},
                    {"title": "6. 감사헌금", "items": []},
                ],
            })

    def test_extract_date_mentions_shared_resolution(self):
        ref = datetime.date(2026, 11, 15)

        # 1. '작년 11/18(화)' -> 2025-11-18 과거 참조로 확정(2026-11-18 아님)
        m_past = extract_date_mentions("작년 11/18(화) 간담회", ref)
        self.assertEqual(len(m_past), 1)
        self.assertEqual(m_past[0].status, "confirmed")
        self.assertEqual(m_past[0].resolved_date, datetime.date(2025, 11, 18))
        self.assertTrue(m_past[0].is_historical_ref)

        # 2. '참가비 5/6 지원' 등 비용·비율 표현 -> 날짜 추출 제외([])
        self.assertEqual(extract_date_mentions("참가비 5/6 지원", ref), [])
        self.assertEqual(extract_date_mentions("회비의 3/5 보조, 재적 2/3 이상", ref), [])

        # 3. 근거 부족 단독 슬래시 -> ambiguous_token(resolved_date=None)
        m_amb = extract_date_mentions("5/6 별도 안내", ref)
        self.assertEqual(len(m_amb), 1)
        self.assertEqual(m_amb[0].status, "ambiguous_token")
        self.assertIsNone(m_amb[0].resolved_date)

        # 4. 문맥만으로 연도를 확정할 수 없는 날짜 -> unconfirmed(resolved_date=None)
        m_unc = extract_date_mentions("9/2(화) 모임", ref)
        self.assertEqual(len(m_unc), 1)
        self.assertEqual(m_unc[0].status, "unconfirmed")
        self.assertIsNone(m_unc[0].resolved_date)

        # 5. 연말 다음 주일(2026-12-27 기준 1/3(일)) -> 2027-01-03 확정
        m_ye = extract_date_mentions("1/3(일) 13:00", datetime.date(2026, 12, 27))
        self.assertEqual(len(m_ye), 1)
        self.assertEqual(m_ye[0].status, "confirmed")
        self.assertEqual(m_ye[0].resolved_date, datetime.date(2027, 1, 3))


if __name__ == "__main__":
    unittest.main()
