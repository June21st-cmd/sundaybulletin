"""Korean spell checker, typo detector, repetition finder, and bracket matching engine."""
import re
from typing import Any, Dict, List, Tuple

from .models import IssueLevel, ReviewIssue


# 1. 자주 틀리는 한국어 맞춤법 패턴: (정규식, 오탈자, 수정안, 도움말)
COMMON_TYPO_PATTERNS: List[Tuple[str, str, str, str]] = [
    (r"([가-힣]*?)되서(?=[^가-힣]|$)", "되서", "돼서", "‘되- + -어서’의 축약형은 ‘돼서’로 표기합니다."),
    (r"([가-힣]*?)됬([가-힣]*)", "됬", "됐", "‘되- + -었-’의 축약형은 ‘됐’으로 표기합니다."),
    (r"(?:^|[^가-힣])안되([,.\s]|$)", "안되", "안돼", "문장의 끝이나 단독 쉼표 앞에서는 ‘안돼’로 표기합니다."),
    (r"(?:^|[^가-힣])되요([,.\s]|$)", "되요", "돼요", "‘되- + -어요’의 축약형은 ‘돼요’로 표기합니다."),
    (r"(?:^|[^가-힣])안되요([,.\s]|$)", "안되요", "안돼요", "‘안돼요’로 표기합니다."),
    (r"(?:^|[^가-힣])몇일(?=[^가-힣]|$)", "몇일", "며칠", "‘몇일’은 표준어가 아니며 항상 ‘며칠’로 표기합니다. (한글 맞춤법 제39항)"),
    (r"(?:^|[^가-힣])바램([가-힣]*)", "바램", "바람", "‘바라다’의 명사형은 ‘바람’이 표준어입니다."),
    (r"(?:^|[^가-힣])뵈요([,.\s]|$)", "뵈요", "봬요", "‘뵈- + -어요’의 축약형은 ‘봬요’로 표기합니다."),
    (r"어의없", "어의없", "어이없", "‘어이없다’ 또는 ‘어처구니없다’가 표준어입니다."),
    (r"(?:^|[^가-힣])금새(?=[^가-힣]|$)", "금새", "금세", "‘지금 바로’의 뜻인 ‘금시에’의 축약형은 ‘금세’입니다."),
    (r"왠만", "왠만", "웬만", "‘우연이나 정도’를 나타낼 때는 ‘웬만’으로 표기합니다."),
    (r"(?:^|[^가-힣])왠일(?=[^가-힣]|$)", "왠일", "웬일", "‘어찌 된 일’을 뜻할 때는 ‘웬일’로 표기합니다."),
    (r"희안", "희안", "희한", "‘드물거나 신기함’을 뜻할 때는 ‘희한(稀罕)’으로 표기합니다."),
    (r"(?:^|[^가-힣])어떻해(?=[^가-힣]|$)", "어떻해", "어떡해", "‘어떻게 해’의 축약형은 ‘어떡해’로 표기합니다."),
    (r"삼가해", "삼가해", "삼가", "기본형이 ‘삼가다’이므로 ‘삼가’로 표기합니다."),
    (r"(?:^|[^가-힣])일찌기(?=[^가-힣]|$)", "일찌기", "일찍이", "‘일찍이’가 표준어입니다."),
    (r"(?:^|[^가-힣])개재(?=[^가-힣]|되|하|$)", "개재", "게재", "글이나 알림을 싣는 것은 ‘게재(揭載)’입니다."),
    (r"단언컨데", "단언컨데", "단언컨대", "어미 ‘-건대/-컨대’는 ‘-대’로 표기합니다."),
    (r"생각컨대", "생각컨대", "생각건대", "‘생각건대’가 올바른 표기입니다."),
    (r"널부러", "널부러", "널브러", "‘널브러지다’가 표준어입니다."),
    (r"치뤘", "치뤘", "치렀", "‘치르다’의 과거형은 ‘치렀다’입니다."),
]

# 2. 겹조사/조사 중복 오류 패턴
DUPLICATE_PARTICLES: List[Tuple[str, str, str]] = [
    (r"([가-힣]+)을를(?=[^가-힣]|$)", "을를", "‘을’ 또는 ‘를’ 하나만 사용해야 합니다."),
    (r"([가-힣]+)이가(?=[^가-힣]|$)", "이가", "‘이’ 또는 ‘가’ 하나만 사용해야 합니다. (이/가 병기는 슬래시 사용)"),
    (r"([가-힣]+)은는(?=[^가-힣]|$)", "은는", "‘은’ 또는 ‘는’ 하나만 사용해야 합니다."),
    (r"([가-힣]+)에서에서(?=[^가-힣]|$)", "에서에서", "조사 ‘에서’가 중복되었습니다."),
    (r"([가-힣]+)에게에게(?=[^가-힣]|$)", "에게에게", "조사 ‘에게’가 중복되었습니다."),
    (r"([가-힣]+)로으로(?=[^가-힣]|$)", "로으로", "‘로’ 또는 ‘으로’ 하나만 사용해야 합니다."),
]

# 3. 단어 중복 허용 목록 (강조나 고유 표현)
DUPLICATION_WHITELIST = {
    "영광", "아멘", "차츰", "하나", "모두", "반짝", "조목", "땀", "길이",
    "두루", "방방", "곳곳", "끼리", "줄줄", "송이", "주", "다시", "꼭"
}

# 4. 문장 부호 짝 (열림, 닫힘, 명칭)
BRACKET_PAIRS = [
    ("(", ")", "소괄호"),
    ("[", "]", "대괄호"),
    ("{", "}", "중괄호"),
    ("“", "”", "큰따옴표"),
    ("〈", "〉", "홑화살괄호"),
    ("《", "》", "겹화살괄호"),
    ("「", "」", "낫표"),
    ("『", "』", "겹낫표"),
]


def extract_labeled_texts(data: Any, path: str = "") -> List[Tuple[str, str]]:
    """Extract texts with their hierarchical location label."""
    items = []
    if isinstance(data, dict):
        if "announcements_sections" in data:
            for sec in data.get("announcements_sections", []):
                sec_title = sec.get("title", "소식")
                for it in sec.get("items", []):
                    if isinstance(it, dict):
                        it_title = it.get("title", "")
                        loc = f"{sec_title} > {it_title}" if it_title else sec_title
                        if it.get("title"):
                            items.append((loc, it.get("title")))
                        if it.get("content"):
                            items.append((loc, it.get("content")))
                    else:
                        items.append((sec_title, str(it)))
        else:
            for k, v in data.items():
                new_path = f"{path} > {k}" if path else str(k)
                items.extend(extract_labeled_texts(v, new_path))
    elif isinstance(data, list):
        for it in data:
            items.extend(extract_labeled_texts(it, path))
    elif isinstance(data, str) and data.strip():
        items.append((path or "본문", data.strip()))
    return items


class KoreanSpellChecker:
    """Validator detecting typos, word/particle duplication, and bracket mismatches."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.labeled_texts = extract_labeled_texts(data)

    def check_all(self) -> List[ReviewIssue]:
        """Run all Korean spelling, duplication, and punctuation checks."""
        issues: List[ReviewIssue] = []
        issues.extend(self.check_common_typos())
        issues.extend(self.check_duplications())
        issues.extend(self.check_bracket_matching())
        return issues

    def check_common_typos(self) -> List[ReviewIssue]:
        """Check for common Korean typos and confusion words."""
        issues = []
        for location, text in self.labeled_texts:
            for pattern, wrong, right, explanation in COMMON_TYPO_PATTERNS:
                for match in re.finditer(pattern, text):
                    full_match = match.group(0).strip()
                    # Clean punctuation
                    clean_match = re.sub(r"^[^\w가-힣]+|[^\w가-힣]+$", "", full_match)
                    if not clean_match:
                        clean_match = full_match

                    # Compute suggestion
                    sugg = clean_match.replace(wrong, right)
                    if sugg == clean_match:
                        sugg = right

                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="국어맞춤법",
                        location=location or "본문",
                        title=f"맞춤법 확인 권장: '{clean_match}'",
                        message=explanation,
                        suggestion=f"'{clean_match}' ➔ '{sugg}'"
                    ))

            # 어미 종결 표기 (-ㄹ게요, -ㄹ게, -ㄹ지)
            for match in re.finditer(r"\b([가-힣]*?)([가-힣])(께요|께|찌)(?=[^가-힣]|$)", text):
                prefix = match.group(1)
                ch = match.group(2)
                ending = match.group(3)
                # Check if preceding syllable has ㄹ 받침: (code - 0xAC00) % 28 == 8
                if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 == 8:
                    repl = {"께요": "게요", "께": "게", "찌": "지"}[ending]
                    wrong_word = match.group(0)
                    right_word = f"{prefix}{ch}{repl}"
                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="국어맞춤법",
                        location=location or "본문",
                        title=f"맞춤법 확인 권장: '{wrong_word}'",
                        message=f"평서형/의문형 어미는 ‘-{repl}’로 표기합니다. (예: {right_word})",
                        suggestion=f"'{wrong_word}' ➔ '{right_word}'"
                    ))
        return issues

    def check_duplications(self) -> List[ReviewIssue]:
        """Check for accidentally duplicated words and particles."""
        issues = []
        for location, text in self.labeled_texts:
            # 1. 겹조사 점검
            for pat, dup_name, msg in DUPLICATE_PARTICLES:
                for match in re.finditer(pat, text):
                    full_word = match.group(0).strip()
                    issues.append(ReviewIssue(
                        level=IssueLevel.WARNING,
                        category="국어맞춤법",
                        location=location or "본문",
                        title=f"조사 중복 오류: '{full_word}'",
                        message=msg,
                        suggestion=f"중복 조사 '{dup_name}' 수정"
                    ))

            # 2. 2글자 이상 단어 연속 중복 점검 (예: '향우실 향우실')
            for match in re.finditer(r"\b([가-힣]{2,})\s+\1\b", text):
                word = match.group(1)
                if word in DUPLICATION_WHITELIST:
                    continue
                full_match = match.group(0)
                issues.append(ReviewIssue(
                    level=IssueLevel.WARNING,
                    category="국어맞춤법",
                    location=location or "본문",
                    title=f"단어 중복 입력: '{full_match}'",
                    message=f"동일한 단어 '{word}'이(가) 연속으로 중복 입력되었습니다.",
                    suggestion=f"'{word}' 1회만 기입"
                ))
        return issues

    def check_bracket_matching(self) -> List[ReviewIssue]:
        """Check for unclosed or mismatched brackets and quotes."""
        issues = []
        for location, text in self.labeled_texts:
            lines = text.splitlines()
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                for open_ch, close_ch, b_name in BRACKET_PAIRS:
                    open_count = line_str.count(open_ch)
                    close_count = line_str.count(close_ch)
                    if open_count != close_count:
                        if open_count > close_count:
                            issues.append(ReviewIssue(
                                level=IssueLevel.WARNING,
                                category="문장부호",
                                location=location or "본문",
                                title=f"닫는 {b_name}('{close_ch}') 누락 의심",
                                message=f"여는 {b_name}('{open_ch}')이 {open_count}개 있으나 닫는 기호는 {close_count}개입니다: \"{line_str[:40]}...\"",
                                suggestion=f"닫는 기호 '{close_ch}' 추가"
                            ))
                        else:
                            issues.append(ReviewIssue(
                                level=IssueLevel.WARNING,
                                category="문장부호",
                                location=location or "본문",
                                title=f"여는 {b_name}('{open_ch}') 누락 의심",
                                message=f"닫는 {b_name}('{close_ch}')이 {close_count}개 있으나 여는 기호는 {open_count}개입니다: \"{line_str[:40]}...\"",
                                suggestion=f"여는 기호 '{open_ch}' 확인"
                            ))
        return issues
