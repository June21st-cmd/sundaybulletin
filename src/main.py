"""Main CLI entry point for Sunday Bulletin generator."""
import argparse
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
        help="Target generator engine (hwpx, typst, or all)",
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

    print(f"📖 Loading bulletin data from: {data_path}")
    data = load_bulletin_data(data_path)
    bulletin_date = data.get("date", "bulletin").replace("-", "")

    # 1. HWPX Engine Execution
    if args.engine in ["hwpx", "all"]:
        if Path(args.hwpx_template).is_file():
            print(f"🖨️ Generating HWPX with template: {args.hwpx_template}")
            hwpx_engine = HwpxEngine(args.hwpx_template)
            out_hwpx = out_dir / f"bulletin_{bulletin_date}.hwpx"
            hwpx_engine.generate(data, out_hwpx)
            print(f"✅ HWPX created: {out_hwpx}")
        else:
            print(f"⚠️ HWPX template not found ({args.hwpx_template}), skipping HWPX.")

    # 2. Typst Engine Execution
    if args.engine in ["typst", "all"]:
        if Path(args.typst_template).is_file():
            print(f"🎨 Compiling Typst with template: {args.typst_template}")
            typst_engine = TypstEngine(args.typst_template)
            out_pdf = out_dir / f"bulletin_{bulletin_date}.pdf"
            try:
                typst_engine.compile(out_pdf)
                print(f"✅ Typst PDF created: {out_pdf}")
            except Exception as e:
                print(f"⚠️ Typst compile skipped or failed: {e}")
        else:
            print(f"⚠️ Typst template not found ({args.typst_template}), skipping Typst.")

    print("🎉 All tasks completed successfully.")


if __name__ == "__main__":
    main()
