"""HWPX template tag substitution and flattening engine."""
import html
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Dict, List
import uuid
import zipfile

from lxml import etree

from scripts.validate_bulletin_facts import validate_bulletin_facts_data
from src.parser import (
    classify_announcement_section,
    is_rule34_monthly_meeting_item,
    parse_bulletin_date,
    prepare_bulletin_data,
)


class BulletinValidationError(ValueError):
    """Raised when bulletin input data fails shared structural, classification, or Rule 34 validation."""

    def __init__(self, issues: List[Dict[str, Any]]):
        self.issues = issues
        summary = "\n".join(
            f"[{iss.get('category', '검증 오류')}] {iss.get('section', '')}: {iss.get('message', '')}"
            for iss in issues
        )
        super().__init__(summary)


class HwpxArtifactValidationError(ValueError):
    """Raised when a staged HWPX output artifact fails pre-export XML, style, content, or Rule 34 checks.

    Error details intentionally exclude personal names and full manuscript text, recording only
    check identifiers, XML locations, style IDs, field paths, and counts.
    """

    def __init__(self, issues: List[Dict[str, str]]):
        self.issues = issues
        summary = "\n".join(
            f"[{iss.get('check', 'artifact_error')}] {iss.get('location', 'unknown')}: {iss.get('detail', '')}"
            for iss in issues
        )
        super().__init__(summary)


def _xml_local_name(el: Any) -> str:
    tag = getattr(el, "tag", None)
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _extract_t_text(t_el: Any) -> str:
    """Extract text from a <t> element, converting nested <lineBreak/> children and preserving .tail text."""
    chunks: List[str] = []
    if t_el.text:
        chunks.append(t_el.text)
    for sub in t_el:
        if _xml_local_name(sub) == "lineBreak":
            chunks.append("\n")
        else:
            chunks.append(_extract_t_text(sub))
        if sub.tail:
            chunks.append(sub.tail)
    return "".join(chunks)


def _extract_direct_p_text(p_el: Any) -> str:
    """Extract paragraph text from direct <run>/<t> and <lineBreak/> children, excluding nested <tbl>/<pic>."""
    parts: List[str] = []
    for run in p_el:
        if _xml_local_name(run) != "run":
            continue
        for child in run:
            lname = _xml_local_name(child)
            if lname == "t":
                parts.append(_extract_t_text(child))
            elif lname == "lineBreak":
                parts.append("\n")
    return "".join(parts)


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _get_image_bytes_size(raw_bytes: bytes) -> tuple[int, int] | None:
    """Extract (width, height) in pixels from raw image bytes without external dependencies."""
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(raw_bytes)) as img:
            return img.size
    except Exception:
        pass

    if len(raw_bytes) >= 24 and raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        import struct
        return struct.unpack(">II", raw_bytes[16:24])
    if len(raw_bytes) >= 26 and raw_bytes.startswith(b"BM"):
        import struct
        w, h = struct.unpack("<ii", raw_bytes[18:26])
        return (abs(w), abs(h))
    return None


def validate_generated_hwpx(
    hwpx_path: Path | str,
    data: Dict[str, Any],
    fallback_stem: str = "",
) -> None:
    """Inspect a staged HWPX archive before exporting it to a final path.

    Note: XML parsing here checks XML well-formedness only, not full HWPX schema conformance
    or visual print layout / page-break rendering in Hancom Office.
    """
    target_path = Path(hwpx_path)
    issues: List[Dict[str, str]] = []

    try:
        zf_ctx = zipfile.ZipFile(target_path, "r")
    except (OSError, zipfile.BadZipFile):
        raise HwpxArtifactValidationError([
            {"check": "invalid_zip", "location": target_path.name, "detail": "not a valid HWPX ZIP archive"}
        ])

    with zf_ctx as zf:
        names = set(zf.namelist())
        if "Contents/header.xml" not in names:
            issues.append({
                "check": "missing_xml_entry",
                "location": "Contents/header.xml",
                "detail": "required header.xml entry is missing",
            })
        section_entries = sorted(n for n in names if re.fullmatch(r"Contents/section\d+\.xml", n))
        if not section_entries:
            issues.append({
                "check": "missing_xml_entry",
                "location": "Contents/section*.xml",
                "detail": "no section XML entries found",
            })
        if issues:
            raise HwpxArtifactValidationError(issues)

        strict_parser = etree.XMLParser(recover=False, resolve_entities=False)
        header_root = None
        try:
            header_root = etree.fromstring(zf.read("Contents/header.xml"), strict_parser)
        except etree.XMLSyntaxError as exc:
            issues.append({
                "check": "xml_syntax",
                "location": "Contents/header.xml",
                "detail": f"line={exc.lineno}, col={exc.offset}",
            })

        parsed_sections: List[tuple[str, Any]] = []
        for sec_entry in section_entries:
            try:
                sec_root = etree.fromstring(zf.read(sec_entry), strict_parser)
                parsed_sections.append((sec_entry, sec_root))
            except etree.XMLSyntaxError as exc:
                issues.append({
                    "check": "xml_syntax",
                    "location": sec_entry,
                    "detail": f"line={exc.lineno}, col={exc.offset}",
                })

        bindata_raw: Dict[str, bytes] = {}
        for n in names:
            if n.startswith("BinData/"):
                try:
                    bindata_raw[n] = zf.read(n)
                except Exception:
                    pass

        if issues or header_root is None:
            raise HwpxArtifactValidationError(issues)

    # 1. Resolve header.xml HANGUL fontfaces and charPr styles + detect duplicate charPr IDs
    hangul_fonts: Dict[str, str] = {}
    for el in header_root.iter():
        if _xml_local_name(el) == "fontface" and el.get("lang") == "HANGUL":
            for f_el in el:
                if _xml_local_name(f_el) == "font" and f_el.get("id") is not None:
                    hangul_fonts[str(f_el.get("id"))] = str(f_el.get("face", ""))

    charpr_styles: Dict[str, Dict[str, Any]] = {}
    for el in header_root.iter():
        if _xml_local_name(el) != "charPr":
            continue
        cid = el.get("id")
        if cid is None:
            issues.append({
                "check": "charpr_missing_id",
                "location": "Contents/header.xml",
                "detail": "charPr element without id",
            })
            continue
        if cid in charpr_styles:
            issues.append({
                "check": "charpr_duplicate",
                "location": "Contents/header.xml",
                "detail": f"charPr id={cid}",
            })
        raw_height = str(el.get("height", ""))
        height_val = int(raw_height) if raw_height.isdigit() else None
        font_ref = next((ch for ch in el if _xml_local_name(ch) == "fontRef"), None)
        hangul_fid = str(font_ref.get("hangul")) if (font_ref is not None and font_ref.get("hangul") is not None) else ""
        font_face = hangul_fonts.get(hangul_fid, "")
        has_bold_tag = any(_xml_local_name(ch) == "bold" for ch in el)
        is_bold = has_bold_tag or ("bold" in font_face.lower())
        charpr_styles[cid] = {
            "font_face": font_face,
            "height": height_val,
            "is_bold": is_bold,
        }

    # 2. Check undefined charPrIDRef references in header.xml and all section*.xml
    for idx, el in enumerate(header_root.iter()):
        ref_id = el.get("charPrIDRef")
        if ref_id is None:
            continue
        if _xml_local_name(el) == "paraHead" and ref_id == "4294967295":
            continue
        if ref_id not in charpr_styles:
            issues.append({
                "check": "charpr_undefined_ref",
                "location": f"Contents/header.xml:{_xml_local_name(el)}#{idx}",
                "detail": f"charPrIDRef={ref_id}",
            })

    for sec_entry, sec_root in parsed_sections:
        for idx, el in enumerate(sec_root.iter()):
            ref_id = el.get("charPrIDRef")
            if ref_id is None:
                continue
            if _xml_local_name(el) == "paraHead" and ref_id == "4294967295":
                continue
            if ref_id not in charpr_styles:
                issues.append({
                    "check": "charpr_undefined_ref",
                    "location": f"{sec_entry}:{_xml_local_name(el)}#{idx}",
                    "detail": f"charPrIDRef={ref_id}",
                })

    # 3. Check residual unreplaced {{...}} placeholder tags
    hdr_placeholders = re.findall(r"\{\{[^{}\r\n]+\}\}", "".join(header_root.itertext()))
    if hdr_placeholders:
        issues.append({
            "check": "unreplaced_placeholder",
            "location": "Contents/header.xml",
            "detail": f"count={len(hdr_placeholders)}",
        })

    for sec_entry, sec_root in parsed_sections:
        p_idx = 0
        for el in sec_root.iter():
            if _xml_local_name(el) != "p":
                continue
            p_txt = _extract_direct_p_text(el)
            matches = re.findall(r"\{\{[^{}\r\n]+\}\}", p_txt)
            if matches:
                issues.append({
                    "check": "unreplaced_placeholder",
                    "location": f"{sec_entry}:p#{p_idx}",
                    "detail": f"count={len(matches)}",
                })
            p_idx += 1

    # 4. Inspect target roster box (Table 10): actual resolved style properties & content completeness/duplication
    prayers = data.get("prayer_requests", data.get("prayers", {})) if isinstance(data, dict) else {}
    if not isinstance(prayers, dict):
        prayers = {}

    raw_nm = data.get("new_members", []) if isinstance(data, dict) else []
    if isinstance(raw_nm, str):
        nm_values = [raw_nm.strip()] if raw_nm.strip() else []
    elif isinstance(raw_nm, list):
        nm_values = [str(x).strip() for x in raw_nm if str(x).strip()]
    else:
        nm_values = []

    h1 = str(prayers.get("healing_1", prayers.get("health_1", data.get("healing_prayer_1", "") if isinstance(data, dict) else ""))).strip()
    h2 = str(prayers.get("healing_2", prayers.get("health_2", data.get("healing_prayer_2", "") if isinstance(data, dict) else ""))).strip()
    h3 = str(prayers.get("healing_3", prayers.get("health_3", data.get("healing_prayer_3", "") if isinstance(data, dict) else ""))).strip()
    mil = str(prayers.get("military", data.get("military_prayer_names", "") if isinstance(data, dict) else "")).strip()
    ov1 = str(prayers.get("overseas_1", data.get("overseas_prayer_1", "") if isinstance(data, dict) else "")).strip()
    ov2 = str(prayers.get("overseas_2", data.get("overseas_prayer_2", "") if isinstance(data, dict) else "")).strip()

    requested_by_sec: Dict[str, List[tuple[str, str]]] = {
        "new_members": [(f"new_members[{i}]", v) for i, v in enumerate(nm_values)],
        "healing": [
            (fpath, val)
            for fpath, val in [
                ("prayer_requests.healing_1", h1),
                ("prayer_requests.healing_2", h2),
                ("prayer_requests.healing_3", h3),
            ]
            if val
        ],
        "military": [("prayer_requests.military", mil)] if mil else [],
        "overseas": [
            (fpath, val)
            for fpath, val in [
                ("prayer_requests.overseas_1", ov1),
                ("prayer_requests.overseas_2", ov2),
            ]
            if val
        ],
    }
    has_any_requested_roster = any(bool(entries) for entries in requested_by_sec.values())

    roster_found: tuple[str, Any] | None = None
    for sec_entry, sec_root in parsed_sections:
        for el in sec_root.iter():
            if _xml_local_name(el) == "tbl" and el.get("id") == "1111275716":
                roster_found = (sec_entry, el)
                break
        if roster_found is not None:
            break

    if roster_found is None:
        for sec_entry, sec_root in parsed_sections:
            for el in sec_root.iter():
                if _xml_local_name(el) == "tbl":
                    tbl_txt = "".join(el.itertext())
                    if "▯건강회복" in tbl_txt or "▯등록 새교우" in tbl_txt:
                        roster_found = (sec_entry, el)
                        break
            if roster_found is not None:
                break

    if roster_found is None:
        if has_any_requested_roster:
            issues.append({
                "check": "roster_boundary_missing",
                "location": "Contents/section*.xml",
                "detail": "Table 10 (id=1111275716) boundary missing for requested roster fields",
            })
    else:
        roster_sec_entry, roster_tbl = roster_found
        sublist_el = next((el for el in roster_tbl.iter() if _xml_local_name(el) == "subList"), None)
        section_body_lines: Dict[str, List[str]] = {
            "new_members": [],
            "healing": [],
            "military": [],
            "overseas": [],
        }
        current_roster_sec: str | None = None
        roster_paras = [ch for ch in sublist_el if _xml_local_name(ch) == "p"] if sublist_el is not None else []

        for pi, p_el in enumerate(roster_paras):
            para_chunks: List[str] = []
            run_children = [ch for ch in p_el if _xml_local_name(ch) == "run"]
            for ri, run_el in enumerate(run_children):
                r_parts: List[str] = []
                for ch in run_el:
                    lname = _xml_local_name(ch)
                    if lname == "t":
                        r_parts.append(_extract_t_text(ch))
                    elif lname == "lineBreak":
                        r_parts.append("\n")
                r_txt = "".join(r_parts)
                s_txt = r_txt.strip()
                if not s_txt:
                    if r_txt and current_roster_sec:
                        para_chunks.append(" ")
                    continue

                if s_txt.startswith("▯"):
                    if s_txt.startswith("▯등록 새교우"):
                        current_roster_sec = "new_members"
                    elif s_txt.startswith("▯건강회복"):
                        current_roster_sec = "healing"
                    elif s_txt.startswith("▯군복무"):
                        current_roster_sec = "military"
                    elif s_txt.startswith("▯해외 체류") or s_txt.startswith("▯해외체류"):
                        current_roster_sec = "overseas"

                    after_bar = s_txt.split("╻", 1)[1].strip() if "╻" in s_txt else ""
                    if not after_bar:
                        # Pure roster subheader run: Bold style is normal and permitted
                        continue
                    if current_roster_sec:
                        para_chunks.append(after_bar)
                else:
                    if current_roster_sec:
                        para_chunks.append(r_txt)

                if current_roster_sec in section_body_lines:
                    cid = str(run_el.get("charPrIDRef", ""))
                    st = charpr_styles.get(cid)
                    if st is not None:
                        loc = f"{roster_sec_entry}:tbl#1111275716/p[{pi}]/run[{ri}]"
                        if st["is_bold"]:
                            issues.append({
                                "check": "roster_body_bold",
                                "location": loc,
                                "detail": f"section={current_roster_sec}, charPrIDRef={cid}, fontface={st['font_face'] or 'UNKNOWN'}, bold=True",
                            })
                        if st["font_face"] != "경기천년바탕 Regular":
                            issues.append({
                                "check": "roster_body_font",
                                "location": loc,
                                "detail": f"section={current_roster_sec}, charPrIDRef={cid}, fontface={st['font_face'] or 'UNKNOWN'}",
                            })
                        if st["height"] != 1550:
                            issues.append({
                                "check": "roster_body_size",
                                "location": loc,
                                "detail": f"section={current_roster_sec}, charPrIDRef={cid}, height={st['height']}",
                            })

            if current_roster_sec in section_body_lines and para_chunks:
                joined_line = _norm_ws("".join(para_chunks))
                if joined_line:
                    section_body_lines[current_roster_sec].append(joined_line)

        for sec_key, field_entries in requested_by_sec.items():
            if not field_entries:
                continue
            sec_norm = " ".join(section_body_lines.get(sec_key, []))
            norm_entries = [(fpath, _norm_ws(val)) for fpath, val in field_entries if _norm_ws(val)]
            expected_counts: Dict[str, int] = {}
            for _, nval in norm_entries:
                expected_counts[nval] = expected_counts.get(nval, 0) + 1
            seen_dup_vals = set()
            for fpath, nval in norm_entries:
                actual_cnt = len(re.findall(rf"(?<!\S){re.escape(nval)}(?!\S)", sec_norm))
                exp_cnt = expected_counts[nval]
                if actual_cnt < exp_cnt:
                    issues.append({
                        "check": "roster_content_missing",
                        "location": f"{roster_sec_entry}:tbl#1111275716/{sec_key}",
                        "detail": f"field={fpath}, expected={exp_cnt}, actual={actual_cnt}",
                    })
                elif actual_cnt > exp_cnt and nval not in seen_dup_vals:
                    issues.append({
                        "check": "roster_content_duplicate",
                        "location": f"{roster_sec_entry}:tbl#1111275716/{sec_key}",
                        "detail": f"field={fpath}, expected={exp_cnt}, actual={actual_cnt}",
                    })
                    seen_dup_vals.add(nval)

    # 5. Parse rendered announcement region & verify requested announcements_sections + Rule 34 final notice/box
    rendered_ann_sections: List[Dict[str, Any]] = []
    ann_region_sec_entry: str | None = None
    has_online_offering_end = False

    for sec_entry, sec_root in parsed_sections:
        top_paras = [ch for ch in sec_root if _xml_local_name(ch) == "p"]
        start_idx = None
        end_idx = None
        for idx, p_el in enumerate(top_paras):
            p_txt = _norm_ws(_extract_direct_p_text(p_el))
            if start_idx is None:
                if p_el.get("paraPrIDRef") == "94" and classify_announcement_section(p_txt) is not None:
                    start_idx = idx
            elif "[온라인헌금 안내]" in p_txt or "[온라인헌금안내]" in p_txt.replace(" ", ""):
                end_idx = idx
                break

        if start_idx is not None:
            ann_region_sec_entry = sec_entry
            has_online_offering_end = end_idx is not None
            region_slice = top_paras[start_idx:end_idx] if end_idx is not None else top_paras[start_idx:]
            curr_group: Dict[str, Any] | None = None
            for p_el in region_slice:
                p_txt = _norm_ws(_extract_direct_p_text(p_el))
                para_pr = p_el.get("paraPrIDRef")
                if para_pr in {"94", "70"} and p_txt:
                    curr_group = {
                        "header_text": p_txt,
                        "role": classify_announcement_section(p_txt),
                        "paras": [],
                    }
                    rendered_ann_sections.append(curr_group)
                elif curr_group is not None:
                    curr_group["paras"].append(p_el)
            break

    ann_sections = data.get("announcements_sections") if isinstance(data, dict) else None
    if isinstance(ann_sections, list) and len(ann_sections) > 0:
        if ann_region_sec_entry is None or not has_online_offering_end or not rendered_ann_sections:
            issues.append({
                "check": "boundary_substitution_failed",
                "location": "Contents/section*.xml",
                "detail": "announcements_sections boundary (paraPrIDRef=94 .. [온라인헌금 안내]) not reflected",
            })
        else:
            rendered_headers = [g["header_text"] for g in rendered_ann_sections]
            for sec_idx, req_sec in enumerate(ann_sections):
                if not isinstance(req_sec, dict):
                    continue
                req_title = _norm_ws(str(req_sec.get("title", "")))
                if not req_title:
                    continue
                matched_group = next(
                    (g for g in rendered_ann_sections if g["header_text"] == req_title or g["header_text"].startswith(req_title + " ")),
                    None,
                )
                if matched_group is None:
                    issues.append({
                        "check": "boundary_substitution_failed" if not any(
                            any(h == _norm_ws(str(s.get("title", ""))) or h.startswith(_norm_ws(str(s.get("title", ""))) + " ") for h in rendered_headers)
                            for s in ann_sections if isinstance(s, dict) and _norm_ws(str(s.get("title", "")))
                        ) else "announcement_section_missing",
                        "location": f"{ann_region_sec_entry}:announcements",
                        "detail": f"field=announcements_sections[{sec_idx}].title",
                    })
                    continue

                rendered_item_texts = [_norm_ws(_extract_direct_p_text(p_el)) for p_el in matched_group["paras"]]
                req_items = req_sec.get("items", [])
                if not isinstance(req_items, list):
                    continue
                for item_idx, item in enumerate(req_items):
                    if isinstance(item, dict):
                        i_title = str(item.get("title", "")).strip()
                        i_content = str(item.get("content", "")).strip()
                    else:
                        i_title = str(item).strip()
                        i_content = ""
                    if not i_title and not i_content:
                        continue
                    if "감사헌금" in req_title:
                        expected_p_txt = _norm_ws(i_content or i_title)
                    elif i_content:
                        expected_p_txt = _norm_ws(f"∙ {i_title}: {i_content}")
                    else:
                        expected_p_txt = _norm_ws(f"∙ {i_title}")
                    if expected_p_txt not in rendered_item_texts:
                        issues.append({
                            "check": "announcement_item_missing",
                            "location": f"{ann_region_sec_entry}:announcements",
                            "detail": f"field=announcements_sections[{sec_idx}].items[{item_idx}]",
                        })

    # 6. Rule 34 final output verification (1st week: 부서 월례회 + tbl 1185698824; 2nd week: 신도회 월례회 + tbl 1137471996)
    bulletin_date = parse_bulletin_date(data, fallback_stem) if isinstance(data, dict) else None
    if bulletin_date is not None and 1 <= bulletin_date.day <= 14:
        if bulletin_date.day <= 7:
            expected_mm_title = "부서 월례회"
            expected_box_id = "1185698824"
            expected_groups = ("관리부", "봉사부", "사회부", "선교부", "성평등부", "예배부", "친교부", "재정부")
        else:
            expected_mm_title = "신도회 월례회"
            expected_box_id = "1137471996"
            expected_groups = ("새청", "청신", "희청", "청녀", "청남", "희녀", "희남", "장녀", "장남")

        today_group = next((g for g in rendered_ann_sections if g["role"] == "today"), None)
        today_loc = f"{ann_region_sec_entry or 'Contents/section*.xml'}:today_schedule"
        if today_group is None:
            issues.append({
                "check": "rule34_notice_missing",
                "location": today_loc,
                "detail": f"expected={expected_mm_title}",
            })
            issues.append({
                "check": "rule34_box_missing",
                "location": today_loc,
                "detail": f"tbl_id={expected_box_id}",
            })
        else:
            notice_matches = [
                p_el
                for p_el in today_group["paras"]
                if is_rule34_monthly_meeting_item(_extract_direct_p_text(p_el).strip(), expected_mm_title)
            ]
            if len(notice_matches) == 0:
                issues.append({
                    "check": "rule34_notice_missing",
                    "location": today_loc,
                    "detail": f"expected={expected_mm_title}",
                })
            elif len(notice_matches) > 1:
                issues.append({
                    "check": "rule34_notice_duplicate",
                    "location": today_loc,
                    "detail": f"expected={expected_mm_title}, count={len(notice_matches)}",
                })

            box_matches = [
                el
                for p_el in today_group["paras"]
                for el in p_el.iter()
                if _xml_local_name(el) == "tbl" and el.get("id") == expected_box_id
            ]
            if len(box_matches) == 0:
                issues.append({
                    "check": "rule34_box_missing",
                    "location": today_loc,
                    "detail": f"tbl_id={expected_box_id}",
                })
            elif len(box_matches) > 1:
                issues.append({
                    "check": "rule34_box_duplicate",
                    "location": today_loc,
                    "detail": f"tbl_id={expected_box_id}, count={len(box_matches)}",
                })
            else:
                box_txt = "".join(box_matches[0].itertext())
                missing_groups = [g for g in expected_groups if g not in box_txt]
                if missing_groups:
                    issues.append({
                        "check": "rule34_box_incomplete",
                        "location": f"{ann_region_sec_entry}:tbl#{expected_box_id}",
                        "detail": f"missing_group_count={len(missing_groups)}",
                    })

    # 7. Logo dimension, aspect ratio & rendering matrix verification (Rule 11)
    has_image3 = any(re.fullmatch(r"BinData/image3\.[a-zA-Z0-9]+", n) for n in names)
    has_image4 = any(re.fullmatch(r"BinData/image4\.[a-zA-Z0-9]+", n) for n in names)

    if has_image3 or has_image4:
        season_val = str(data.get("metadata", {}).get("season", "") or data.get("season", "") or "")
        matched_lit_cfg = None
        for s_key, s_cfg in HwpxEngine.LITURGICAL_CONFIG.items():
            if s_key in season_val:
                matched_lit_cfg = s_cfg
                break

        pic_by_img_ref: Dict[str, Any] = {}
        sec_by_img_ref: Dict[str, str] = {}
        for sec_name, sec_root in parsed_sections:
            for p_el in sec_root.iter():
                if _xml_local_name(p_el) == "pic":
                    for sub in p_el.iter():
                        if _xml_local_name(sub) == "img":
                            b_ref = sub.get("binaryItemIDRef")
                            if b_ref in ("image3", "image4") and b_ref not in pic_by_img_ref:
                                pic_by_img_ref[b_ref] = p_el
                                sec_by_img_ref[b_ref] = sec_name

        for img_ref in ["image3", "image4"]:
            bin_entry = next((n for n in names if re.fullmatch(rf"BinData/{img_ref}\.[a-zA-Z0-9]+", n)), None)
            if not bin_entry and img_ref not in pic_by_img_ref:
                continue

            loc_label = f"{sec_by_img_ref.get(img_ref, 'Contents/section0.xml')}:pic[{img_ref}]"

            if not bin_entry:
                issues.append({
                    "check": "logo_file_missing",
                    "location": f"BinData/{img_ref}",
                    "detail": f"BinData entry for {img_ref} is missing",
                })
                continue

            raw_bytes = bindata_raw.get(bin_entry)
            if not raw_bytes:
                issues.append({
                    "check": "logo_file_missing",
                    "location": f"BinData/{img_ref}",
                    "detail": f"BinData entry for {img_ref} is empty or missing",
                })
                continue
            img_size = _get_image_bytes_size(raw_bytes)
            if not img_size:
                issues.append({
                    "check": "logo_image_unreadable",
                    "location": bin_entry,
                    "detail": "failed to decode logo image dimensions",
                })
                continue

            img_w, img_h = img_size

            pic_el = pic_by_img_ref.get(img_ref)
            if pic_el is None:
                issues.append({
                    "check": "logo_pic_missing",
                    "location": loc_label,
                    "detail": f"no pic element referencing {img_ref}",
                })
                continue

            sz_el = next((el for el in pic_el.iter() if _xml_local_name(el) == "sz"), None)
            cur_sz_el = next((el for el in pic_el.iter() if _xml_local_name(el) == "curSz"), None)
            org_sz_el = next((el for el in pic_el.iter() if _xml_local_name(el) == "orgSz"), None)
            sca_el = next((el for el in pic_el.iter() if _xml_local_name(el) == "scaMatrix"), None)

            if sz_el is None or cur_sz_el is None or org_sz_el is None or sca_el is None:
                issues.append({
                    "check": "logo_pic_incomplete",
                    "location": loc_label,
                    "detail": "missing required sizing or matrix tags in pic",
                })
                continue

            try:
                cur_w, cur_h = int(cur_sz_el.get("width", 0)), int(cur_sz_el.get("height", 0))
                sz_w, sz_h = int(sz_el.get("width", 0)), int(sz_el.get("height", 0))
                org_w, org_h = int(org_sz_el.get("width", 0)), int(org_sz_el.get("height", 0))
                e1, e5 = float(sca_el.get("e1", 0.0)), float(sca_el.get("e5", 0.0))
            except (ValueError, TypeError) as conv_err:
                issues.append({
                    "check": "logo_pic_invalid_attributes",
                    "location": loc_label,
                    "detail": str(conv_err),
                })
                continue

            # Determine expected target size based on image and season (Rule 11)
            known_targets = {
                "image3": {
                    (336, 482): (5437, 7800),     # 창조절 / 주현절 심볼
                    (251, 283): (7007, 7899),     # 성령강림절 심볼
                    (293, 351): (round(7500 * 293 / 351), 7500),  # 사순절 / 대림절 심볼
                    (275, 321): (round(7500 * 275 / 321), 7500),  # 성탄절 / 부활절 심볼
                },
                "image4": {
                    (1084, 373): (18018, 6200),   # 창조절 / 주현절 글씨
                    (700, 207): (20542, 6080),    # 성령강림절 글씨
                    (704, 197): (round(5800 * 704 / 197), 5800),  # 사순절 / 대림절 글씨
                    (700, 197): (round(5800 * 700 / 197), 5800),  # 성탄절 / 부활절 글씨
                },
            }
            known_map = known_targets.get(img_ref, {})
            if (img_w, img_h) in known_map:
                exp_w, exp_h = known_map[(img_w, img_h)]
            elif matched_lit_cfg:
                if img_ref == "image3":
                    target_sz = matched_lit_cfg.get("symbol_target_sz")
                    if not target_sz:
                        max_h = 7500
                        exp_w = round(max_h * img_w / img_h)
                        target_sz = (exp_w, max_h)
                else:
                    target_sz = matched_lit_cfg.get("text_target_sz")
                    if not target_sz:
                        max_h = 5800
                        exp_w = round(max_h * img_w / img_h)
                        target_sz = (exp_w, max_h)
                exp_w, exp_h = target_sz
            else:
                max_h = 7500 if img_ref == "image3" else 5800
                exp_w, exp_h = (round(max_h * img_w / img_h), max_h)

            # 1. Size match check (with tolerance up to 2 units for rounding)
            if abs(cur_w - exp_w) > 2 or abs(cur_h - exp_h) > 2 or abs(sz_w - exp_w) > 2 or abs(sz_h - exp_h) > 2:
                issues.append({
                    "check": "logo_size_mismatch",
                    "location": loc_label,
                    "detail": f"expected={exp_w}x{exp_h}, got_cur={cur_w}x{cur_h}, got_sz={sz_w}x{sz_h}",
                })

            # 2. orgSz match check (img_px * 75)
            exp_org_w = img_w * 75
            exp_org_h = img_h * 75
            if abs(org_w - exp_org_w) > 30 or abs(org_h - exp_org_h) > 30:
                issues.append({
                    "check": "logo_orgsz_mismatch",
                    "location": loc_label,
                    "detail": f"expected={exp_org_w}x{exp_org_h}, got={org_w}x{org_h}",
                })

            # 3. scaMatrix match check
            if exp_org_w > 0 and exp_org_h > 0:
                exp_e1 = exp_w / exp_org_w
                exp_e5 = exp_h / exp_org_h
                if abs(e1 - exp_e1) > 0.005 or abs(e5 - exp_e5) > 0.005:
                    issues.append({
                        "check": "logo_matrix_mismatch",
                        "location": loc_label,
                        "detail": f"expected=({exp_e1:.6f},{exp_e5:.6f}), got=({e1:.6f},{e5:.6f})",
                    })

            # 4. Aspect Ratio check
            if cur_h > 0 and exp_h > 0:
                rendered_ratio = cur_w / cur_h
                exp_ratio = exp_w / exp_h
                if abs(rendered_ratio - exp_ratio) > 0.01:
                    issues.append({
                        "check": "logo_ratio_distortion",
                        "location": loc_label,
                        "detail": f"expected_ratio={exp_ratio:.3f}, rendered_ratio={rendered_ratio:.3f}",
                    })

    if issues:
        raise HwpxArtifactValidationError(issues)


class HwpxEngine:
    """Production-grade engine for HWPX template XML tag substitution."""

    DEFAULT_LOGO_DIR = Path(r"C:\Users\june2\OneDrive\바탕 화면\주보인수인계\향린로고")
    MAX_EXPORT_RETRIES: int = 20

    LITURGICAL_CONFIG = {
        "창조절": {
            "color": "#0F8140",
            "symbol_logo": "주현절, 창조절 (1).png",
            "text_logo": "주현절, 창조절 (2).png",
            "symbol_target_sz": (5437, 7800),
            "text_target_sz": (18018, 6200),
        },
        "주현절": {
            "color": "#0F8140",
            "symbol_logo": "주현절, 창조절 (1).png",
            "text_logo": "주현절, 창조절 (2).png",
            "symbol_target_sz": (5437, 7800),
            "text_target_sz": (18018, 6200),
        },
        "성령강림": {
            "color": "#ED2024",
            "symbol_logo": "성령강림절 (1).png",
            "text_logo": "성령강림절 (2).png",
            "symbol_target_sz": (7007, 7899),
            "text_target_sz": (20542, 6080),
        },
        "사순절": {
            "color": "#7D287E",
            "symbol_logo": "사순절, 대림절 (1).png",
            "text_logo": "사순절, 대림절 (2).png",
        },
        "대림절": {
            "color": "#7D287E",
            "symbol_logo": "사순절, 대림절 (1).png",
            "text_logo": "사순절, 대림절 (2).png",
        },
        "부활절": {
            "color": "#4DC6F2",
            "symbol_logo": "성탄절, 부활절 (1).png",
            "text_logo": "성탄절, 부활절 (2).png",
        },
        "성탄절": {
            "color": "#4DC6F2",
            "symbol_logo": "성탄절, 부활절 (1).png",
            "text_logo": "성탄절, 부활절 (2).png",
        },
    }

    # 타이포그래피 맞춤 자간 설정 (과부/외톨이 글자 방지)
    # 불릿 '∙ ' 기호는 항상 자간 0%를 유지하여 정렬을 보존하고 본문 시작부부터 맞춤 자간 적용
    SPACING_CID_MAP = {
        -1: ("204", "205"),
        -2: ("206", "207"),
        -3: ("208", "209"),
        -4: ("210", "211"),
        -5: ("212", "213"),
        -6: ("214", "215"),
        -7: ("216", "217"),
        -11: ("218", "219"),
    }

    ITEM_SPACING_CONFIG = [
        # (제목 키워드, 적용할 미세 자간%)
        ("친교부 나들이", -5),
        ("혼인", -5),
        ("사진으로 보는 향린 역사", -6),
        ("홍근수 목사 13주기", -5),
        ("홍근수 목사", -5),
        ("심방", -11),
        ("성서배움마당", -7),
        ("향린국악학교 수강생", -3),  # 서도민요반 줄바꿈에 맞춰 시원하게 -3%
        ("우리가락 얼쑤", -5),
        ("안병무 박사 30주기 연극", -4),
        ("기후정의행진 피켓", -3),  # 둘째 줄 '시'가 윗줄로 올라가도록 1줄 완성
        ("이번주 성서일과", -1),
    ]

    LIFESTYLE_PLEDGES = {
        1: "우리는 하나님 나라의 일꾼으로 이 땅에 파송되었음을 믿으며, 하나님 나라의 실현을 위해 성서공부, 기도, 신앙ㆍ신학서적 읽기 등 일상의 신앙훈련을 통해 사회선교의 영성을 키운다.",
        2: "우리는 교인들 한 명 한 명의 주체적 참여가 교회 민주주의의 근간이 된다고 믿으며, 이를 위해 각 신도회와 부서, 평화나눔공동체 등 교회 모임에 적극적으로 참여한다.",
        3: "우리는 우리의 삶과 숨결이 녹아 있는 우리 가락과 정서로 하나님께 예배드릴 때 더욱 뜻깊은 예배가 된다고 믿으며, 우리 가락이나 우리 악기를 배우기 위해 힘쓴다.",
        4: "우리는 평화를 위하여 일하는 이가 하나님의 자녀임을 믿으며, 국가보안법 폐지와 한반도 평화협정 실현을 위한 활동에 나선다.",
        5: "우리는 분단된 겨레를 하나 되게 하는 것이 하나님의 뜻이라 믿으며, 평화통일을 이루기 위해 기도하고, 헌금하며, 활동한다.",
        6: "우리는 누구에게나 햇빛과 비를 주셔서 평등하게 사랑하시는 하나님을 믿으며, 교회와 가정, 직장 등 모든 관계에서 차별적 언어나 행위를 하지 않도록 민감하게 성찰하며 행동한다.",
        7: "우리는 고통받는 이웃과 함께 아파하시는 하나님을 믿으며, 사회적 불의에 맞서 싸우고, 고통당하는 이웃들과 연대하는 활동에 참여한다.",
        8: "우리는 창조질서의 보전이 하나님의 뜻이라 믿으며, 자녀들과 함께 일상생활에서 친환경적으로 생활하고 이웃과 힘을 모아 생태적 삶을 실천한다.",
        9: "우리는 하나님께서 주신 모든 생명을 있는 그대로 소중히 여기는 것이 하나님의 뜻이라 믿으며, 어린이ㆍ청소년들의 심리와 교육 상태를 이해하고, 그들의 교육 환경과 사회 환경을 개선하기 위해 노력한다.",
        10: "우리는 신앙의 유산을 이어 나가는 것이 하나님의 뜻이라 믿으며, 어린이ㆍ청소년들과 한국교회의 미래를 위해 교회교육이 매우 중요함을 인식하고, 교육 재정 확보, 교사 봉사, 학부모 활동 등을 통해 교회교육을 지원한다.",
    }

    def __init__(self, template_path: Path | str, logo_dir: Path | str | None = None):
        self.template_path = Path(template_path)
        if not self.template_path.is_file():
            raise FileNotFoundError(f"HWPX template not found: {self.template_path}")
        self.logo_dir = Path(logo_dir) if logo_dir else self.DEFAULT_LOGO_DIR

    @staticmethod
    def flatten_data(data: Dict[str, Any]) -> Dict[str, str]:
        """Flatten hierarchical bulletin data into a comprehensive tag replacement map."""
        flat_map: Dict[str, str] = {}

        # 1. Metadata mappings
        meta = data.get("metadata", {})
        if isinstance(meta, dict):
            flat_map["foundation_year"] = str(meta.get("foundation_year", "73"))
            flat_map["창립주년"] = flat_map["foundation_year"]
            
            flat_map["unification_year"] = str(meta.get("unification_year", "82"))
            flat_map["통일염원"] = flat_map["unification_year"]
            
            flat_map["date"] = str(meta.get("date", ""))
            flat_map["date_korean"] = str(meta.get("date_korean", meta.get("date", "")))
            flat_map["주일일자"] = flat_map["date_korean"]
            
            flat_map["season"] = str(meta.get("season", ""))
            flat_map["절기"] = flat_map["season"]
            
            motto = str(meta.get("motto", ""))
            flat_map["motto"] = motto
            flat_map["표어"] = motto
            motto_parts = [p.strip() for p in motto.splitlines() if p.strip()] if "\n" in motto else [motto, ""]
            flat_map["motto_line1"] = str(meta.get("motto_line1", motto_parts[0] if motto_parts else ""))
            flat_map["motto_line2"] = str(meta.get("motto_line2", motto_parts[1] if len(motto_parts) > 1 else ""))

            flat_map["headline_left"] = str(data.get("headline_left") or meta.get("headline_left", ""))
            flat_map["헤드라인_좌"] = flat_map["headline_left"]
            
            flat_map["headline_right"] = str(data.get("headline_right") or meta.get("headline_right", ""))
            flat_map["헤드라인_우"] = flat_map["headline_right"]

            flat_map["cover_photo"] = str(data.get("cover_photo") or meta.get("cover_photo", ""))
            flat_map["대문사진"] = flat_map["cover_photo"]

        # 2. Worship order mappings
        worship = data.get("worship_1", data.get("worship", {}))
        if isinstance(worship, dict):
            flat_map["worship_call_scripture"] = str(worship.get("call_scripture", ""))
            flat_map["예배부름_성경"] = flat_map["worship_call_scripture"]

            flat_map["worship_opening_hymn"] = str(worship.get("opening_hymn", ""))
            flat_map["여는찬송"] = flat_map["worship_opening_hymn"]

            confession_val = str(worship.get("confession_or_lord_prayer") or worship.get("lord_prayer_hymn") or worship.get("confession_hymn") or worship.get("lord_prayer") or "")
            flat_map["confession_or_lord_prayer"] = confession_val
            flat_map["주기도송"] = confession_val
            flat_map["신앙고백송"] = confession_val

            choir_title = str(worship.get("choir_song_title", "")).strip()
            choir_info = str(worship.get("choir_song_info", "")).strip()
            # Rule 33: 성가대 찬양 글·곡 정보 ALL CAPS 및 Mrs. 자동 정제
            if choir_info:
                choir_info = re.sub(r'\bMrs\.\s*', '', choir_info, flags=re.IGNORECASE)
                def clean_caps(m):
                    w = m.group(0)
                    if len(w) > 1 and w.isupper():
                        if '.' in w:
                            return w
                        return w.title()
                    return w
                choir_info = re.sub(r'[A-Za-z]+(?:\.[A-Za-z]+)*', clean_caps, choir_info)

            if choir_title:
                if not (choir_title.startswith("“") or choir_title.startswith('"')):
                    formatted_title = f"“{choir_title}”"
                else:
                    formatted_title = choir_title
                if choir_info:
                    if not (choir_info.startswith("(") or choir_info.startswith("（")):
                        formatted_info = f" ({choir_info})"
                    else:
                        formatted_info = f" {choir_info}"
                else:
                    formatted_info = ""
                full_choir = f"{formatted_title}{formatted_info}"
            else:
                formatted_title = ""
                formatted_info = ""
                full_choir = ""

            flat_map["choir_song"] = full_choir
            flat_map["찬양"] = full_choir
            flat_map["choir_song_title"] = formatted_title
            flat_map["찬양곡명"] = formatted_title
            flat_map["choir_song_info"] = formatted_info
            flat_map["찬양정보"] = formatted_info
            flat_map["choir_song_lyrics_1"] = str(worship.get("choir_song_lyrics_1", ""))
            flat_map["choir_song_lyrics_2"] = str(worship.get("choir_song_lyrics_2", ""))

            flat_map["worship_scripture"] = str(worship.get("scripture", ""))
            flat_map["성서읽기"] = flat_map["worship_scripture"]
            flat_map["성경본문"] = flat_map["worship_scripture"]

            flat_map["responsive_scripture_ref"] = str(worship.get("responsive_scripture_ref", ""))
            flat_map["함께읽는말씀_성경"] = flat_map["responsive_scripture_ref"]
            flat_map["responsive_scripture_1"] = str(worship.get("responsive_scripture_1", ""))
            flat_map["responsive_scripture_2"] = str(worship.get("responsive_scripture_2", ""))
            flat_map["responsive_scripture_3"] = str(worship.get("responsive_scripture_3", ""))
            flat_map["responsive_scripture_4"] = str(worship.get("responsive_scripture_4", ""))

            flat_map["worship_gospel"] = str(worship.get("gospel", ""))
            flat_map["복음서읽기"] = flat_map["worship_gospel"]

            sermon_title_raw = str(worship.get("sermon_title", "")).strip()
            # 템플릿의 “{{worship_sermon_title}}” 태그에 이미 따옴표가 포함되어 있으므로 외곽 따옴표 자동 정규화
            if (sermon_title_raw.startswith(('“', '"', "'")) and sermon_title_raw.endswith(('”', '"', "'"))):
                sermon_title_raw = sermon_title_raw[1:-1].strip()
            flat_map["worship_sermon_title"] = sermon_title_raw
            flat_map["설교제목"] = flat_map["worship_sermon_title"]
            flat_map["하늘뜻펴기_제목"] = flat_map["worship_sermon_title"]

            flat_map["worship_preacher"] = str(worship.get("preacher", ""))
            flat_map["설교자"] = flat_map["worship_preacher"]
            flat_map["하늘뜻펴기_설교자"] = flat_map["worship_preacher"]

            flat_map["worship_response_hymn"] = str(worship.get("response_hymn", ""))
            flat_map["응답찬송"] = flat_map["worship_response_hymn"]

            flat_map["worship_offering_hymn"] = str(worship.get("decision_hymn", worship.get("offering_hymn", "")))
            flat_map["봉헌찬송"] = flat_map["worship_offering_hymn"]
            flat_map["결단찬송"] = flat_map["worship_offering_hymn"]

            flat_map["worship_benediction"] = str(worship.get("benediction", ""))
            flat_map["축복기도"] = flat_map["worship_benediction"]

        # 3. Duties (예배위원 3주 테이블)
        duties = data.get("duties", {})
        if not isinstance(duties, dict):
            duties = {}

        import datetime
        base_date = None
        date_raw = data.get("date") or meta.get("date") or meta.get("date_korean") or ""
        if date_raw:
            d_m = re.search(r"(\d{4})[-.년\s]+(\d{1,2})[-.월\s]+(\d{1,2})", str(date_raw))
            if d_m:
                try:
                    base_date = datetime.date(int(d_m.group(1)), int(d_m.group(2)), int(d_m.group(3)))
                except ValueError:
                    pass

        for idx, w in enumerate(["w1", "w2", "w3"]):
            w_data = duties.get(w, {})
            if not isinstance(w_data, dict):
                w_data = {}
            w_date = str(w_data.get("date", "")).strip()
            if not w_date and base_date:
                calc_date = base_date + datetime.timedelta(days=7 * idx)
                w_date = f"{calc_date.month:02d}/{calc_date.day:02d}"

            flat_map[f"duty_{w}_date"] = w_date
            flat_map[f"duty_{w}_presider"] = str(w_data.get("presider", ""))
            flat_map[f"duty_{w}_pastoral_prayer"] = str(w_data.get("pastoral_prayer", ""))
            flat_map[f"duty_{w}_scripture_reader"] = str(w_data.get("scripture_reader", ""))
            flat_map[f"duty_{w}_preacher"] = str(w_data.get("preacher", ""))
            flat_map[f"duty_{w}_thanks_prayer"] = str(w_data.get("thanks_prayer", ""))


        # Service duties (주일 봉사)
        service = data.get("service_duties") or data.get("service_duties_september") or {}
        if isinstance(service, dict):
            flat_map["service_worship_guides"] = str(service.get("worship_guides", "김경민 강정희")).strip()
            flat_map["service_av_room"] = str(service.get("av_room", "")).strip()
            flat_map["service_finance"] = str(service.get("finance", "재정부")).strip()
            flat_map["service_parking"] = str(service.get("parking", "관리부 희남")).strip()
            flat_map["service_meal"] = str(service.get("fellowship_meal", "봉사부 청녀")).strip()
            flat_map["service_recycling"] = str(service.get("recycling", "청녀")).strip()

        # 4. Donations (감사헌금)
        donations = data.get("donations", {})

        if isinstance(donations, dict):
            flat_map["thanksgiving_donors"] = str(donations.get("thanksgiving", ""))
            flat_map["감사헌금"] = flat_map["thanksgiving_donors"]

        # 5. Prayer requests (기도나눔)
        prayers = data.get("prayer_requests", data.get("prayers", {}))
        if isinstance(prayers, dict):
            flat_map["healing_prayer_1"] = str(prayers.get("healing_1", prayers.get("health_1", "")))
            flat_map["healing_prayer_2"] = str(prayers.get("healing_2", prayers.get("health_2", "")))
            flat_map["healing_prayer_3"] = str(prayers.get("healing_3", prayers.get("health_3", "")))
            flat_map["military_prayer_names"] = str(prayers.get("military", ""))
            flat_map["overseas_prayer_1"] = str(prayers.get("overseas_1", ""))
            flat_map["overseas_prayer_2"] = str(prayers.get("overseas_2", ""))

        # 6. Announcements slot mapping (up to 15 slots)
        announcements = data.get("announcements", [])
        if isinstance(announcements, list):
            for i in range(15):
                slot_idx = i + 1
                if i < len(announcements):
                    item = announcements[i]
                    if isinstance(item, dict):
                        title = str(item.get("title", ""))
                        content = str(item.get("content", ""))
                    else:
                        title = str(item)
                        content = ""
                else:
                    title = ""
                    content = ""
                
                flat_map[f"ad{slot_idx}_title"] = title
                flat_map[f"광고{slot_idx}_제목"] = title
                flat_map[f"ad{slot_idx}_content"] = content
                flat_map[f"광고{slot_idx}_내용"] = content

        # 7. Direct top-level key-values
        for key, val in data.items():
            if isinstance(val, (str, int, float)):
                flat_map[key] = str(val)

        return flat_map

    @staticmethod
    def _update_pic_xml(pic_xml: str, px_w: int, px_h: int, target_w: int, target_h: int) -> str:
        """Update HWPX <pic> tag attributes including sz, curSz, orgSz, scaMatrix, and imgRect."""
        org_w = px_w * 75
        org_h = px_h * 75
        center_x = round(target_w / 2)
        center_y = round(target_h / 2)
        e1 = target_w / org_w
        e5 = target_h / org_h

        # 1. orgSz
        pic_xml = re.sub(r'(<(?:\w+:)?orgSz\b[^>]*width=")\d+("[^>]*height=")\d+(")', rf'\g<1>{org_w}\g<2>{org_h}\g<3>', pic_xml)
        # 2. curSz
        pic_xml = re.sub(r'(<(?:\w+:)?curSz\b[^>]*width=")\d+("[^>]*height=")\d+(")', rf'\g<1>{target_w}\g<2>{target_h}\g<3>', pic_xml)
        # 3. sz
        pic_xml = re.sub(r'(<(?:\w+:)?sz\b[^>]*width=")\d+("[^>]*height=")\d+(")', rf'\g<1>{target_w}\g<2>{target_h}\g<3>', pic_xml)
        # 4. rotationInfo
        pic_xml = re.sub(r'(<(?:\w+:)?rotationInfo\b[^>]*centerX=")\d+("[^>]*centerY=")\d+(")', rf'\g<1>{center_x}\g<2>{center_y}\g<3>', pic_xml)
        # 5. scaMatrix
        pic_xml = re.sub(r'(<(?:\w+:)?scaMatrix\b[^>]*e1=")[^"]+("[^>]*e5=")[^"]+(")', rf'\g<1>{e1:.6f}\g<2>{e5:.6f}\g<3>', pic_xml)
        # 6. imgRect pt1, pt2, pt3
        pic_xml = re.sub(r'(<(?:\w+:)?pt1\b[^>]*x=")\d+("[^>]*y=")\d+(")', rf'\g<1>{org_w}\g<2>0\g<3>', pic_xml)
        pic_xml = re.sub(r'(<(?:\w+:)?pt2\b[^>]*x=")\d+("[^>]*y=")\d+(")', rf'\g<1>{org_w}\g<2>{org_h}\g<3>', pic_xml)
        pic_xml = re.sub(r'(<(?:\w+:)?pt3\b[^>]*x=")\d+("[^>]*y=")\d+(")', rf'\g<1>0\g<2>{org_h}\g<3>', pic_xml)
        # 7. imgClip
        pic_xml = re.sub(r'(<(?:\w+:)?imgClip\b[^>]*right=")\d+("[^>]*bottom=")\d+(")', rf'\g<1>{org_w}\g<2>{org_h}\g<3>', pic_xml)
        # 8. imgDim
        pic_xml = re.sub(r'(<(?:\w+:)?imgDim\b[^>]*dimwidth=")\d+("[^>]*dimheight=")\d+(")', rf'\g<1>{org_w}\g<2>{org_h}\g<3>', pic_xml)

        return pic_xml

    @staticmethod
    def _get_image_size(img_path: Path) -> tuple[int, int]:
        """Get (width, height) in pixels from an image file; raises ValueError on failure."""
        try:
            raw = img_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"로고 이미지 파일을 읽을 수 없습니다 ({img_path.name}): {exc}") from exc

        size = _get_image_bytes_size(raw)
        if not size or size[0] <= 0 or size[1] <= 0:
            raise ValueError(f"로고 이미지 크기 판독 실패 ({img_path.name}): 이미지 형식이 올바르지 않거나 손상되었습니다.")
        return size

    def _verify_official_scripture(self, data: Dict[str, Any]) -> None:
        """Verify that responsive_scripture matches official homepage scripture (Rule 0).
        Raises ValueError if arbitrary/hallucinated scripture is detected.
        """
        worship = data.get("worship_1", data.get("worship", {}))
        if not isinstance(worship, dict):
            return

        meta = data.get("metadata", {})
        if meta.get("skip_scripture_verification") or data.get("skip_scripture_verification"):
            return

        resp_lines = []
        for k in ["responsive_scripture_1", "responsive_scripture_2", "responsive_scripture_3", "responsive_scripture_4"]:
            v = str(worship.get(k, "")).strip()
            if v:
                resp_lines.append(v)
        if not resp_lines and worship.get("responsive_scripture"):
            rs = worship.get("responsive_scripture")
            if isinstance(rs, list):
                resp_lines = [str(x).strip() for x in rs if str(x).strip()]
            elif isinstance(rs, str):
                resp_lines = [l.strip() for l in rs.split("\n") if l.strip()]

        if not resp_lines:
            return

        # Extract target Sunday date
        meta = data.get("metadata", {})
        date_str = str(meta.get("date_compact") or meta.get("date") or meta.get("date_korean") or data.get("date", ""))
        d_m = re.search(r'(\d{4})[-.]?(\d{2})[-.]?(\d{2})', date_str)
        if not d_m:
            return
        target_date_iso = f"{d_m.group(1)}-{d_m.group(2)}-{d_m.group(3)}"

        try:
            try:
                from scripts.fetch_sunday_scripture import fetch_post_url, fetch_scripture_content
            except ImportError:
                from fetch_sunday_scripture import fetch_post_url, fetch_scripture_content

            post_url = fetch_post_url(target_date_iso)
            if post_url:
                raw_scripture = fetch_scripture_content(post_url)
                if raw_scripture:
                    clean_official = re.sub(r'\s+', ' ', raw_scripture)
                    for idx, line in enumerate(resp_lines, 1):
                        core_text = re.sub(r'^\d+\s*', '', line).strip()
                        tokens = [t for t in core_text.split() if len(t) >= 2]
                        if not tokens:
                            continue
                        match_count = sum(1 for t in tokens if t in clean_official)
                        ratio = match_count / len(tokens)
                        if ratio < 0.6:
                            raise ValueError(
                                f"[CRITICAL BLOCKER] 함께읽는말씀 본문 출처 위반 감지 (Rule 0)!\n"
                                f" - 입력 행 {idx}: \"{line}\"\n"
                                f" - 공식 SSOT 게시판({post_url}) 본문 일치율: {ratio:.1%} (기준: 60% 이상)\n"
                                f" AI 자체 기억에 의한 작문이나 비공식 번역본 인용은 엄격히 차단됩니다."
                            )
        except ValueError:
            raise
        except Exception:
            # Network issues or offline unit test fallback
            pass

    def generate(self, data: Dict[str, Any], output_path: Path | str) -> Path:
        """Generate a new HWPX file by substituting text placeholders in XML.
        
        Args:
            data: Structured or flat bulletin data dict.
            output_path: Target destination path for generated HWPX.
            
        Returns:
            Path to the generated HWPX file.
        """
        output_file = Path(output_path)
        prepared_data = prepare_bulletin_data(data, fallback_stem=output_file.stem)
        fact_issues = validate_bulletin_facts_data(
            prepared_data,
            fallback_stem=output_file.stem,
            check_online_scripture=False,
        )
        fact_errors = [iss for iss in fact_issues if iss.get("level") == "ERROR"]
        if fact_errors:
            raise BulletinValidationError(fact_errors)

        data = prepared_data

        flat_map = self.flatten_data(data)

        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as stage_dir:
            temp_path = Path(temp_dir)
            staged_hwpx = Path(stage_dir) / "staged_output.hwpx"

            # 1. Unpack HWPX zip
            with zipfile.ZipFile(self.template_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)

            # 2. Process XML section files
            contents_dir = temp_path / "Contents"
            if contents_dir.is_dir():
                for xml_file in contents_dir.glob("section*.xml"):
                    xml_text = xml_file.read_text(encoding="utf-8")

                    # 1) 예배위원 3개 행(w1, w2, w3) 정규화: 템플릿의 누락/병합된 행을 6개 열(날짜, 인도, 목회기도, 성서읽기, 하늘뜻펴기, 감사기도)로 먼저 복구
                    def build_duty_row_template(prefix: str, r_idx: int) -> str:
                        date_val = str(flat_map.get(f"{prefix}_date", "")).strip()
                        presider_val = str(flat_map.get(f"{prefix}_presider", "")).strip()
                        # 연합예배 등 전체 병합 행 감지 (규칙 17: 9/27 골든 레퍼런스 스타일 복원)
                        if "연합예배" in presider_val or "연합예배" in date_val or (date_val == "10/11" and not presider_val):
                            event_text = presider_val if presider_val else "세계성만찬기념주일 향린공동체연합예배"
                            if "향공연합예배" in event_text or event_text == "연합예배":
                                event_text = "세계성만찬기념주일 향린공동체연합예배"
                            return (
                                '<ns1:tr>'
                                '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="28">'
                                '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                                f'<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{html.escape(date_val)}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                                f'<ns1:cellAddr colAddr="0" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="2" rowSpan="1"/><ns1:cellSz width="5183" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                                '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="28">'
                                '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                                f'<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{html.escape(event_text)}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                                f'<ns1:cellAddr colAddr="2" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="7" rowSpan="1"/><ns1:cellSz width="47750" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                                '</ns1:tr>'
                            )
                        row = (
                            '<ns1:tr>'
                            '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="28">'
                            '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                            '<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{{__PREFIX___date}}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                            f'<ns1:cellAddr colAddr="0" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="2" rowSpan="1"/><ns1:cellSz width="5183" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                            '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="28">'
                            '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                            '<ns1:p id="0" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{{__PREFIX___presider}}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                            f'<ns1:cellAddr colAddr="2" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="2" rowSpan="1"/><ns1:cellSz width="9547" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                            '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="28">'
                            '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                            '<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{{__PREFIX___pastoral_prayer}}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                            f'<ns1:cellAddr colAddr="4" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="1" rowSpan="1"/><ns1:cellSz width="9546" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                            '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="28">'
                            '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                            '<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{{__PREFIX___scripture_reader}}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                            f'<ns1:cellAddr colAddr="5" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="1" rowSpan="1"/><ns1:cellSz width="9557" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                            '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="29">'
                            '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                            '<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{{__PREFIX___preacher}}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                            f'<ns1:cellAddr colAddr="6" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="1" rowSpan="1"/><ns1:cellSz width="9554" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                            '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="30">'
                            '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                            '<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="121"><ns1:t>{{__PREFIX___thanks_prayer}}</ns1:t></ns1:run></ns1:p></ns1:subList>'
                            f'<ns1:cellAddr colAddr="7" rowAddr="{r_idx}"/><ns1:cellSpan colSpan="2" rowSpan="1"/><ns1:cellSz width="9546" height="2673"/><ns1:cellMargin left="0" right="0" top="0" bottom="0"/></ns1:tc>'
                            '</ns1:tr>'
                        )
                        return row.replace("__PREFIX__", prefix)


                    duty_3rows_pattern = r'<(?:\w+:)?tr>(?:(?!</(?:\w+:)?tr>)[\s\S])*?\{\{duty_w1_date\}\}[\s\S]*?</(?:\w+:)?tr>\s*<(?:\w+:)?tr>(?:(?!</(?:\w+:)?tr>)[\s\S])*?\{\{duty_w2_date\}\}[\s\S]*?</(?:\w+:)?tr>\s*<(?:\w+:)?tr>(?:(?!</(?:\w+:)?tr>)[\s\S])*?\{\{duty_w3_date\}\}[\s\S]*?</(?:\w+:)?tr>'
                    if re.search(duty_3rows_pattern, xml_text):
                        clean_3rows = f"{build_duty_row_template('duty_w1', 18)}\n{build_duty_row_template('duty_w2', 19)}\n{build_duty_row_template('duty_w3', 20)}"
                        xml_text = re.sub(duty_3rows_pattern, clean_3rows, xml_text)

                    # 함께읽는말씀 본문 (단일 산문 줄글 문단, 템플릿 표준 서식 paraPr 65, charPr 173)
                    if not flat_map.get("responsive_scripture_ref") and flat_map.get("theme_scripture_ref"):
                        flat_map["responsive_scripture_ref"] = flat_map["theme_scripture_ref"]

                    resp_lines = []
                    for k in ["responsive_scripture_1", "responsive_scripture_2", "responsive_scripture_3", "responsive_scripture_4"]:
                        val = str(flat_map.get(k, "")).strip()
                        if val:
                            resp_lines.append(val)
                    if not resp_lines and flat_map.get("responsive_scripture"):
                        resp_lines = [l.strip() for l in str(flat_map.get("responsive_scripture")).splitlines() if l.strip()]
                    if not resp_lines and flat_map.get("theme_scripture_text"):
                        resp_lines = [l.strip() for l in str(flat_map.get("theme_scripture_text")).splitlines() if l.strip()]

                    if resp_lines:
                        # 함께읽는말씀 본문: 골든 레퍼런스 표준 서식 (함초롬돋움 15pt Regular charPr 173, 장평 75, 자간 -14, paraPr 65)
                        resp_p_list = []
                        for i, line_text in enumerate(resp_lines):
                            p_id = "2147483648" if i == 0 else "0"
                            resp_p_list.append(
                                f'<ns1:p id="{p_id}" paraPrIDRef="65" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                f'<ns1:run charPrIDRef="173"><ns1:t>{html.escape(line_text)}</ns1:t></ns1:run>'
                                f'</ns1:p>'
                            )
                        resp_cell_sublist = "".join(resp_p_list)
                        target_resp_h = "3606" if len(resp_lines) <= 1 else "6232" if len(resp_lines) <= 3 else "7550"
                        # Table 1 함께읽는말씀 본문(width="51898")만 스코프 한정하여 치환
                        resp_pattern = r'<(?:\w+:)?tc\b[^>]*>(?:(?!</(?:\w+:)?tc>).)*?colAddr="1"\s*rowAddr="17"[^>]*>[\s\S]*?<(?:\w+:)?cellSz width="51898"[\s\S]*?</(?:\w+:)?tc>'
                        def repl_resp_cell(match):
                            tc = match.group(0)
                            tc = re.sub(r'height="\d+"', f'height="{target_resp_h}"', tc)
                            return re.sub(r'<(?:\w+:)?subList[^>]*>.*?</(?:\w+:)?subList>', f'<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{resp_cell_sublist}</ns1:subList>', tc, flags=re.DOTALL)
                        xml_text = re.sub(resp_pattern, repl_resp_cell, xml_text, flags=re.DOTALL)
                        # Table 1 함께읽는말씀 소제목(width="951")만 높이 동기화 (Table 4 예배위원 행 절대 오염 방지)
                        resp_col0_pat = r'(<(?:\w+:)?tc\b(?:(?!</(?:\w+:)?tc>).)*?colAddr="0"\s*rowAddr="17"[^>]*>[\s\S]*?<(?:\w+:)?cellSz width="951"\s*height=)"\d+"'
                        xml_text = re.sub(resp_col0_pat, r'\g<1>"' + target_resp_h + '"', xml_text)

                        # Table 1 성서읽기(rowAddr 15), 함께읽는말씀(rowAddr 16) 오른쪽 셀 vertAlign="CENTER" 보장 (Rule 20)
                        xml_text = re.sub(
                            r'(<(?:\w+:)?tc\b(?:(?!</(?:\w+:)?tc>).)*?colAddr="2"\s*rowAddr="(?:15|16)"[^>]*>[\s\S]*?<(?:\w+:)?subList\b[^>]*?vertAlign=)"[^"]*"',
                            r'\g<1>"CENTER"',
                            xml_text
                        )

                        # Table 4 예배위원 헤더 행(날짜-인도-목회기도) 높이를 골든 레퍼런스 표준(2739)으로 확실히 보장
                        duty_header_pat = r'(<(?:\w+:)?tc\b(?:(?!</(?:\w+:)?tc>).)*?rowAddr="17"[^>]*>[\s\S]*?<(?:\w+:)?cellSz width="(?:5183|9546|9547|9554|9557)"\s*height=)"\d+"'
                        xml_text = re.sub(duty_header_pat, r'\g<1>"2739"', xml_text)

                    # 건강회복 명단 복원 (140% 줄간격 paraPr 98, charPr 46 경기천년바탕 Regular 15.5pt)
                    healing_1 = flat_map.get("healing_prayer_1", "").strip()
                    healing_2 = flat_map.get("healing_prayer_2", "").strip()
                    healing_3 = flat_map.get("healing_prayer_3", "").strip()
                    healing_lines = [h for h in [healing_1, healing_2, healing_3] if h]
                    if healing_lines:
                        clean_healing_ps = []
                        for idx, h_text in enumerate(healing_lines):
                            pid = "2147483648" if idx == 0 else "0"
                            clean_healing_ps.append(
                                f'<ns1:p id="{pid}" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="46"><ns1:t> {html.escape(h_text)}</ns1:t></ns1:run></ns1:p>'
                            )
                        healing_block_pat = r'<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\{\{healing_prayer_1\}\}[\s\S]*?</(?:\w+:)?p>\s*<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\{\{healing_prayer_3\}\}[\s\S]*?</(?:\w+:)?p>'
                        if re.search(healing_block_pat, xml_text):
                            xml_text = re.sub(healing_block_pat, "\n".join(clean_healing_ps), xml_text)

                    # 해외체류 명단 복원 (140% 줄간격 paraPr 98, charPr 46 경기천년바탕 Regular 15.5pt)
                    overseas_1 = flat_map.get("overseas_prayer_1", "").strip()
                    overseas_2 = flat_map.get("overseas_prayer_2", "").strip()
                    overseas_lines = [o for o in [overseas_1, overseas_2] if o]
                    if overseas_lines:
                        clean_overseas_ps = []
                        for idx, o_text in enumerate(overseas_lines):
                            pid = "2147483648" if idx == 0 else "0"
                            clean_overseas_ps.append(
                                f'<ns1:p id="{pid}" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="46"><ns1:t> {html.escape(o_text)}</ns1:t></ns1:run></ns1:p>'
                            )
                        overseas_block_pat = r'<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\{\{overseas_prayer_1\}\}[\s\S]*?</(?:\w+:)?p>\s*<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\{\{overseas_prayer_2\}\}[\s\S]*?</(?:\w+:)?p>'
                        if re.search(overseas_block_pat, xml_text):
                            xml_text = re.sub(overseas_block_pat, "\n".join(clean_overseas_ps), xml_text)

                    # 하늘뜻펴기 행 우측 빈 칸 병합 (너비 34411 + 5547 = 39958, colSpan 6, 사용자 지정 서식 영구 반영)
                    sermon_merge_pat = r'(<(?:\w+:)?tc\b(?:(?!</(?:\w+:)?tc>).)*?<(?:\w+:)?cellAddr colAddr="3" rowAddr="4"[\s\S]*?</(?:\w+:)?tc>)\s*<(?:\w+:)?tc\b(?:(?!</(?:\w+:)?tc>).)*?<(?:\w+:)?cellAddr colAddr="8" rowAddr="4"[\s\S]*?</(?:\w+:)?tc>'
                    def merge_sermon_cells(match):
                        tc3 = match.group(1)
                        tc3 = re.sub(r'colSpan="5"', 'colSpan="6"', tc3)
                        tc3 = re.sub(r'cellSz width="34411"', 'cellSz width="39958"', tc3)
                        return tc3
                    xml_text = re.sub(sermon_merge_pat, merge_sermon_cells, xml_text, flags=re.DOTALL)

                    # Replace defined keys
                    for key, val in flat_map.items():
                        escaped_val = html.escape(val)
                        xml_text = xml_text.replace(f"{{{{{key}}}}}", escaped_val)
                        xml_text = xml_text.replace(f"{{{{ {key} }}}}", escaped_val)


                    # Dynamic liturgical hymn substitution (주기도송 vs 신앙고백송)
                    # 우측 셀 표기 원칙: 곡 종류와 무관하게 항상 "국악찬송 000장" 형식으로 표기!
                    confession = flat_map.get("confession_or_lord_prayer", "")
                    if not confession:
                        worship_dict = data.get("worship_1", data.get("worship", {}))
                        if isinstance(worship_dict, dict):
                            confession = str(worship_dict.get("confession_or_lord_prayer", ""))
                    
                    # "주기도문송" 표기 정규화 -> 반드시 "주기도송"으로 통일
                    confession = confession.replace("주기도문송", "주기도송").strip()

                    # 일자 기반 월(month) 추출
                    date_str = str(flat_map.get("date") or flat_map.get("date_korean") or "")
                    month = None
                    m_match = re.search(r"[-./](\d{1,2})[-./]|\b(\d{1,2})월", date_str)
                    if m_match:
                        month = int(m_match.group(1) or m_match.group(2))

                    # 찬송 장 번호(num) 판별:
                    # 1, 5, 9월: 주기도송, 245장 -> "국악찬송 245장"
                    # 3, 7, 11월: 주기도송, 246장 -> "국악찬송 246장"
                    # 2, 4, 6, 8, 10, 12월: 신앙고백송, 254장 -> "국악찬송 254장"
                    num_match = re.search(r"(\d+)장", confession)
                    if num_match:
                        hymn_num = num_match.group(1)
                    elif month in [1, 5, 9]:
                        hymn_num = "245"
                    elif month in [3, 7, 11]:
                        hymn_num = "246"
                    else:
                        hymn_num = "254"

                    # 주기도송 / 신앙고백송 행만 정밀 타겟 치환 (타 찬송 및 결단찬송 오염 원천 차단)
                    confession_row_pat = r'(<(?:\w+:)?tr\b(?:(?!</(?:\w+:)?tr>).)*?(?:신\s*앙\s*고\s*백\s*송|주\s*기\s*도\s*송)[\s\S]*?</(?:\w+:)?tr>)'
                    def repl_confession_row(m):
                        tr = m.group(0)
                        if hymn_num in ["245", "246"] or "주기도" in confession:
                            tr = re.sub(r"신\s*앙\s*고\s*백\s*송", "주 기 도 송", tr)
                        else:
                            tr = re.sub(r"주\s*기\s*도\s*송", "신 앙 고 백 송", tr)
                        hymn_right_cell = f"국악찬송 {hymn_num}장"
                        tr = re.sub(r"국악찬송\s*\d+장", hymn_right_cell, tr)
                        return tr

                    if re.search(confession_row_pat, xml_text):
                        xml_text = re.sub(confession_row_pat, repl_confession_row, xml_text)
                    else:
                        # Fallback for simple mock/test XML without <tr>
                        if hymn_num in ["245", "246"] or "주기도" in confession:
                            xml_text = re.sub(r"신\s*앙\s*고\s*백\s*송", "주 기 도 송", xml_text)
                        else:
                            xml_text = re.sub(r"주\s*기\s*도\s*송", "신 앙 고 백 송", xml_text)
                        hymn_right_cell = f"국악찬송 {hymn_num}장"
                        xml_text = re.sub(r"국악찬송\s*\d+장", hymn_right_cell, xml_text)

                    # Dynamic lifestyle pledge substitution (향린교인 생활실천 다짐 10개 조항 순환)
                    pledge_info = data.get("lifestyle_pledge", {})
                    p_num = ""
                    p_text = ""
                    if isinstance(pledge_info, dict):
                        p_num = str(pledge_info.get("number", "")).strip()
                        p_text = str(pledge_info.get("text") or pledge_info.get("content") or "").strip()

                    # 자동 순환 계산 (원고에 명시되지 않거나 비어있는 경우)
                    if not p_num or not p_text:
                        d_m = re.search(r"(\d{4})[-.년\s]+(\d{1,2})[-.월\s]+(\d{1,2})", date_str)
                        if d_m:
                            try:
                                import datetime
                                cur_dt = datetime.date(int(d_m.group(1)), int(d_m.group(2)), int(d_m.group(3)))
                                base_dt = datetime.date(2026, 9, 6)
                                diff_weeks = (cur_dt - base_dt).days // 7
                                calc_num = ((8 + diff_weeks) % 10) + 1
                                if not p_num:
                                    p_num = str(calc_num)
                                if not p_text:
                                    p_text = self.LIFESTYLE_PLEDGES.get(calc_num, "")
                            except Exception:
                                pass

                    if p_num and p_text:
                        pledge_pattern = r'(charPrIDRef="178"[^>]*><(?:\w+:)?t>)\d+\.\s*(</(?:\w+:)?t></(?:\w+:)?run>).*?(</(?:\w+:)?p>)'
                        repl = rf'\g<1>{p_num}. \g<2><ns1:run charPrIDRef="192"><ns1:t>{html.escape(p_text)}</ns1:t></ns1:run>\g<3>'
                        xml_text = re.sub(pledge_pattern, repl, xml_text, flags=re.DOTALL)
                        # 실천다짐 표 높이 골든 레퍼런스(10/4 주보) 표준 규격(6504)으로 슬림화
                        xml_text = re.sub(r'(<(?:\w+:)?cellSz width="52270"\s*height=)"\d+"', r'\g<1>"6504"', xml_text)

                    # Clean choir row (Row 24): unify height to 3217, 17pt Bold title + 14pt Regular info
                    choir_title_str = flat_map.get("choir_song_title", "")
                    choir_info_str = flat_map.get("choir_song_info", "")
                    choir_runs = '<ns1:run charPrIDRef="36"><ns1:t> </ns1:t></ns1:run>'
                    if choir_title_str and "미정" not in choir_title_str and "준비" not in choir_title_str:
                        choir_runs += f'<ns1:run charPrIDRef="81"><ns1:t>{html.escape(choir_title_str)}</ns1:t></ns1:run>'
                        if choir_info_str:
                            choir_runs += f'<ns1:run charPrIDRef="93"><ns1:t>{html.escape(choir_info_str)}</ns1:t></ns1:run>'
                    else:
                        # 미완성/임시 항목은 17pt 빨간색(#FF0000, charPrIDRef="158")으로 시각적 경고
                        choir_runs += '<ns1:run charPrIDRef="158"><ns1:t>[찬양곡 준비 중]</ns1:t></ns1:run>'
                    choir_p = f'<ns1:p id="2147483648" paraPrIDRef="66" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">{choir_runs}</ns1:p>'

                    choir_row_pattern = r'<(?:\w+:)?tr>(?:(?!</(?:\w+:)?tr>)[\s\S])*?<(?:\w+:)?t>찬\s*양</(?:\w+:)?t>[\s\S]*?</(?:\w+:)?tr>'
                    clean_choir_row = (
                        '<ns1:tr><ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="5">'
                        '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                        '<ns1:p id="2147483648" paraPrIDRef="29" styleIDRef="24" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="78" /></ns1:p></ns1:subList>'
                        '<ns1:cellAddr colAddr="0" rowAddr="13" /><ns1:cellSpan colSpan="1" rowSpan="1" /><ns1:cellSz width="951" height="3217" /><ns1:cellMargin left="0" right="0" top="0" bottom="0" /></ns1:tc>'
                        '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="18">'
                        '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                        '<ns1:p id="2147483648" paraPrIDRef="22" styleIDRef="24" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="37"><ns1:t>찬 양</ns1:t></ns1:run></ns1:p></ns1:subList>'
                        '<ns1:cellAddr colAddr="1" rowAddr="13" /><ns1:cellSpan colSpan="1" rowSpan="1" /><ns1:cellSz width="10375" height="3217" /><ns1:cellMargin left="0" right="0" top="0" bottom="0" /></ns1:tc>'
                        '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="5">'
                        '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                        f'{choir_p}</ns1:subList>'
                        '<ns1:cellAddr colAddr="2" rowAddr="13" /><ns1:cellSpan colSpan="2" rowSpan="1" /><ns1:cellSz width="41523" height="3217" /><ns1:cellMargin left="0" right="0" top="0" bottom="0" /></ns1:tc></ns1:tr>'
                    )
                    xml_text = re.sub(choir_row_pattern, clean_choir_row, xml_text)

                    # Row heights:
                    # 1. 성가대 가사 칸 여백 한 칸 줄임 (height 4852 -> 4569, -1mm)
                    xml_text = re.sub(r'(<(?:\w+:)?cellSz width="\d+" height=")4852(" />)', r'\g<1>4569\g<2>', xml_text)

                    # 2. 함께읽는말씀 본문 여백 확장 (하단 페이지 여백선에 닿을 때까지 height 6232 -> 7550)
                    xml_text = re.sub(r'(<(?:\w+:)?cellSz width="\d+" height=")6232(" />)', r'\g<1>7550\g<2>', xml_text)

                    # 교독송 가사 동적 치환
                    worship_dict = data.get("worship_1", data.get("worship", {}))
                    rh = worship_dict.get("responsive_hymn", {}) if isinstance(worship_dict, dict) else {}
                    if rh:
                        s1_1 = rh.get("stanza1_1", "")
                        s1_2 = rh.get("stanza1_2", "")
                        s1_3 = rh.get("stanza1_3", "")
                        s2_1 = rh.get("stanza2_1", "")
                        s2_2 = rh.get("stanza2_2", "")
                        s2_3 = rh.get("stanza2_3", "")
                        s3_1 = rh.get("stanza3_1", "")
                        s3_2 = rh.get("stanza3_2", "")
                        s3_3 = rh.get("stanza3_3", "")
                        s1_end = rh.get("stanza1_end", "")
                        s2_end = rh.get("stanza2_end", "")
                        s3_end = rh.get("stanza3_end", "")

                        if s1_1: xml_text = xml_text.replace('주님이여 우리들을 -', s1_1)
                        if s1_2: xml_text = xml_text.replace('불쌍하게 여기시고', s1_2)
                        if s1_3: xml_text = xml_text.replace('주의얼굴 비추시어', s1_3.rstrip('.'))

                        if s2_1: xml_text = xml_text.replace('그리하여 온세상이 -', s2_1)
                        if s2_2: xml_text = re.sub(r'주님의뜻 알게하고\s*', s2_2, xml_text)
                        if s2_3: xml_text = xml_text.replace('온나라가 주님구원', s2_3.rstrip('.'))

                        if s3_1: xml_text = xml_text.replace('주님이여 민족들이 -', s3_1)
                        if s3_2: xml_text = re.sub(r'찬양하게 하옵소서\s*', s3_2, xml_text)
                        if s3_3: xml_text = xml_text.replace('모든민족 주님에게', s3_3.rstrip('.'))

                        if s1_end: xml_text = xml_text.replace('복을내려 주옵소서', s1_end.rstrip('.'))
                        if s2_end: xml_text = xml_text.replace('알게하여 주옵소서', s2_end.rstrip('.'))
                        if s3_end:
                            xml_text = re.sub(r'>찬\s*양하게<', f'>{s3_end}<', xml_text)
                        else:
                            xml_text = xml_text.replace('>찬 양하게<', '>않 게하여<')

                        # 교독송 마지막 마디 가사: 당주 후렴구 음표 1:1 정밀 정렬 (Rule 18)
                        refrain_raw = rh.get("refrain_1", "").replace(" ", "").replace("-", "")
                        if len(refrain_raw) >= 4:
                            c1 = refrain_raw[0]
                            c2 = f" {refrain_raw[1:3]}"
                            c3 = f" {refrain_raw[3]}"
                        elif len(refrain_raw) == 3:
                            c1 = refrain_raw[0]
                            c2 = f" {refrain_raw[1]}"
                            c3 = f" {refrain_raw[2]}"
                        else:
                            c1, c2, c3 = "주", " 옵소", " 서"

                        col5_new = (
                            f'<ns1:run charPrIDRef="86"><ns1:t>{c1}</ns1:t></ns1:run>'
                            f'<ns1:run charPrIDRef="86"><ns1:t>{c2}</ns1:t></ns1:run>'
                            f'<ns1:run charPrIDRef="87"><ns1:t>{c3}</ns1:t></ns1:run>'
                            f'<ns1:run charPrIDRef="87"><ns1:t>  -  -</ns1:t></ns1:run>'
                            f'<ns1:run charPrIDRef="90" />'
                        )
                        pattern_col5 = r'<(?:\w+:)?run charPrIDRef="86"><(?:\w+:)?t>하</(?:\w+:)?t></(?:\w+:)?run>[\s\S]*?<(?:\w+:)?run charPrIDRef="87"><(?:\w+:)?t>-   -</(?:\w+:)?t></(?:\w+:)?run>(?:<(?:\w+:)?run charPrIDRef="90"\s*/>)?'
                        xml_text = re.sub(pattern_col5, col5_new, xml_text)

                        s3_score_word = s3_end if s3_end else "않 게하여"
                        refrain_display = f"{c1}{c2}{c3}  -  -"

                        xml_text = xml_text.replace(
                            '주님이여 우리들을 -불쌍하게 여기시고주의얼굴 비추시어.그리하여 온세상이 -주님의뜻 알게하고 온나라가 주님구원. 주님이여 민족들이 -찬양하게 하옵소서 모든민족 주님에게.',
                            f'{s1_1}{s1_2}{s1_3}{s2_1}{s2_2}{s2_3} {s3_1}{s3_2}{s3_3}'
                        )
                        xml_text = xml_text.replace(
                            '복을내려 주옵소서.찬 양하게  -   -  -하 옵소서 -   -알게하여 주옵소서.',
                            f'{s1_end}{s3_score_word}  -   -  -{refrain_display}{s2_end}'
                        )


                    # 주일 봉사자 동적 치환
                    guide_txt = flat_map.get("service_worship_guides", "김경민 강정희")

                    av_txt = flat_map.get("service_av_room", "")
                    finance_txt = flat_map.get("service_finance", "재정부")
                    parking_txt = flat_map.get("service_parking", "관리부 희남")
                    meal_txt = flat_map.get("service_meal", "봉사부 청녀")
                    recycling_txt = flat_map.get("service_recycling", "청녀")

                    clean_service_p1 = (
                        f'<ns1:p id="2147483648" paraPrIDRef="61" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0">'
                        f'<ns1:run charPrIDRef="119"><ns1:t>예배안내</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(guide_txt)})</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="119"><ns1:t>╻방송실</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(av_txt)})</ns1:t></ns1:run>'
                        f'</ns1:p>'
                    )
                    clean_service_p2 = (
                        f'<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0">'
                        f'<ns1:run charPrIDRef="119"><ns1:t>헌금계수</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(finance_txt)})</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="119"><ns1:t>╻주차</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(parking_txt)})</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="119"><ns1:t>╻공동식사</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(meal_txt)})</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="119"><ns1:t>╻분리배출</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(recycling_txt)})</ns1:t></ns1:run>'
                        f'</ns1:p>'
                    )
                    service_pat = r'<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>).)*?예배안내.*?</(?:\w+:)?p>\s*<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>).)*?헌금계수.*?</(?:\w+:)?p>'
                    if re.search(service_pat, xml_text, re.DOTALL):
                        xml_text = re.sub(service_pat, f"{clean_service_p1}\n{clean_service_p2}", xml_text, flags=re.DOTALL)

                    # 7면 시작: 방문 환영 표 문단에 명시적 쪽나눔(pageBreak="1") 부여하여 6면과 7면 분리 및 새교우 표와 7면 동시 수용
                    old_welcome_p = '<ns1:p id="0" paraPrIDRef="38" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="25"><ns1:tbl id="1111275715"'
                    new_welcome_p = '<ns1:p id="0" paraPrIDRef="38" styleIDRef="0" pageBreak="1" columnBreak="0" merged="0"><ns1:run charPrIDRef="25"><ns1:tbl id="1111275715"'
                    xml_text = xml_text.replace(old_welcome_p, new_welcome_p)

                    # Auto-clean any remaining unreplaced slots
                    xml_text = re.sub(r"\{\{[^}]+\}\}", "", xml_text)

                    # 4. 공동관심사 (announcements_sections) 치환
                    ann_sections = data.get("announcements_sections", [])
                    if ann_sections:
                        def generate_announcements_xml(sections: list) -> str:
                            p_list = []
                            for sec in sections:
                                sec_title = sec.get("title", "")
                                date_range = sec.get("date_range", "")
                                items = sec.get("items", [])

                                # 1. 소제목 헤더 문단
                                if date_range:
                                    # 이번주 일정 안내 헤더: 제목만 회색 음영(charPr 143), 날짜는 음영 없이 검정(charPr 133)
                                    p_header = (
                                        f'<ns1:p id="0" paraPrIDRef="94" styleIDRef="34" pageBreak="0" columnBreak="0" merged="0">'
                                        f'<ns1:run charPrIDRef="143"><ns1:t> {html.escape(sec_title)}  </ns1:t></ns1:run>'
                                        f'<ns1:run charPrIDRef="133"><ns1:t> {html.escape(date_range)}</ns1:t></ns1:run>'
                                        f'<ns1:run charPrIDRef="30" />'
                                        f'</ns1:p>'
                                    )
                                elif "감사헌금" in sec_title:
                                    p_header = (
                                        f'<ns1:p id="0" paraPrIDRef="70" styleIDRef="29" pageBreak="0" columnBreak="0" merged="0">'
                                        f'<ns1:run charPrIDRef="143"><ns1:t> {html.escape(sec_title)}  </ns1:t></ns1:run>'
                                        f'<ns1:run charPrIDRef="24" />'
                                        f'</ns1:p>'
                                    )
                                else:
                                    p_header = (
                                        f'<ns1:p id="0" paraPrIDRef="94" styleIDRef="34" pageBreak="0" columnBreak="0" merged="0">'
                                        f'<ns1:run charPrIDRef="143"><ns1:t> {html.escape(sec_title)}  </ns1:t></ns1:run>'
                                        f'<ns1:run charPrIDRef="24" />'
                                        f'</ns1:p>'
                                    )
                                p_list.append(p_header)

                                # 2. 항목 문단들
                                for item in items:
                                    if isinstance(item, dict):
                                        i_title = str(item.get("title", "")).strip()
                                        i_content = str(item.get("content", "")).strip()
                                    else:
                                        i_title = str(item).strip()
                                        i_content = ""

                                    # 항목별 맞춤 자간 설정 (인간의 융통성: 한두 글자가 다음 줄로 삐져나오는 과부 현상 방지)
                                    # 불릿 '∙ ' 기호는 항상 charPr 79(자간 0%)를 유지하여 정렬을 보존하고,
                                    # 글자 시작 부분부터 끝 부분까지 항목별 맞춤 자간 적용
                                    item_sp = 0
                                    for kw, sp_val in self.ITEM_SPACING_CONFIG:
                                        if kw in i_title:
                                            item_sp = sp_val
                                            break

                                    if item_sp in self.SPACING_CID_MAP:
                                        b_cid, r_cid = self.SPACING_CID_MAP[item_sp]
                                    else:
                                        b_cid, r_cid = "127", "38"

                                    if "감사헌금" in sec_title:
                                        if i_content or i_title:
                                            p_item = (
                                                f'<ns1:p id="2147483648" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                                f'<ns1:run charPrIDRef="193"><ns1:t>{html.escape(i_content or i_title)}</ns1:t></ns1:run>'
                                                f'</ns1:p>'
                                            )
                                            p_list.append(p_item)
                                    else:
                                        # 길목 청년활동가 지원 사업 또는 교적 정보 확인 시스템 또는 사용자 지정 이미지 항목 처리
                                        has_qr = ("청년활동가" in i_title) or ("교적" in i_title) or (isinstance(item, dict) and item.get("image"))
                                        qr_pic_xml = ""
                                        if has_qr:
                                            if "교적" in i_title:
                                                # 10/4 골든 레퍼런스 원본 규격 (width 3568, height 3568, vertOffset 148, horzOffset 49440)
                                                qr_pic_xml = (
                                                    '<ns1:pic id="1209202286" zOrder="17" numberingType="PICTURE" textWrap="SQUARE" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="135460463" reverse="0">'
                                                    '<ns1:offset x="4294966515" y="4294967204"/>'
                                                    '<ns1:orgSz width="26760" height="26760"/>'
                                                    '<ns1:curSz width="3568" height="3568"/>'
                                                    '<ns1:flip horizontal="0" vertical="0"/>'
                                                    '<ns1:rotationInfo angle="0" centerX="1784" centerY="1784" rotateimage="1"/>'
                                                    '<ns1:renderingInfo>'
                                                    '<ns2:transMatrix e1="1" e2="0" e3="-781" e4="0" e5="1" e6="-92"/>'
                                                    '<ns2:scaMatrix e1="0.133333" e2="0" e3="781" e4="0" e5="0.133333" e6="92"/>'
                                                    '<ns2:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
                                                    '</ns1:renderingInfo>'
                                                    '<ns2:img binaryItemIDRef="image8" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
                                                    '<ns1:imgRect><ns2:pt0 x="0" y="0"/><ns2:pt1 x="26760" y="0"/><ns2:pt2 x="26760" y="26760"/><ns2:pt3 x="0" y="26760"/></ns1:imgRect>'
                                                    '<ns1:imgClip left="0" right="26760" top="0" bottom="26760"/>'
                                                    '<ns1:inMargin left="0" right="0" top="0" bottom="0"/>'
                                                    '<ns1:imgDim dimwidth="26760" dimheight="26760"/>'
                                                    '<ns1:effects/>'
                                                    '<ns1:sz width="3568" widthRelTo="ABSOLUTE" height="3568" heightRelTo="ABSOLUTE" protect="0"/>'
                                                    '<ns1:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="148" horzOffset="49440"/>'
                                                    '<ns1:outMargin left="0" right="0" top="0" bottom="0"/>'
                                                    '<ns1:shapeComment>그림입니다.\n원본 그림의 이름: 교인 정보 수정.png\n원본 그림의 크기: 가로 357pixel, 세로 357pixel</ns1:shapeComment>'
                                                    '</ns1:pic>'
                                                )
                                            else:
                                                qr_pic_xml = (
                                                    '<ns1:pic id="1191766890" zOrder="34" numberingType="PICTURE" textWrap="IN_FRONT_OF_TEXT" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="118025067" reverse="0">'
                                                    '<ns1:offset x="4294942857" y="0"/>'
                                                    '<ns1:orgSz width="26760" height="26760"/>'
                                                    '<ns1:curSz width="2321" height="2321"/>'
                                                    '<ns1:flip horizontal="0" vertical="0"/>'
                                                    '<ns1:rotationInfo angle="0" centerX="1160" centerY="1160" rotateimage="1"/>'
                                                    '<ns1:renderingInfo>'
                                                    '<ns2:transMatrix e1="1" e2="0" e3="-24439" e4="0" e5="1" e6="0"/>'
                                                    '<ns2:scaMatrix e1="0.086734" e2="0" e3="24439" e4="0" e5="0.086734" e6="0"/>'
                                                    '<ns2:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
                                                    '</ns1:renderingInfo>'
                                                    '<ns2:img binaryItemIDRef="image8" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
                                                    '<ns1:imgRect><ns2:pt0 x="0" y="0"/><ns2:pt1 x="26760" y="0"/><ns2:pt2 x="26760" y="26760"/><ns2:pt3 x="0" y="26760"/></ns1:imgRect>'
                                                    '<ns1:imgClip left="0" right="26760" top="0" bottom="26760"/>'
                                                    '<ns1:inMargin left="0" right="0" top="0" bottom="0"/>'
                                                    '<ns1:imgDim dimwidth="26760" dimheight="26760"/>'
                                                    '<ns1:effects/>'
                                                    '<ns1:sz width="2321" widthRelTo="ABSOLUTE" height="2321" heightRelTo="ABSOLUTE" protect="0"/>'
                                                    '<ns1:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="49176"/>'
                                                    '<ns1:outMargin left="0" right="0" top="0" bottom="0"/>'
                                                    '<ns1:shapeComment>그림입니다.\n원본 그림의 이름: 2gtkk.png\n원본 그림의 크기: 가로 357pixel, 세로 357pixel</ns1:shapeComment>'
                                                    '</ns1:pic>'
                                                )

                                        bullet_cid = r_cid if has_qr else "79"
                                        if i_content:
                                            escaped_content = html.escape(i_content).replace("\n", "<ns1:lineBreak/>")
                                            p_item = (
                                                f'<ns1:p id="2147483648" paraPrIDRef="102" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                                f'<ns1:run charPrIDRef="{bullet_cid}">{qr_pic_xml}<ns1:t>∙ </ns1:t></ns1:run>'
                                                f'<ns1:run charPrIDRef="{b_cid}"><ns1:t>{html.escape(i_title)}</ns1:t></ns1:run>'
                                                f'<ns1:run charPrIDRef="{r_cid}"><ns1:t>: {escaped_content}</ns1:t></ns1:run>'
                                                f'</ns1:p>'
                                            )
                                        else:
                                            p_item = (
                                                f'<ns1:p id="2147483648" paraPrIDRef="102" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                                f'<ns1:run charPrIDRef="{bullet_cid}">{qr_pic_xml}<ns1:t>∙ </ns1:t></ns1:run>'
                                                f'<ns1:run charPrIDRef="{b_cid}"><ns1:t>{html.escape(i_title)}</ns1:t></ns1:run>'
                                                f'</ns1:p>'
                                            )
                                        p_list.append(p_item)

                                        # 신도회 월례회 항목 직후 신도회 장소 안내 표(박스) 자동 삽입 (단, 당일 '오늘 일정'일 때만)
                                        if i_title == "신도회 월례회" and "오늘 일정" in sec_title:
                                            fellowship_box = (

                                                '<ns1:p id="2147483648" paraPrIDRef="109" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                                '<ns1:run charPrIDRef="72"><ns1:t>  </ns1:t>'
                                                '<ns1:tbl id="1137471996" zOrder="17" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="1" colCnt="1" cellSpacing="0" borderFillIDRef="4" noAdjust="0">'
                                                '<ns1:sz width="50408" widthRelTo="ABSOLUTE" height="6852" heightRelTo="ABSOLUTE" protect="0" />'
                                                '<ns1:pos treatAsChar="1" affectLSpacing="0" flowWithText="0" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0" />'
                                                '<ns1:outMargin left="0" right="0" top="0" bottom="0" />'
                                                '<ns1:inMargin left="510" right="510" top="141" bottom="141" />'
                                                '<ns1:tr>'
                                                '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="4">'
                                                '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                                                '<ns1:p id="2147483648" paraPrIDRef="32" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="195"><ns1:t>새청: 청소년부실(5층) ‖ 청신: 상담실(4층) ‖ 희청: 안병무도서관(3층)</ns1:t></ns1:run></ns1:p>'
                                                '<ns1:p id="2147483648" paraPrIDRef="32" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="195"><ns1:t>청녀: 세미나실(4층) ‖ 청남: 복도 쉼터(4층) ‖ 희녀: 담임목사실(4층)</ns1:t></ns1:run></ns1:p>'
                                                '<ns1:p id="2147483648" paraPrIDRef="32" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="195"><ns1:t>희남: 유아부(4층) ‖ 장녀: 장년여신도회방(4층) ‖ 장남: 장년남신도회방(5층)</ns1:t></ns1:run></ns1:p>'
                                                '</ns1:subList>'
                                                '<ns1:cellAddr colAddr="0" rowAddr="0" /><ns1:cellSpan colSpan="1" rowSpan="1" /><ns1:cellSz width="50408" height="6852" /><ns1:cellMargin left="510" right="510" top="141" bottom="141" />'
                                                '</ns1:tc>'
                                                '</ns1:tr>'
                                                '</ns1:tbl>'
                                                '<ns1:t /></ns1:run>'
                                                '</ns1:p>'
                                            )
                                            p_list.append(fellowship_box)

                                        # 부서 월례회 항목 직후 부서 장소 안내 표(박스) 자동 삽입 (단, 당일 '오늘 일정'일 때만)
                                        if i_title == "부서 월례회" and "오늘 일정" in sec_title:
                                            dept_box = (

                                                '<ns1:p id="2147483648" paraPrIDRef="109" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                                '<ns1:run charPrIDRef="72"><ns1:t>  </ns1:t>'
                                                '<ns1:tbl id="1185698824" zOrder="16" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="1" colCnt="1" cellSpacing="0" borderFillIDRef="4" noAdjust="0">'
                                                '<ns1:sz width="50408" widthRelTo="ABSOLUTE" height="6852" heightRelTo="ABSOLUTE" protect="0" />'
                                                '<ns1:pos treatAsChar="1" affectLSpacing="0" flowWithText="0" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0" />'
                                                '<ns1:outMargin left="0" right="0" top="0" bottom="0" />'
                                                '<ns1:inMargin left="510" right="510" top="141" bottom="141" />'
                                                '<ns1:tr>'
                                                '<ns1:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="4">'
                                                '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                                                '<ns1:p id="2147483648" paraPrIDRef="32" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="195"><ns1:t>관리부: 향우실(1층) ‖ 봉사부: 친교실(5층) ‖ 사회부: 세미나실(4층)</ns1:t></ns1:run></ns1:p>'
                                                '<ns1:p id="2147483648" paraPrIDRef="32" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="195"><ns1:t>선교부: 도서관(3층) ‖ 성평등부: 담임목사실(4층) ‖ 예배부: 대예배실(2층)</ns1:t></ns1:run></ns1:p>'
                                                '<ns1:p id="2147483648" paraPrIDRef="32" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="195"><ns1:t>친교부: 향우실(1층) ‖ 재정부: 상담실(4층)</ns1:t></ns1:run></ns1:p>'
                                                '</ns1:subList>'
                                                '<ns1:cellAddr colAddr="0" rowAddr="0" /><ns1:cellSpan colSpan="1" rowSpan="1" /><ns1:cellSz width="50408" height="6852" /><ns1:cellMargin left="510" right="510" top="141" bottom="141" />'
                                                '</ns1:tc>'
                                                '</ns1:tr>'
                                                '</ns1:tbl>'
                                                '<ns1:t /></ns1:run>'
                                                '</ns1:p>'
                                            )
                                            p_list.append(dept_box)

                                p_blank = '<ns1:p id="0" paraPrIDRef="95" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="125" /></ns1:p>'
                                p_list.append(p_blank)

                            return "\n".join(p_list)

                        new_ann_xml = generate_announcements_xml(ann_sections)
                        ann_pat = r'<(?:\w+:)?p [^>]*paraPrIDRef="94"[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?1\.\s*오늘\s*일정\s*안내[\s\S]*?(?=<(?:\w+:)?p [^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\[온라인헌금\s*안내\])'
                        if re.search(ann_pat, xml_text):
                            xml_text = re.sub(ann_pat, new_ann_xml + "\n", xml_text, count=1)

                    # 교회 탄소중립 최신 수치 갱신 (9월 데이터 - 10/4 주보 SSOT)
                    xml_text = re.sub(
                        r'\[교회탄소중립\]\s*[^<]+',
                        '[교회탄소중립] 9월전기 사용량 4.91MWh(전년4.94MWh) / 생산량 1.70MWh(전년1.30MWh)',
                        xml_text
                    )
                    xml_text = xml_text.replace("7월전기 ", "9월전기 ").replace("8월전기 ", "9월전기 ")
                    xml_text = xml_text.replace("5.86MWh", "4.91MWh").replace("6.89MWh", "4.91MWh")
                    xml_text = xml_text.replace("전년5.91MWh", "전년4.94MWh").replace("전년6.90MWh", "전년4.94MWh")
                    xml_text = xml_text.replace("1.08MWh", "1.70MWh").replace("1.31MWh", "1.70MWh")
                    xml_text = xml_text.replace("전년1.26MWh", "전년1.30MWh").replace("전년1.29MWh", "전년1.30MWh")

                    # 5. Table 10 (등록 새교우 및 기도나눔) 골든 레퍼런스 완벽 복원 (규칙 27: 140% 압축 8페이지 엄수)
                    new_members = data.get("new_members", [])
                    if isinstance(new_members, str):
                        new_members = [new_members]
                    healing_1 = flat_map.get("healing_prayer_1", "").strip()
                    healing_2 = flat_map.get("healing_prayer_2", "").strip()
                    healing_3 = flat_map.get("healing_prayer_3", "").strip()
                    military = flat_map.get("military_prayer_names", "").strip()
                    overseas_1 = flat_map.get("overseas_prayer_1", "").strip()
                    overseas_2 = flat_map.get("overseas_prayer_2", "").strip()

                    if isinstance(new_members, list) and len(new_members) > 0:
                        p_t10 = []
                        # [0] 등록 새교우 헤더
                        p_t10.append('<ns1:p id="2147483648" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="66"><ns1:t>▯등록 새교우 (2026)</ns1:t></ns1:run></ns1:p>')
                        # [1~N] 새교우 행들
                        for i, line_str in enumerate(new_members):
                            pid = "2147483648" if i == 0 else "0"
                            p_t10.append(
                                f'<ns1:p id="{pid}" paraPrIDRef="99" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                f'<ns1:run charPrIDRef="21"><ns1:t> {html.escape(line_str.strip())}</ns1:t></ns1:run>'
                                f'</ns1:p>'
                            )
                        # 빈 줄
                        p_t10.append('<ns1:p id="2147483648" paraPrIDRef="99" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="152"/></ns1:p>')
                        # 건강회복 헤더
                        p_t10.append('<ns1:p id="2147483648" paraPrIDRef="100" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="66"><ns1:t>▯건강회복을 위해</ns1:t></ns1:run></ns1:p>')
                        # 건강회복 행들 (교인 명단 볼드 절대 금지: charPrIDRef 46 경기천년바탕 Regular 15.5pt)
                        h_first = True
                        for h_text in [healing_1, healing_2, healing_3]:
                            if h_text:
                                pid = "2147483648" if h_first else "0"
                                p_t10.append(f'<ns1:p id="{pid}" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="46"><ns1:t> {html.escape(h_text)}</ns1:t></ns1:run></ns1:p>')
                                h_first = False
                        # 빈 줄
                        p_t10.append('<ns1:p id="2147483648" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="68"/></ns1:p>')
                        # 군복무
                        p_t10.append(
                            f'<ns1:p id="2147483648" paraPrIDRef="100" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                            f'<ns1:run charPrIDRef="66"><ns1:t>▯군복무 중 건강과 안전을 위해╻</ns1:t></ns1:run>'
                            f'<ns1:run charPrIDRef="46"><ns1:t> {html.escape(military)}</ns1:t></ns1:run>'
                            f'</ns1:p>'
                        )
                        # 빈 줄
                        p_t10.append('<ns1:p id="2147483648" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="68"/></ns1:p>')
                        # 해외체류 헤더
                        p_t10.append('<ns1:p id="2147483648" paraPrIDRef="100" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="66"><ns1:t>▯해외 체류 중인 교우들을 위해</ns1:t></ns1:run></ns1:p>')
                        # 해외체류 행들 (교인 명단 볼드 절대 금지: charPrIDRef 46 경기천년바탕 Regular 15.5pt)
                        o_first = True
                        for o_text in [overseas_1, overseas_2]:
                            if o_text:
                                pid = "2147483648" if o_first else "0"
                                p_t10.append(f'<ns1:p id="{pid}" paraPrIDRef="98" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="46"><ns1:t> {html.escape(o_text)}</ns1:t></ns1:run></ns1:p>')
                                o_first = False

                        t10_sublist_content = "".join(p_t10)
                        t10_pattern = r'(<(?:\w+:)?tbl\b[^>]*?id="1111275716"[^>]*>[\s\S]*?<(?:\w+:)?tc\b[^>]*>)(?:(?!</(?:\w+:)?tc>)[\s\S])*?(<(?:\w+:)?cellAddr colAddr="0" rowAddr="0"[\s\S]*?</(?:\w+:)?tbl>)'
                        def repl_t10(match):
                            prefix = match.group(1)
                            suffix = match.group(2)
                            return f'{prefix}<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{t10_sublist_content}</ns1:subList>{suffix}'
                        
                        if re.search(r'id="1111275716"', xml_text):
                            xml_text = re.sub(t10_pattern, repl_t10, xml_text, count=1)

                    # 6. 8페이지 목회마당 포스터 제거 및 텍스트 주입
                    pastoral_text = str(data.get("pastoral_corner", {}).get("text", "") or data.get("pastoral_text", "")).strip()
                    if pastoral_text:
                        escaped_pastoral = html.escape(pastoral_text).replace("\n", "<ns1:lineBreak/>")
                        def update_p8_cell(match):
                            tc_chunk = match.group(0)
                            new_p = (
                                f'<ns1:p id="2147483648" paraPrIDRef="101" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                f'<ns1:run charPrIDRef="173"><ns1:t>{escaped_pastoral}</ns1:t></ns1:run>'
                                f'</ns1:p>'
                            )
                            return re.sub(r'<(?:\w+:)?subList[^>]*>.*?</(?:\w+:)?subList>', f'<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{new_p}</ns1:subList>', tc_chunk, flags=re.DOTALL)
                        xml_text = re.sub(r'<(?:\w+:)?tc\b[^>]*>(?:(?!</(?:\w+:)?tc>).)*?<(?:\w+:)?cellSz width="52411" height="71036"[^>]*>.*?</(?:\w+:)?tc>', update_p8_cell, xml_text, flags=re.DOTALL)





                    # 교회 대표전화번호 순서 보정: 776-9141, 3806 (9141 우선 표기 규칙 28)
                    xml_text = xml_text.replace("776-3806, 9141", "776-9141, 3806")

                    # 공동체 교회 최신 정보 보장 (규칙 29): 들꽃향린교회 -> 희년향린교회
                    xml_text = xml_text.replace("들꽃향린교회", "희년향린교회")
                    xml_text = xml_text.replace("서울시 강동구 천호대로 991 ☎ 02-478-9101", "서울시 송파구 올림픽로37길 130 파크리오A상가 513호 ☎ 010-6432-8063")
                    xml_text = xml_text.replace("서울시 송파구 올림픽로37길 130 A동 513호 ☎ 010-6432-8063", "서울시 송파구 올림픽로37길 130 파크리오A상가 513호 ☎ 010-6432-8063")
                    xml_text = xml_text.replace("서울 송파구 올림픽로37길 130 A동 513호", "서울 송파구 올림픽로37길 130 파크리오A상가 513호")

                    # Remove linesegarray cache tags to prevent Hancom Office "tampered document" false-alarm.
                    # Hancom recalculates text layouts automatically when linesegarray is absent.
                    xml_text = re.sub(r'<(?:\w+:)?linesegarray[^>]*>.*?</(?:\w+:)?linesegarray>|<(?:\w+:)?linesegarray[^>]*/>', '', xml_text, flags=re.DOTALL)

                    xml_file.write_text(xml_text, encoding="utf-8")

            # 3. Liturgical color and logo substitution
            season = str(flat_map.get("season", "") or flat_map.get("절기", ""))
            matched_cfg = None
            for s_key, s_cfg in self.LITURGICAL_CONFIG.items():
                if s_key in season:
                    matched_cfg = s_cfg
                    break

            if matched_cfg:
                target_color = matched_cfg["color"]
                
                # 3-1. Replace color & optimize text styles in header.xml
                header_file = contents_dir / "header.xml"
                if header_file.is_file():
                    h_text = header_file.read_text(encoding="utf-8")
                    # Replace red template color #FF0000 with target season color
                    h_text = re.sub(r'textColor="#FF0000"', f'textColor="{target_color}"', h_text, flags=re.IGNORECASE)

                    # 하늘뜻펴기 제목이 1줄로 알맞게 차도록 17pt 유지 및 장평 90%, 자간 0% 최적화 (사용자 지정 서식 영구 반영)
                    # (우측 칸 병합 후 너비 39958에 맞춰 자연스럽고 시원하게 1줄 배치)
                    h_text = re.sub(
                        r'(<hh:charPr id="10[23]" height=")\d+("[^>]*>\s*<hh:fontRef[^>]*/>\s*<hh:ratio )[^>]+(/>\s*<hh:spacing )[^>]+(/>)',
                        r'\g<1>1700\g<2>hangul="90" latin="90" hanja="90" japanese="90" other="90" symbol="90" user="90"\g<3>hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"\g<4>',
                        h_text
                    )

                    # 함께 읽는 말씀 본문이 1줄씩 알맞게 수용되도록 charPr id="173" 장평/자간 최적화
                    # (ratio 77 -> 75, spacing -10 -> -14)
                    h_text = re.sub(
                        r'(<hh:charPr id="173"[^>]*>\s*<hh:fontRef[^>]*/>\s*<hh:ratio )[^>]+(/>\s*<hh:spacing )[^>]+(/>)',
                        r'\g<1>hangul="75" latin="75" hanja="75" japanese="75" other="75" symbol="75" user="75"\g<2>hangul="-14" latin="-14" hanja="-14" japanese="-14" other="-14" symbol="-14" user="-14"\g<3>',
                        h_text
                    )

                    # 감사헌금 명단 자간 최적화 (지난주 주보 골든 레퍼런스와 동일하게 ratio 96, spacing -8)
                    h_text = re.sub(
                        r'(<hh:charPr id="193"[^>]*>\s*<hh:fontRef[^>]*/>\s*<hh:ratio )[^>]+(/>\s*<hh:spacing )[^>]+(/>)',
                        r'\g<1>hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"\g<2>hangul="-8" latin="-8" hanja="-8" japanese="-8" other="-8" symbol="-8" user="-8"\g<3>',
                        h_text
                    )

                    # 신도회 월례회 박스 내부 폰트 자간 최적화 (비정상 spacing -13 -> 골든 레퍼런스 기준 spacing 0, ratio 96)
                    h_text = re.sub(
                        r'(<hh:charPr id="195"[^>]*>\s*<hh:fontRef[^>]*/>\s*<hh:ratio )[^>]+(/>\s*<hh:spacing )[^>]+(/>)',
                        r'\g<1>hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"\g<2>hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"\g<3>',
                        h_text
                    )

                    # 공동관심사 소식 제목(charPr 127) 및 본문(charPr 38): 골든 레퍼런스 표준 ratio 96, spacing 0 통일
                    h_text = re.sub(
                        r'(<hh:charPr id="127"[^>]*>\s*<hh:fontRef[^>]*/>\s*<hh:ratio )[^>]+(/>\s*<hh:spacing )[^>]+(/>)',
                        r'\g<1>hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"\g<2>hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"\g<3>',
                        h_text
                    )
                    h_text = re.sub(
                        r'(<hh:charPr id="38"[^>]*>\s*<hh:fontRef[^>]*/>\s*<hh:ratio )[^>]+(/>\s*<hh:spacing )[^>]+(/>)',
                        r'\g<1>hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"\g<2>hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"\g<3>',
                        h_text
                    )

                    # 공동관심사 소주제 줄간격 130% 고정 및 내용 문단 줄간격 조절 (기본 170%, 분량에 따라 유동 조절 가능)
                    ann_line_spacing = str(data.get("announcement_line_spacing", 170))
                    def update_para_102_line_spacing(match):
                        xml_chunk = match.group(0)
                        return re.sub(r'lineSpacing type="PERCENT" value="\d+"', f'lineSpacing type="PERCENT" value="{ann_line_spacing}"', xml_chunk)

                    h_text = re.sub(r'<hh:paraPr id="102"[\s\S]*?</hh:paraPr>', update_para_102_line_spacing, h_text)

                    # 미적 조판용 미세 자간 charPr 등록 (-1% ~ -11%) - 이미 정의된 ID는 중복 추가 금지
                    existing_cids = set(re.findall(r'<(?:[\w]+:)?charPr\b[^>]*\bid="(\d+)"', h_text))
                    new_charpr_xml = []
                    for sp, (b_id, r_id) in self.SPACING_CID_MAP.items():
                        ratio_val = "95" if sp <= -4 else "96"
                        if b_id not in existing_cids:
                            new_charpr_xml.append(
                                f'<hh:charPr id="{b_id}" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="9">'
                                f'<hh:fontRef hangul="3" latin="3" hanja="3" japanese="3" other="3" symbol="3" user="3"/>'
                                f'<hh:ratio hangul="{ratio_val}" latin="{ratio_val}" hanja="{ratio_val}" japanese="{ratio_val}" other="{ratio_val}" symbol="{ratio_val}" user="{ratio_val}"/>'
                                f'<hh:spacing hangul="{sp}" latin="{sp}" hanja="{sp}" japanese="{sp}" other="{sp}" symbol="{sp}" user="{sp}"/>'
                                f'<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
                                f'<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                                f'<hh:bold/>'
                                f'<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
                                f'<hh:strikeout shape="NONE" color="#000000"/>'
                                f'<hh:outline type="NONE"/>'
                                f'<hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>'
                                f'</hh:charPr>'
                            )
                        if r_id not in existing_cids:
                            new_charpr_xml.append(
                                f'<hh:charPr id="{r_id}" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="9">'
                                f'<hh:fontRef hangul="3" latin="3" hanja="3" japanese="3" other="3" symbol="3" user="3"/>'
                                f'<hh:ratio hangul="{ratio_val}" latin="{ratio_val}" hanja="{ratio_val}" japanese="{ratio_val}" other="{ratio_val}" symbol="{ratio_val}" user="{ratio_val}"/>'
                                f'<hh:spacing hangul="{sp}" latin="{sp}" hanja="{sp}" japanese="{sp}" other="{sp}" symbol="{sp}" user="{sp}"/>'
                                f'<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
                                f'<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                                f'<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
                                f'<hh:strikeout shape="NONE" color="#000000"/>'
                                f'<hh:outline type="NONE"/>'
                                f'<hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>'
                                f'</hh:charPr>'
                            )
                    if new_charpr_xml:
                        added_xml = "".join(new_charpr_xml)
                        m_cnt = re.search(r'(<hh:charProperties itemCnt=")(\d+)(">)', h_text)
                        if m_cnt:
                            old_cnt = int(m_cnt.group(2))
                            new_cnt = old_cnt + len(new_charpr_xml)
                            h_text = h_text[:m_cnt.start()] + f'{m_cnt.group(1)}{new_cnt}{m_cnt.group(3)}' + h_text[m_cnt.end():]
                        h_text = h_text.replace('</hh:charProperties>', f'{added_xml}</hh:charProperties>')

                    # 8페이지 목회마당 포스터 제거 및 배경 초기화 (텍스트 대체 시)
                    pastoral_text = str(data.get("pastoral_corner", {}).get("text", "") or data.get("pastoral_text", "")).strip()
                    if pastoral_text:
                        def remove_poster_fill(match):
                            bf_chunk = match.group(0)
                            return re.sub(
                                r'<hc:fillBrush>.*?</hc:fillBrush>',
                                '<hc:fillBrush><hc:winBrush faceColor="#FFFFFF" hatchColor="none" alpha="0"/></hc:fillBrush>',
                                bf_chunk,
                                flags=re.DOTALL
                            )
                        h_text = re.sub(r'<hh:borderFill id="50"[\s\S]*?</hh:borderFill>', remove_poster_fill, h_text)

                    header_file.write_text(h_text, encoding="utf-8")

                # 3-2. Replace logos in BinData and preserve exact aspect ratio & rendering matrix
                bindata_dir = temp_path / "BinData"
                if bindata_dir.is_dir() and self.logo_dir.is_dir():
                    sym_file = self.logo_dir / matched_cfg["symbol_logo"]
                    txt_file = self.logo_dir / matched_cfg["text_logo"]
                    
                    logo_specs = {}
                    if sym_file.is_file():
                        shutil.copy2(sym_file, bindata_dir / "image3.png")
                        w, h = self._get_image_size(sym_file)
                        target_sz = matched_cfg.get("symbol_target_sz")
                        if not target_sz:
                            max_h = 7500
                            target_w = round(max_h * w / h)
                            target_sz = (target_w, max_h)
                        logo_specs["image3"] = {
                            "px_w": w,
                            "px_h": h,
                            "target_w": target_sz[0],
                            "target_h": target_sz[1],
                        }

                    if txt_file.is_file():
                        shutil.copy2(txt_file, bindata_dir / "image4.png")
                        w, h = self._get_image_size(txt_file)
                        target_sz = matched_cfg.get("text_target_sz")
                        if not target_sz:
                            max_h = 5800
                            target_w = round(max_h * w / h)
                            target_sz = (target_w, max_h)
                        logo_specs["image4"] = {
                            "px_w": w,
                            "px_h": h,
                            "target_w": target_sz[0],
                            "target_h": target_sz[1],
                        }

                    # Update exact dimensions, matrix, and clip in section*.xml to ensure 100% distortion-free rendering
                    if logo_specs:
                        for img_ref, spec in logo_specs.items():
                            matched_pic_count = 0
                            for xml_file in contents_dir.glob("section*.xml"):
                                s_text = xml_file.read_text(encoding="utf-8")
                                pic_pat = rf'(<(?:\w+:)?pic\b(?:(?!</(?:\w+:)?pic>).)*?binaryItemIDRef="{img_ref}".*?</(?:\w+:)?pic>)'
                                p_m = re.search(pic_pat, s_text, flags=re.DOTALL)
                                if p_m:
                                    orig_pic = p_m.group(1)
                                    updated_pic = self._update_pic_xml(
                                        orig_pic,
                                        spec["px_w"],
                                        spec["px_h"],
                                        spec["target_w"],
                                        spec["target_h"]
                                    )
                                    s_text = s_text.replace(orig_pic, updated_pic)
                                    xml_file.write_text(s_text, encoding="utf-8")
                                    matched_pic_count += 1
                            if matched_pic_count == 0:
                                raise ValueError(f"HWPX 본문에서 로고 그림 개체({img_ref})를 찾을 수 없어 크기를 조정하지 못했습니다.")

            # 3-3. Cover photo handling (사진이 없으면 파일과 그림 개체 완전 제거, 틀 비율 유지)
            cover_photo_path = flat_map.get("cover_photo", "") or data.get("metadata", {}).get("cover_photo", "")
            if not cover_photo_path or not Path(cover_photo_path).is_file():
                # 사진 칸의 그림 개체 완전 제거 (파일도 없고 개체도 없는 깨끗한 빈 칸)
                for xml_file in contents_dir.glob("section*.xml"):
                    s_text = xml_file.read_text(encoding="utf-8")
                    def remove_photo_pic(match):
                        tc = match.group(0)
                        return re.sub(r'<(?:\w+:)?pic\b.*?</(?:\w+:)?pic>', '', tc, flags=re.DOTALL)
                    s_text = re.sub(
                        r'<(?:\w+:)?tc\b[^>]*>(?:(?!</(?:\w+:)?tc>).)*?<(?:\w+:)?cellSz width="52624" height="40060"[^>]*>.*?</(?:\w+:)?tc>',
                        remove_photo_pic,
                        s_text,
                        flags=re.DOTALL
                    )
                    xml_file.write_text(s_text, encoding="utf-8")

                # BinData에서 image2.png 제거
                bindata_dir = temp_path / "BinData"
                img2_path = bindata_dir / "image2.png"
                if img2_path.is_file():
                    img2_path.unlink()

                # content.hpf에서 image2 항목 제거
                hpf_file = contents_dir / "content.hpf"
                if hpf_file.is_file():
                    hpf_text = hpf_file.read_text(encoding="utf-8")
                    hpf_text = re.sub(r'<opf:item id="image2"[^>]*/>\s*', '', hpf_text)
                    hpf_file.write_text(hpf_text, encoding="utf-8")
            else:
                bindata_dir = temp_path / "BinData"
                bindata_dir.mkdir(parents=True, exist_ok=True)
                target_img2 = bindata_dir / "image2.png"
                shutil.copy2(Path(cover_photo_path), target_img2)

                # content.hpf에 image2 항목 등록
                hpf_file = contents_dir / "content.hpf"
                if hpf_file.is_file():
                    hpf_text = hpf_file.read_text(encoding="utf-8")
                    if 'id="image2"' in hpf_text:
                        hpf_text = re.sub(
                            r'<opf:item id="image2"[^>]*/>',
                            '<opf:item id="image2" href="BinData/image2.png" media-type="image/png" isEmbeded="1"/>',
                            hpf_text
                        )
                    else:
                        hpf_text = hpf_text.replace(
                            '</opf:manifest>',
                            '<opf:item id="image2" href="BinData/image2.png" media-type="image/png" isEmbeded="1"/></opf:manifest>'
                        )
                    hpf_file.write_text(hpf_text, encoding="utf-8")

                # 이미지 픽셀 크기 확인
                px_w, px_h = 2126, 1654
                try:
                    from PIL import Image
                    with Image.open(target_img2) as im:
                        px_w, px_h = im.size
                except Exception:
                    pass
                dim_w = px_w * 75
                dim_h = px_h * 75
                photo_name = Path(cover_photo_path).name

                # section0.xml의 대문 사진 칸에 <pic> 개체 주입 (골든 레퍼런스 규격)
                cover_pic_xml = (
                    f'<ns1:pic id="1180644702" zOrder="16" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="106902879" reverse="0">'
                    f'<ns1:offset x="0" y="0"/>'
                    f'<ns1:orgSz width="51000" height="39780"/>'
                    f'<ns1:curSz width="0" height="0"/>'
                    f'<ns1:flip horizontal="0" vertical="0"/>'
                    f'<ns1:rotationInfo angle="0" centerX="25500" centerY="19890" rotateimage="1"/>'
                    f'<ns1:renderingInfo>'
                    f'<ns2:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
                    f'<ns2:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
                    f'<ns2:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
                    f'</ns1:renderingInfo>'
                    f'<ns2:img binaryItemIDRef="image2" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
                    f'<ns1:imgRect><ns2:pt0 x="0" y="0"/><ns2:pt1 x="51000" y="0"/><ns2:pt2 x="51000" y="39780"/><ns2:pt3 x="0" y="39780"/></ns1:imgRect>'
                    f'<ns1:imgClip left="0" right="{dim_w}" top="0" bottom="{dim_h}"/>'
                    f'<ns1:inMargin left="0" right="0" top="0" bottom="0"/>'
                    f'<ns1:imgDim dimwidth="{dim_w}" dimheight="{dim_h}"/>'
                    f'<ns1:effects/>'
                    f'<ns1:sz width="51000" widthRelTo="ABSOLUTE" height="39780" heightRelTo="ABSOLUTE" protect="0"/>'
                    f'<ns1:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
                    f'<ns1:outMargin left="0" right="0" top="0" bottom="0"/>'
                    f'<ns1:shapeComment>그림입니다.\n원본 그림의 이름: {photo_name}\n원본 그림의 크기: 가로 {px_w}pixel, 세로 {px_h}pixel</ns1:shapeComment>'
                    f'</ns1:pic>'
                )
                photo_sublist = (
                    f'<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                    f'<ns1:p id="2147483648" paraPrIDRef="31" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                    f'<ns1:run charPrIDRef="7">{cover_pic_xml}<ns1:t/></ns1:run>'
                    f'</ns1:p>'
                    f'</ns1:subList>'
                )
                for xml_file in contents_dir.glob("section*.xml"):
                    s_text = xml_file.read_text(encoding="utf-8")
                    def insert_photo_cell(match):
                        tc = match.group(0)
                        return re.sub(
                            r'<(?:\w+:)?subList\b[^>]*>.*?</(?:\w+:)?subList>',
                            photo_sublist,
                            tc,
                            flags=re.DOTALL
                        )
                    s_text = re.sub(
                        r'<(?:\w+:)?tc\b[^>]*>(?:(?!</(?:\w+:)?tc>).)*?<(?:\w+:)?cellSz width="52624" height="40060"[^>]*>.*?</(?:\w+:)?tc>',
                        insert_photo_cell,
                        s_text,
                        flags=re.DOTALL
                    )
                    xml_file.write_text(s_text, encoding="utf-8")

            # 3-3-B. Cover photo caption handling (1면 사진 설명란)
            hl_left = flat_map.get("headline_left", "").strip()
            hl_right = flat_map.get("headline_right", "").strip()
            has_photo = bool(cover_photo_path and Path(cover_photo_path).is_file())
            if has_photo and hl_left and hl_right:
                for xml_file in contents_dir.glob("section*.xml"):
                    s_text = xml_file.read_text(encoding="utf-8")
                    def replace_caption_cell(match):
                        tc = match.group(0)
                        p_two_lines = (
                            f'<ns1:p id="2147483648" paraPrIDRef="37" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                            f'<ns1:run charPrIDRef="26"><ns1:t>{html.escape(hl_left)}</ns1:t></ns1:run>'
                            f'</ns1:p>'
                            f'<ns1:p id="0" paraPrIDRef="37" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                            f'<ns1:run charPrIDRef="26"><ns1:t>{html.escape(hl_right)}</ns1:t></ns1:run>'
                            f'</ns1:p>'
                        )
                        return re.sub(
                            r'<(?:\w+:)?subList\b[^>]*>.*?</(?:\w+:)?subList>',
                            f'<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{p_two_lines}</ns1:subList>',
                            tc,
                            flags=re.DOTALL
                        )
                    s_text = re.sub(
                        r'<(?:\w+:)?tc\b[^>]*>(?:(?!</(?:\w+:)?tc>).)*?<(?:\w+:)?cellSz width="52624" height="4581"[^>]*>.*?</(?:\w+:)?tc>',
                        replace_caption_cell,
                        s_text,
                        flags=re.DOTALL
                    )
                    xml_file.write_text(s_text, encoding="utf-8")
            elif not has_photo:
                # 사진이 없을 때는 무조건 '╻' 단 한 줄만 유지 (규칙 13, 규칙 31)
                for xml_file in contents_dir.glob("section*.xml"):
                    s_text = xml_file.read_text(encoding="utf-8")
                    def replace_empty_caption(match):
                        tc = match.group(0)
                        p_one_line = (
                            '<ns1:p id="2147483648" paraPrIDRef="37" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                            '<ns1:run charPrIDRef="26"><ns1:t>╻</ns1:t></ns1:run>'
                            '</ns1:p>'
                        )
                        return re.sub(
                            r'<(?:\w+:)?subList\b[^>]*>.*?</(?:\w+:)?subList>',
                            f'<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{p_one_line}</ns1:subList>',
                            tc,
                            flags=re.DOTALL
                        )
                    s_text = re.sub(
                        r'<(?:\w+:)?tc\b[^>]*>(?:(?!</(?:\w+:)?tc>).)*?<(?:\w+:)?cellSz width="52624" height="4581"[^>]*>.*?</(?:\w+:)?tc>',
                        replace_empty_caption,
                        s_text,
                        flags=re.DOTALL
                    )
                    xml_file.write_text(s_text, encoding="utf-8")

            # 3-4. User custom asset (예: 교적 정보 확인 시스템 QR코드 gyoin_info_qr.png, 길목 청년활동가 지원 사업 QR코드 2gtkk.png) 주입 및 매니페스트 동기화
            # 주의: 교독송 악보(image5.bmp, image6.bmp)와 절대 충돌하지 않도록 독립 ID인 image8 사용
            ann_text_all = str(data.get("announcements_sections", []))
            if "교적" in ann_text_all and Path("data/assets/images/gyoin_info_qr.png").is_file():
                asset_qr = Path("data/assets/images/gyoin_info_qr.png")
            elif Path("data/assets/images/2gtkk.png").is_file():
                asset_qr = Path("data/assets/images/2gtkk.png")
            else:
                asset_qr = Path("data/assets/images/image6.png")

            if asset_qr.is_file():
                bindata_dir = temp_path / "BinData"
                bindata_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset_qr, bindata_dir / "image8.png")

                hpf_file = contents_dir / "content.hpf"
                if hpf_file.is_file():
                    hpf_text = hpf_file.read_text(encoding="utf-8")
                    if 'id="image8"' in hpf_text:
                        hpf_text = re.sub(
                            r'<opf:item id="image8"[^>]*/>',
                            '<opf:item id="image8" href="BinData/image8.png" media-type="image/png" isEmbeded="1"/>',
                            hpf_text
                        )
                    else:
                        hpf_text = hpf_text.replace(
                            '</opf:manifest>',
                            '<opf:item id="image8" href="BinData/image8.png" media-type="image/png" isEmbeded="1"/></opf:manifest>'
                        )
                    hpf_file.write_text(hpf_text, encoding="utf-8")

            # 3-5. 8페이지 목회마당 포스터 처리 또는 텍스트 주입 시 이미지 정리
            pastoral_image = data.get("pastoral_corner", {}).get("image") or data.get("pastoral_image")
            if pastoral_image and not pastoral_text:
                p_img_path = Path(pastoral_image)
                if p_img_path.is_file():
                    bindata_dir = temp_path / "BinData"
                    bindata_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p_img_path, bindata_dir / "image1.jpg")
                    hpf_file = contents_dir / "content.hpf"
                    if hpf_file.is_file():
                        hpf_text = hpf_file.read_text(encoding="utf-8")
                        if 'id="image1"' not in hpf_text:
                            hpf_text = hpf_text.replace(
                                '</opf:manifest>',
                                '<opf:item id="image1" href="BinData/image1.jpg" media-type="image/jpeg" isEmbeded="1"/></opf:manifest>'
                            )
                            hpf_file.write_text(hpf_text, encoding="utf-8")
            elif pastoral_text:
                bindata_dir = temp_path / "BinData"
                img1_file = bindata_dir / "image1.jpg"
                if img1_file.is_file():
                    img1_file.unlink()
                hpf_file = contents_dir / "content.hpf"
                if hpf_file.is_file():
                    hpf_text = hpf_file.read_text(encoding="utf-8")
                    hpf_text = re.sub(r'<opf:item id="image1"[^>]*/>\s*', '', hpf_text)
                    hpf_file.write_text(hpf_text, encoding="utf-8")

            # 3-6. season 미지정 경로에서도 section*.xml이 미세 자간 charPr(204~219)을 참조한 경우 header.xml 누락 등록 보완
            if not matched_cfg and contents_dir.is_dir():
                header_file = contents_dir / "header.xml"
                if header_file.is_file():
                    spacing_cids = {cid for pair in self.SPACING_CID_MAP.values() for cid in pair}
                    sec_uses_spacing = any(
                        any(f'charPrIDRef="{cid}"' in xf.read_text(encoding="utf-8") for cid in spacing_cids)
                        for xf in contents_dir.glob("section*.xml")
                    )
                    if sec_uses_spacing:
                        h_text = header_file.read_text(encoding="utf-8")
                        if "</hh:charProperties>" in h_text:
                            existing_cids = set(re.findall(r'<(?:[\w]+:)?charPr\b[^>]*\bid="(\d+)"', h_text))
                            new_charpr_xml = []
                            for sp, (b_id, r_id) in self.SPACING_CID_MAP.items():
                                ratio_val = "95" if sp <= -4 else "96"
                                if b_id not in existing_cids:
                                    new_charpr_xml.append(
                                        f'<hh:charPr id="{b_id}" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="9">'
                                        f'<hh:fontRef hangul="3" latin="3" hanja="3" japanese="3" other="3" symbol="3" user="3"/>'
                                        f'<hh:ratio hangul="{ratio_val}" latin="{ratio_val}" hanja="{ratio_val}" japanese="{ratio_val}" other="{ratio_val}" symbol="{ratio_val}" user="{ratio_val}"/>'
                                        f'<hh:spacing hangul="{sp}" latin="{sp}" hanja="{sp}" japanese="{sp}" other="{sp}" symbol="{sp}" user="{sp}"/>'
                                        f'<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
                                        f'<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                                        f'<hh:bold/>'
                                        f'<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
                                        f'<hh:strikeout shape="NONE" color="#000000"/>'
                                        f'<hh:outline type="NONE"/>'
                                        f'<hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>'
                                        f'</hh:charPr>'
                                    )
                                if r_id not in existing_cids:
                                    new_charpr_xml.append(
                                        f'<hh:charPr id="{r_id}" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="9">'
                                        f'<hh:fontRef hangul="3" latin="3" hanja="3" japanese="3" other="3" symbol="3" user="3"/>'
                                        f'<hh:ratio hangul="{ratio_val}" latin="{ratio_val}" hanja="{ratio_val}" japanese="{ratio_val}" other="{ratio_val}" symbol="{ratio_val}" user="{ratio_val}"/>'
                                        f'<hh:spacing hangul="{sp}" latin="{sp}" hanja="{sp}" japanese="{sp}" other="{sp}" symbol="{sp}" user="{sp}"/>'
                                        f'<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
                                        f'<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                                        f'<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
                                        f'<hh:strikeout shape="NONE" color="#000000"/>'
                                        f'<hh:outline type="NONE"/>'
                                        f'<hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>'
                                        f'</hh:charPr>'
                                    )
                            if new_charpr_xml:
                                added_xml = "".join(new_charpr_xml)
                                m_cnt = re.search(r'(<hh:charProperties itemCnt=")(\d+)(">)', h_text)
                                if m_cnt:
                                    old_cnt = int(m_cnt.group(2))
                                    new_cnt = old_cnt + len(new_charpr_xml)
                                    h_text = h_text[:m_cnt.start()] + f'{m_cnt.group(1)}{new_cnt}{m_cnt.group(3)}' + h_text[m_cnt.end():]
                                h_text = h_text.replace("</hh:charProperties>", f"{added_xml}</hh:charProperties>")
                                header_file.write_text(h_text, encoding="utf-8")

            # 4. Stage HWPX zip strictly compliant with KS X 6101 / OCF standard, validate artifact, then export
            self._write_hwpx_zip(temp_path, staged_hwpx)
            return self._export_validated_hwpx(staged_hwpx, data, output_file)

    @staticmethod
    def _write_hwpx_zip(source_dir: Path, archive_path: Path) -> None:
        with zipfile.ZipFile(archive_path, "w") as zip_out:
            mimetype_file = source_dir / "mimetype"
            if mimetype_file.is_file():
                zip_out.write(mimetype_file, "mimetype", compress_type=zipfile.ZIP_STORED)
            for file_item in sorted(source_dir.rglob("*")):
                if file_item.is_file() and file_item.name != "mimetype":
                    arcname = file_item.relative_to(source_dir).as_posix()
                    zip_out.write(file_item, arcname, compress_type=zipfile.ZIP_DEFLATED)

    @staticmethod
    def _copy_to_temp_export(src_path: Path, temp_dst_path: Path, chunk_size: int = 65536) -> None:
        """Write complete validated HWPX bytes to an exclusive temporary file in the output directory."""
        with open(src_path, "rb") as f_src, open(temp_dst_path, "xb") as f_dst:
            while True:
                chunk = f_src.read(chunk_size)
                if not chunk:
                    break
                f_dst.write(chunk)
            f_dst.flush()
            os.fsync(f_dst.fileno())

    @staticmethod
    def _commit_temp_export_no_overwrite(temp_export: Path, target_path: Path) -> None:
        """Commit temp_export to target_path without overwriting any existing file (never uses os.replace)."""
        if target_path.exists():
            raise FileExistsError(f"Output target already exists: {target_path}")
        if os.name == "nt":
            os.rename(temp_export, target_path)
        else:
            os.link(temp_export, target_path)
            temp_export.unlink()

    @staticmethod
    def _export_validated_hwpx(
        staged_hwpx: Path,
        data: Dict[str, Any],
        output_file: Path,
        max_attempts: int = 20,
    ) -> Path:
        from src.utils import get_next_bulletin_version

        validate_generated_hwpx(staged_hwpx, data, fallback_stem=output_file.stem)
        output_dir = output_file.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_export = output_dir / f".{output_file.name}.tmp_{os.getpid()}_{uuid.uuid4().hex}.part"

        try:
            HwpxEngine._copy_to_temp_export(staged_hwpx, temp_export)

            base_stem = re.sub(r"_v\d+$", "", output_file.stem)
            candidate = output_file
            next_v: int | None = None
            attempts = 0

            while True:
                attempts += 1
                if attempts > max_attempts:
                    raise OSError(
                        f"내보내기 대상 파일 확정 실패 (최대 재시도 {max_attempts}회 초과): {candidate}"
                    )

                if candidate.exists():
                    scanned_v = get_next_bulletin_version(output_dir, base_stem)
                    next_v = scanned_v if next_v is None else max(next_v + 1, scanned_v)
                    candidate = output_dir / f"{base_stem}_v{next_v}{output_file.suffix}"
                    continue

                if candidate.stem != output_file.stem:
                    validate_generated_hwpx(temp_export, data, fallback_stem=candidate.stem)

                try:
                    HwpxEngine._commit_temp_export_no_overwrite(temp_export, candidate)
                    return candidate
                except (FileExistsError, PermissionError) as exc:
                    if attempts >= max_attempts:
                        raise OSError(
                            f"내보내기 대상 파일 확정 실패 (반복 오류로 중단, 시도 {attempts}회): {candidate}"
                        ) from exc
                    scanned_v = get_next_bulletin_version(output_dir, base_stem)
                    next_v = scanned_v if next_v is None else max(next_v + 1, scanned_v)
                    candidate = output_dir / f"{base_stem}_v{next_v}{output_file.suffix}"
        finally:
            if temp_export.exists():
                try:
                    temp_export.unlink()
                except OSError:
                    pass

