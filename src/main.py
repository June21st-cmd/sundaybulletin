"""Main CLI entry point for Sunday Bulletin generator."""
import argparse
import os
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
from src.utils import get_versioned_bulletin_paths
import re

import yaml
from scripts.fetch_session_material import find_latest_session_material
from scripts.validate_bulletin_facts import validate_facts
from src.reviewer.rules import BulletinRuleChecker
from src.reviewer.models import IssueLevel

def is_same_file_path(p1: str | Path, p2: str | Path) -> bool:
    path1 = Path(p1)
    path2 = Path(p2)
    try:
        if path1.exists() and path2.exists():
            return path1.samefile(path2)
    except Exception:
        pass
    try:
        norm1 = os.path.normcase(os.path.normpath(str(path1.resolve())))
        norm2 = os.path.normcase(os.path.normpath(str(path2.resolve())))
        return norm1 == norm2
    except Exception:
        return False

def run_preflight(data: dict, yaml_path: Path, downloads_dir: Path | None = None) -> bool:
    print("\n🔍 Pre-flight 검증을 시작합니다...")
    
    raw_text_path = None
    potential_raw = None
    m = re.search(r'(\d{4})(\d{2})(\d{2})', yaml_path.name)
    if m:
        raw_name = f"{m.group(1)}-{m.group(2)}-{m.group(3)}_주보원고.md"
        potential_raw = yaml_path.parent / raw_name
        if potential_raw.exists():
            raw_text_path = str(potential_raw)
            
    fact_issues = validate_facts(str(yaml_path), raw_text_path)
    
    checker = BulletinRuleChecker(data)
    rule_issues = checker.check_all()
    
    blocks = []
    warns = []

    # Source Manifest 검사
    m_name = yaml_path.stem + "_manifest.yaml"
    manifest_path = yaml_path.parent / m_name
    
    if not manifest_path.exists():
        blocks.append(f"[Source Manifest 누락] {m_name} 파일이 존재하지 않습니다. Source Collection 단계가 생략되었습니다.")
    else:
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = yaml.safe_load(f)
                sm = manifest_data.get("source_manifest", {})
                session = sm.get("session_material", {})
                mf_raw = session.get("file_path")
                if not mf_raw:
                    blocks.append(f"[Source Manifest 오류] 정기당회 자료 file_path가 없습니다.")
                else:
                    latest_res = find_latest_session_material(downloads_dir)
                    if latest_res is None:
                        blocks.append(
                            "[최신 정기당회 결정 실패] 시스템에서 정기당회 자료를 찾을 수 없습니다. "
                            "Downloads 폴더를 확인해주세요."
                        )
                    elif isinstance(latest_res, dict) and latest_res.get("error"):
                        err_msg = latest_res.get("message", "최신 정기당회 자료를 확정할 수 없습니다.")
                        blocks.append(
                            f"[최신 정기당회 결정 실패] {err_msg} "
                            "Source Collection을 다시 실행하여 확인해주세요."
                        )
                    else:
                        latest_path_str = latest_res["file_path"]
                        if not is_same_file_path(mf_raw, latest_path_str):
                            blocks.append(
                                f"[Source Manifest 불일치] 최신 정기당회 자료와 불일치합니다.\n"
                                f"    Manifest 자료: {mf_raw}\n"
                                f"    현재 최신 정기당회 자료: {latest_path_str}\n"
                                f"    Source Collection을 다시 실행하여 Manifest를 갱신해야 합니다."
                            )
                
                findings = session.get("findings", [])
                for f_item in findings:
                    if not f_item.get("present_in_memo", True):
                        item_name = f_item.get("item", "알 수 없는 일정")
                        note = f_item.get("note", "")
                        warns.append(f"[특별일정 미기재] 당회 자료에서 '{item_name}'({note}) 일정을 발견했으나 당주 원고에 없습니다. 특별주일 사전공지 대상인지 확인 바랍니다.")
        except Exception as e:
            blocks.append(f"[Source Manifest 파싱 실패] {e}")


    if not raw_text_path:
        warn_msg = f"원고 파일({potential_raw.name if potential_raw else '알 수 없음'})을 찾을 수 없어 원고 대조 검증을 수행하지 못했습니다."
        warns.append(f"[원고 MD 탐색 실패] {warn_msg}")
    
    for issue in fact_issues:
        cat = issue["category"]
        lvl = issue["level"]
        msg = issue["message"]
        
        if "Rule 34" in cat:
            continue
        elif cat == "정례 모임 시간 불일치":
            blocks.append(f"[정례 모임 시간 불일치] {msg}")
        elif cat == "정례 모임 장소 불일치":
            blocks.append(f"[정례 모임 장소 불일치] {msg}")
        elif cat == "정례 모임 장소 누락":
            warns.append(f"[정례 모임 장소 누락] {msg}")
        elif cat == "원고 미언급 항목 (외부자료 임의 추가 의심)":
            warns.append(f"[원고 미언급 항목 추가 의심] {msg}")
        elif cat == "인접 항목 동일 시간 감지 (복붙 확인 요망)":
            warns.append(f"[복붙 오염 의심] {msg}")
        elif lvl == "ERROR":
            blocks.append(f"[{cat}] {msg}")
        elif lvl == "WARNING":
            warns.append(f"[{cat}] {msg}")

    for issue in rule_issues:
        cat = issue.category
        title = issue.title
        msg = issue.message
        
        if cat == "고유규칙" and "전화번호 순서 오류" in title:
            continue
        elif cat == "예배위원" and "미정/공란" in title:
            warns.append(f"[예배위원 공란] {msg}")
        elif cat == "예전찬송" and "예전 찬송 규칙 불일치" in title:
            continue
        elif issue.level == IssueLevel.ERROR:
            blocks.append(f"[{cat}] {msg}")
        elif issue.level == IssueLevel.WARNING:
            warns.append(f"[{cat}] {msg}")

    if warns:
        print("⚠️ [Pre-flight 경고]")
        for w in warns:
            print(f"  - {w}")
    
    if blocks:
        print("\n❌ [Pre-flight 차단] 다음 치명적인 오류가 해결되기 전에는 주보를 생성할 수 없습니다:")
        for b in blocks:
            print(f"  - {b}")
        return False
        
    print("✅ Pre-flight 검증 통과!")
    return True


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
    parser.add_argument(
        "--no-version",
        action="store_true",
        help="Do not add version suffix (_v1, _v2) to output files",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    data_path = Path(args.data)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📖 주보 원고 데이터를 로드합니다: {data_path}")
    data = load_bulletin_data(data_path)
    
    if not run_preflight(data, data_path):
        sys.exit(1)

    # Determine date compact string for output filename
    meta = data.get("metadata", {})
    if isinstance(meta, dict) and meta.get("date_compact"):
        date_str = meta["date_compact"]
    elif data.get("date"):
        date_str = str(data["date"]).replace("-", "")
    else:
        date_str = "latest"

    base_stem = f"[주보] {date_str}"
    if args.no_version:
        out_hwpx = out_dir / f"{base_stem}.hwpx"
        out_pdf = out_dir / f"{base_stem}.pdf"
    else:
        out_hwpx, out_pdf = get_versioned_bulletin_paths(out_dir, base_stem)

    # 1. HWPX Engine Execution
    if args.engine in ["hwpx", "all"]:
        hwpx_tpl = Path(args.hwpx_template)
        if hwpx_tpl.is_file():
            print(f"🖨️ HWPX 템플릿 치환 중: {hwpx_tpl.name}")
            hwpx_engine = HwpxEngine(hwpx_tpl)
            actual_hwpx = hwpx_engine.generate(data, out_hwpx)
            file_size_mb = actual_hwpx.stat().st_size / (1024 * 1024)
            print(f"✅ HWPX 인쇄본 생성 완료: {actual_hwpx} ({file_size_mb:.2f} MB)")
        else:
            print(f"⚠️ HWPX 템플릿이 존재하지 않습니다 ({hwpx_tpl}), HWPX 생성을 건너뜁니다.")

    # 2. Typst Engine Execution
    if args.engine in ["typst", "all"]:
        typst_tpl = Path(args.typst_template)
        if typst_tpl.is_file():
            print(f"🎨 Typst PDF 컴파일 중: {typst_tpl.name}")
            typst_engine = TypstEngine(typst_tpl)
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
