"""Integrated bulletin review engine coordinating rule checks, cross-week comparison, and diff tracking."""
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import BulletinReviewReport, IssueLevel, ReviewIssue
from .rules import BulletinRuleChecker
from .cross_week import CrossWeekComparator
from .diff_tracker import VersionDiffTracker


class BulletinReviewer:
    """Main reviewer engine orchestrating all QA dimensions."""

    def __init__(
        self,
        current_data: Dict[str, Any],
        prev_bulletin_data: Optional[Dict[str, Any]] = None,
        prev_version_data: Optional[Dict[str, Any]] = None,
        version_label: str = "초안 v1"
    ):
        self.current = current_data
        self.prev_bulletin = prev_bulletin_data
        self.prev_version = prev_version_data
        self.version_label = version_label

        meta = current_data.get("metadata", {})
        self.target_date = str(meta.get("date_korean") or meta.get("date_compact") or "날짜 미상")

    def run_review(self) -> BulletinReviewReport:
        """Run all review suites and return a structured report."""
        report = BulletinReviewReport(
            target_date=self.target_date,
            target_version=self.version_label
        )

        # 1. 15대 규칙 및 정적 정합성 검사
        rule_checker = BulletinRuleChecker(self.current)
        report.issues.extend(rule_checker.check_all())

        # 2. 직전 주 주보 대조 검사
        comparator = CrossWeekComparator(self.current, self.prev_bulletin)
        cw_issues, cw_summary = comparator.compare()
        report.issues.extend(cw_issues)
        report.cross_week_summary = cw_summary

        # 3. 버전 간 변경사항 추적 (수정본 비교 시)
        if self.prev_version:
            diff_tracker = VersionDiffTracker(self.current, self.prev_version)
            diff_issues, diff_summary = diff_tracker.track_diff()
            report.issues.extend(diff_issues)
            report.diff_summary = diff_summary

        return report

    @staticmethod
    def format_console_report(report: BulletinReviewReport) -> str:
        """Format the report into an easy-to-read, visual dashboard for the user."""
        lines = []
        lines.append("=" * 72)
        lines.append(f"📋 [향린교회 주보 통합 검토 보고서] {report.target_date} ({report.target_version})")
        lines.append("=" * 72)

        # Section 1: 미완성/임시 항목 (빨간색 강조 대상)
        temp_markers = report.temporary_markers
        lines.append("")
        lines.append("🔴 1. 즉시 확인 필요한 미완성 항목 (문서 내 빨간색 표시)")
        if temp_markers:
            for issue in temp_markers:
                sugg = f" ➔ [조치: {issue.suggestion}]" if issue.suggestion else ""
                lines.append(f"  • [{issue.location}] {issue.title}: {issue.message}{sugg}")
        else:
            lines.append("  ✅ 미완성 또는 확인 요망 임시 문구 없음 (모두 확정됨)")

        # Section 2: 직전 주 주보 대조 결과
        lines.append("")
        lines.append("🔄 2. 직전 주 주보 대조 결과")
        cw = report.cross_week_summary
        if cw.get("has_prev_data"):
            # 예배위원 릴레이
            matches = cw.get("duty_relay_matches", [])
            mismatches = cw.get("duty_relay_mismatches", [])
            lines.append("  [예배위원 3주 릴레이]")
            if matches:
                lines.append(f"    ✅ 지난주 예고 일치: {', '.join(matches[:3])} 등 {len(matches)}건")
            if mismatches:
                for mm in mismatches:
                    lines.append(f"    ⚠️ {mm}")

            # 소식 연속성
            expired = cw.get("expired_events_found", [])
            if expired:
                lines.append("  [지나간 일정 점검]")
                for ex in expired:
                    lines.append(f"    ⚠️ 지난 일정 방치 의심: {ex}")

            carried = cw.get("carried_over_announcements", [])
            if carried:
                lines.append("  [이후 일정 ➔ 이번주 승격]")
                for car in carried:
                    lines.append(f"    {car}")
        else:
            lines.append("  ℹ️ 직전 주 주보 원본이 감지되지 않아 단독 규칙 검사만 수행했습니다.")

        # Section 3: 버전 간 변경 사항 (v1 -> v2 ...)
        if report.diff_summary:
            lines.append("")
            lines.append(f"📝 3. 직전 버전 대비 변경 내역 ({report.target_version})")
            diff = report.diff_summary
            if diff.get("added"):
                lines.append("  [새로 반영된 항목]")
                for item in diff["added"]:
                    lines.append(f"    + {item}")
            if diff.get("modified"):
                lines.append("  [수정된 항목]")
                for item in diff["modified"]:
                    lines.append(f"    * {item}")
            if diff.get("removed"):
                lines.append("  [삭제된 항목]")
                for item in diff["removed"]:
                    lines.append(f"    - {item}")

        # Section 4: 15대 고유 규칙 및 오류 점검
        other_errors = [i for i in report.issues if i.level == IssueLevel.ERROR and not i.is_temporary_marker]
        other_warnings = [i for i in report.issues if i.level == IssueLevel.WARNING and not i.is_temporary_marker]

        lines.append("")
        lines.append("🔍 4. 향린 15대 고유 규칙 및 오류 점검")
        if not other_errors and not other_warnings:
            lines.append("  ✅ 전화번호, 신도회 명칭, 층수, 요일 등 모든 규칙 통과!")
        else:
            for err in other_errors:
                lines.append(f"  ❌ [{err.location}] {err.title}: {err.message} (제안: {err.suggestion})")
            for warn in other_warnings:
                lines.append(f"  ⚠️ [{warn.location}] {warn.title}: {warn.message}")

        lines.append("")
        lines.append("-" * 72)
        status_text = "🟢 인쇄 가능 수준" if report.error_count == 0 and not temp_markers else "🟠 보완 필요"
        lines.append(f"📊 검토 종합 요약: 오류 {report.error_count}건 | 확인요망 {report.warning_count}건 ➔ [{status_text}]")
        lines.append("=" * 72)

        return "\n".join(lines)
