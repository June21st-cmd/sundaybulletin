"""Unit tests for bulletin data parser and validator."""
import tempfile
import unittest
from pathlib import Path

from src.parser import load_bulletin_data, parse_raw_text_to_dict, validate_bulletin_data


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


if __name__ == "__main__":
    unittest.main()
