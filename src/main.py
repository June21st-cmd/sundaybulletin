"""Main CLI entry point for Sunday Bulletin generator."""
import argparse
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.config import DEFAULT_HWPX_TEMPLATE, DEFAULT_TYPST_TEMPLATE, OUTPUT_DIR
from src.hwpx_engine import HwpxEngine
from src.parser import load_bulletin_data
from src.typst_engine import TypstEngine


def parse_args():
    parser = argparse.ArgumentParser(description="Sunday Bulletin Generator CLI")
    parser.add_argument(
        "--data",
        "-d",
        type=str,
        required=True,
        help="Path to weekly bulletin data file (YAML/JSON)",
    )
    parser.add_argument(
        "--engine",
        "-e",
        choices=["hwpx", "typst", "all"],
        default="all",
        help="Target generator engine (hwpx, typst, or all - default: all)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(OUTPUT_DIR),
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--hwpx-template",
        type=str,
        default=str(DEFAULT_HWPX_TEMPLATE),
        help="Path to custom HWPX template",
    )
    parser.add_argument(
        "--typst-template",
        type=str,
        default=str(DEFAULT_TYPST_TEMPLATE),
        help="Path to custom Typst template",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    data_path = Path(args.data)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📖 주보 원고 데이터를 로드합니다: {data_path}")
    data = load_bulletin_data(data_path)

    # Determine date compact string for output filename
    meta = data.get("metadata", {})
    if isinstance(meta, dict) and meta.get("date_compact"):
        date_str = meta["date_compact"]
    elif data.get("date"):
        date_str = str(data["date"]).replace("-", "")
    else:
        date_str = "latest"

    # 1. HWPX Engine Execution
    if args.engine in ["hwpx", "all"]:
        hwpx_tpl = Path(args.hwpx_template)
        if hwpx_tpl.is_file():
            print(f"🖨️ HWPX 템플릿 치환 중: {hwpx_tpl.name}")
            hwpx_engine = HwpxEngine(hwpx_tpl)
            out_hwpx = out_dir / f"[주보] {date_str}.hwpx"
            hwpx_engine.generate(data, out_hwpx)
            file_size_mb = out_hwpx.stat().st_size / (1024 * 1024)
            print(f"✅ HWPX 인쇄본 생성 완료: {out_hwpx} ({file_size_mb:.2f} MB)")
        else:
            print(f"⚠️ HWPX 템플릿이 존재하지 않습니다 ({hwpx_tpl}), HWPX 생성을 건너뜁니다.")

    # 2. Typst Engine Execution
    if args.engine in ["typst", "all"]:
        typst_tpl = Path(args.typst_template)
        if typst_tpl.is_file():
            print(f"🎨 Typst PDF 컴파일 중: {typst_tpl.name}")
            typst_engine = TypstEngine(typst_tpl)
            out_pdf = out_dir / f"[주보] {date_str}.pdf"
            try:
                typst_engine.compile(out_pdf)
                print(f"✅ Typst PDF 생성 완료: {out_pdf}")
            except Exception as e:
                print(f"⚠️ Typst 컴파일 생략 (선택 엔진): {e}")
        else:
            print(f"⚠️ Typst 템플릿이 존재하지 않습니다 ({typst_tpl}), Typst 생성을 건너뜁니다.")

    print("\n🎉 모든 주보 생성 작업이 완료되었습니다.")


if __name__ == "__main__":
    main()
