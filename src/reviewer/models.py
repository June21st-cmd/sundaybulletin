"""Data models for Sunday bulletin review issues and reports."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IssueLevel(str, Enum):
    """Severity level of a review issue."""
    ERROR = "ERROR"        # Must be fixed before printing (규칙 위반, 잘못된 날짜 등)
    WARNING = "WARNING"    # Check required (미완성 항목, 지난주와 불일치 등)
    INFO = "INFO"          # Informational notice (버전 간 변경사항 등)


@dataclass
class ReviewIssue:
    """Represents a single issue found during bulletin review."""
    level: IssueLevel
    category: str         # e.g., '고유규칙', '일정/요일', '예배위원', '직전주대조', '버전변경'
    location: str         # e.g., '1면 표지', '2면 예배순서', '5면 공동관심사'
    title: str            # Short issue summary
    message: str          # Detailed description
    suggestion: Optional[str] = None  # Suggested fix or action
    is_temporary_marker: bool = False  # True if it is an unfinished placeholder that should be highlighted in red

    def __str__(self) -> str:
        icon = "🔴" if self.level == IssueLevel.ERROR else ("⚠️" if self.level == IssueLevel.WARNING else "ℹ️")
        sugg = f" ➔ [제안: {self.suggestion}]" if self.suggestion else ""
        return f"{icon} [{self.location}] {self.title}: {self.message}{sugg}"


@dataclass
class BulletinReviewReport:
    """Comprehensive review report containing all detected issues and diffs."""
    target_date: str
    target_version: str
    issues: List[ReviewIssue] = field(default_factory=list)
    diff_summary: Dict[str, Any] = field(default_factory=dict)
    cross_week_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.level == IssueLevel.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == IssueLevel.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.level == IssueLevel.INFO)

    @property
    def temporary_markers(self) -> List[ReviewIssue]:
        return [i for i in self.issues if i.is_temporary_marker]
