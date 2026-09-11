"""CLI script to review a Sunday bulletin input file."""
import argparse
import glob
from pathlib import Path
import sys

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.parser import load_bulletin_data
from src.reviewer.engine import BulletinReviewer


def find_latest_input_file() -> Path:
    """Find the most recently modified bulletin YAML in input/."""
    candidates = glob.glob("input/bulletin_*.yaml") + glob.glob("data/inputs/bulletin_*.yaml")
    if not candidates:
        raise FileNotFoundError("No bulletin YAML found in input/ or data/inputs/.")
    candidates.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(candidates[0])


def main():
    parser = argparse.ArgumentParser(description="향린교회 주보 지능형 통합 검토 도구")
    parser.add_argument("input_file", nargs="?", help="검토할 주보 YAML 파일 경로 (생략 시 최신 파일 자동 선택)")
    parser.add_argument("--prev-week", help="직전 주 주보 YAML 경로 (생략 시 자동 탐색)")
    parser.add_argument("--prev-version", help="직전 수정본 YAML 경로 (버전 간 변경사항 추적용)")
    parser.add_argument("--version-label", default="초안 v1", help="현재 검토 중인 버전 명칭 (예: '수정본 v2')")
    parser.add_argument("--save-report", action="store_true", help="output/ 폴더에 마크다운 검토 보고서 저장")

    args = parser.parse_args()

    input_path = Path(args.input_file) if args.input_file else find_latest_input_file()
    print(f"🔍 주보 데이터 로드 중: {input_path}")
    current_data = load_bulletin_data(input_path)

    prev_week_data = None
    if args.prev_week:
        prev_week_data = load_bulletin_data(args.prev_week)

    prev_ver_data = None
    if args.prev_version:
        prev_ver_data = load_bulletin_data(args.prev_version)

    reviewer = BulletinReviewer(
        current_data=current_data,
        prev_bulletin_data=prev_week_data,
        prev_version_data=prev_ver_data,
        version_label=args.version_label
    )

    report = reviewer.run_review()
    formatted = reviewer.format_console_report(report)

    # Print to console (handle windows cp949 console safely)
    try:
        print(formatted)
    except UnicodeEncodeError:
        print(formatted.encode("utf-8", errors="replace").decode("utf-8"))

    if args.save_report:
        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"[검토보고서] {report.target_date.replace(' ', '_')}.md"
        report_path.write_text(formatted, encoding="utf-8")
        print(f"\n📄 검토 보고서 저장 완료: {report_path}")


if __name__ == "__main__":
    main()
