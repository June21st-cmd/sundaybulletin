"""Unit tests for Korean spelling, typos, duplication, and bracket matching."""
import unittest

from src.reviewer.models import IssueLevel
from src.reviewer.spelling import KoreanSpellChecker


class TestKoreanSpellChecker(unittest.TestCase):
    """Test suite for KoreanSpellChecker."""

    def test_typo_detection(self):
        """Test detection of common Korean typos."""
        sample_data = {
            "announcements_sections": [
                {
                    "title": "1. 오늘 일정 안내",
                    "items": [
                        {"title": "회의", "content": "일정이 변경되서 14시에 모입니다."},
                        {"title": "일정 안내", "content": "몇일 동안 진행되는 행사입니다."},
                        {"title": "신청 안내", "content": "꼭 참석해 주시길 바램입니다."},
                        {"title": "봉사자 모임", "content": "내일 뵈요."},
                        {"title": "참여 안내", "content": "제가 도와드릴께요."},
                    ]
                }
            ]
        }
        checker = KoreanSpellChecker(sample_data)
        issues = checker.check_all()

        typo_texts = [i.title + " " + i.message for i in issues]
        joined = " ".join(typo_texts)
        self.assertTrue("되서" in joined or "되/돼" in joined)
        self.assertTrue("몇일" in joined or "며칠" in joined)
        self.assertTrue("바램" in joined or "바람" in joined)
        self.assertTrue("뵈요" in joined or "봬요" in joined)
        self.assertTrue("드릴께요" in joined or "드릴게요" in joined)

    def test_word_duplication(self):
        """Test detection of duplicated words and particles."""
        sample_data = {
            "announcements_sections": [
                {
                    "title": "2. 함께 만드는 향린",
                    "items": [
                        {"title": "도서관", "content": "향우실 향우실 모임이 있습니다."},
                        {"title": "모임 안내", "content": "청년들을를 위한 자리입니다."},
                    ]
                }
            ]
        }
        checker = KoreanSpellChecker(sample_data)
        issues = checker.check_all()

        titles = [i.title for i in issues]
        self.assertTrue(any("단어 중복" in t for t in titles))
        self.assertTrue(any("조사 중복" in t or "겹조사" in t for t in titles))

    def test_bracket_mismatch(self):
        """Test detection of unclosed brackets and quotes."""
        sample_data = {
            "announcements_sections": [
                {
                    "title": "3. 이번주 일정 안내",
                    "items": [
                        {"title": "세미나", "content": "향우실(1층 에서 열립니다."},
                        {"title": "도서", "content": "〈난민의 사도 바울 책을 읽습니다."},
                        {"title": "행사", "content": "“새로운 만남 행사에 초대합니다."},
                    ]
                }
            ]
        }
        checker = KoreanSpellChecker(sample_data)
        issues = checker.check_all()

        bracket_issues = [i for i in issues if "문장부호" in i.category or "괄호" in i.title or "따옴표" in i.title]
        self.assertGreaterEqual(len(bracket_issues), 3)

    def test_whitelist_protection(self):
        """Church proper nouns and liturgical repetitions should not trigger false alarms."""
        sample_data = {
            "metadata": {"season": "창조절 둘째주일"},
            "worship": {
                "gloria": "영광 영광 아멘",
                "responsive_hymn": "주- 님을 찾습니다",
            },
            "announcements_sections": [
                {
                    "title": "1. 오늘 일정 안내",
                    "items": [
                        {"title": "신도회", "content": "청녀 희녀 장녀 회의를 진행합니다."},
                        {"title": "연극", "content": "안병무 박사 30주기 연극 〈선천댁〉 안내입니다."},
                        {"title": "차츰차츰", "content": "하나하나 차츰차츰 준비해 나갑니다."},
                    ]
                }
            ]
        }
        checker = KoreanSpellChecker(sample_data)
        issues = checker.check_all()

        # None of the church proper nouns should trigger errors
        for issue in issues:
            self.assertNotIn("선천댁", issue.message)
            self.assertNotIn("청녀", issue.message)
            self.assertNotIn("영광 영광", issue.message)
            self.assertNotIn("하나하나", issue.message)


if __name__ == "__main__":
    unittest.main()
