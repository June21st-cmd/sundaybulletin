"""HWPX template tag substitution and flattening engine."""
import html
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Dict, List
import zipfile


class HwpxEngine:
    """Production-grade engine for HWPX template XML tag substitution."""

    DEFAULT_LOGO_DIR = Path(r"C:\Users\june2\OneDrive\바탕 화면\주보인수인계\향린로고")

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

            flat_map["headline_left"] = str(meta.get("headline_left", ""))
            flat_map["헤드라인_좌"] = flat_map["headline_left"]
            
            flat_map["headline_right"] = str(meta.get("headline_right", ""))
            flat_map["헤드라인_우"] = flat_map["headline_right"]

        # 2. Worship order mappings
        worship = data.get("worship_1", data.get("worship", {}))
        if isinstance(worship, dict):
            flat_map["worship_call_scripture"] = str(worship.get("call_scripture", ""))
            flat_map["예배부름_성경"] = flat_map["worship_call_scripture"]

            flat_map["worship_opening_hymn"] = str(worship.get("opening_hymn", ""))
            flat_map["여는찬송"] = flat_map["worship_opening_hymn"]

            flat_map["choir_song_title"] = str(worship.get("choir_song_title", ""))
            flat_map["찬양곡명"] = flat_map["choir_song_title"]
            flat_map["choir_song_info"] = str(worship.get("choir_song_info", ""))
            flat_map["찬양정보"] = flat_map["choir_song_info"]
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

            flat_map["worship_gospel"] = str(worship.get("gospel", ""))
            flat_map["복음서읽기"] = flat_map["worship_gospel"]

            flat_map["worship_sermon_title"] = str(worship.get("sermon_title", ""))
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
        if isinstance(duties, dict):
            for w in ["w1", "w2", "w3"]:
                w_data = duties.get(w, {})
                flat_map[f"duty_{w}_date"] = str(w_data.get("date", ""))
                flat_map[f"duty_{w}_presider"] = str(w_data.get("presider", ""))
                flat_map[f"duty_{w}_pastoral_prayer"] = str(w_data.get("pastoral_prayer", ""))
                flat_map[f"duty_{w}_scripture_reader"] = str(w_data.get("scripture_reader", ""))
                flat_map[f"duty_{w}_preacher"] = str(w_data.get("preacher", ""))
                flat_map[f"duty_{w}_thanks_prayer"] = str(w_data.get("thanks_prayer", ""))

        # 4. Donations (감사헌금)
        donations = data.get("donations", {})
        if isinstance(donations, dict):
            flat_map["thanksgiving_donors"] = str(donations.get("thanksgiving", ""))
            flat_map["감사헌금"] = flat_map["thanksgiving_donors"]

        # 5. Prayer requests (기도나눔)
        prayers = data.get("prayer_requests", {})
        if isinstance(prayers, dict):
            flat_map["healing_prayer_1"] = str(prayers.get("healing_1", ""))
            flat_map["healing_prayer_2"] = str(prayers.get("healing_2", ""))
            flat_map["healing_prayer_3"] = str(prayers.get("healing_3", ""))
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

    def generate(self, data: Dict[str, Any], output_path: Path | str) -> Path:
        """Generate a new HWPX file by substituting text placeholders in XML.
        
        Args:
            data: Structured or flat bulletin data dict.
            output_path: Target destination path for generated HWPX.
            
        Returns:
            Path to the generated HWPX file.
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        flat_map = self.flatten_data(data)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # 1. Unpack HWPX zip
            with zipfile.ZipFile(self.template_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)

            # 2. Process XML section files
            contents_dir = temp_path / "Contents"
            if contents_dir.is_dir():
                for xml_file in contents_dir.glob("section*.xml"):
                    xml_text = xml_file.read_text(encoding="utf-8")

                    # Replace defined keys
                    for key, val in flat_map.items():
                        escaped_val = html.escape(val)
                        xml_text = xml_text.replace(f"{{{{{key}}}}}", escaped_val)
                        xml_text = xml_text.replace(f"{{{{ {key} }}}}", escaped_val)

                    # Dynamic liturgical hymn substitution (주기도송 vs 신앙고백송)
                    confession = flat_map.get("confession_or_lord_prayer", "")
                    if not confession:
                        worship_dict = data.get("worship_1", data.get("worship", {}))
                        if isinstance(worship_dict, dict):
                            confession = str(worship_dict.get("confession_or_lord_prayer", ""))
                    
                    # "주기도문송" 표기 정규화 -> 반드시 "주기도송"으로 통일
                    confession = confession.replace("주기도문송", "주기도송").strip()

                    # 일자 기반 월(month) 추출 (미지정 시 기본 찬송 번호 보완용)
                    date_str = str(flat_map.get("date") or flat_map.get("date_korean") or "")
                    month = None
                    m_match = re.search(r"[-./](\d{1,2})[-./]|\b(\d{1,2})월", date_str)
                    if m_match:
                        month = int(m_match.group(1) or m_match.group(2))

                    if "주기도" in confession:
                        xml_text = xml_text.replace("신 앙 고 백 송", "주 기 도 송")
                        if "장" in confession:
                            song_target = confession
                        elif month in [3, 7, 11]:
                            song_target = "주기도송(2) 246장"
                        else:
                            song_target = "주기도송(1) 245장"
                        xml_text = xml_text.replace("국악찬송 254장", song_target)
                    elif "신앙고백" in confession:
                        if confession and confession != "국악찬송 254장":
                            xml_text = xml_text.replace("국악찬송 254장", confession)

                    # Dynamic lifestyle pledge substitution (향린교인 생활실천 다짐 10개 조항 순환)
                    pledge_info = data.get("lifestyle_pledge", {})
                    if isinstance(pledge_info, dict) and pledge_info.get("text"):
                        p_num = pledge_info.get("number", "")
                        p_text = pledge_info.get("text", "")
                        pledge_pattern = r'(charPrIDRef="178"[^>]*><(?:\w+:)?t>)\d+\.\s*(</(?:\w+:)?t></(?:\w+:)?run>).*?(</(?:\w+:)?p>)'
                        repl = rf'\g<1>{p_num}. \g<2><ns1:run charPrIDRef="192"><ns1:t>{html.escape(p_text)}</ns1:t></ns1:run>\g<3>'
                        xml_text = re.sub(pledge_pattern, repl, xml_text, flags=re.DOTALL)

                    # Auto-clean any remaining unreplaced slots
                    xml_text = re.sub(r"\{\{[^}]+\}\}", "", xml_text)

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
                
                # 3-1. Replace color in header.xml
                header_file = contents_dir / "header.xml"
                if header_file.is_file():
                    h_text = header_file.read_text(encoding="utf-8")
                    # Replace red template color #FF0000 with target season color
                    h_text = re.sub(r'textColor="#FF0000"', f'textColor="{target_color}"', h_text, flags=re.IGNORECASE)
                    header_file.write_text(h_text, encoding="utf-8")

                # 3-2. Replace logos in BinData and preserve exact aspect ratio & rendering matrix
                bindata_dir = temp_path / "BinData"
                if bindata_dir.is_dir() and self.logo_dir.is_dir():
                    sym_file = self.logo_dir / matched_cfg["symbol_logo"]
                    txt_file = self.logo_dir / matched_cfg["text_logo"]
                    
                    logo_specs = {}
                    if sym_file.is_file():
                        shutil.copy2(sym_file, bindata_dir / "image3.png")
                        try:
                            from PIL import Image
                            with Image.open(sym_file) as img:
                                w, h = img.size
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
                        except Exception:
                            pass

                    if txt_file.is_file():
                        shutil.copy2(txt_file, bindata_dir / "image4.png")
                        try:
                            from PIL import Image
                            with Image.open(txt_file) as img:
                                w, h = img.size
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
                        except Exception:
                            pass

                    # Update exact dimensions, matrix, and clip in section*.xml to ensure 100% distortion-free rendering
                    if logo_specs:
                        for xml_file in contents_dir.glob("section*.xml"):
                            s_text = xml_file.read_text(encoding="utf-8")
                            for img_ref, spec in logo_specs.items():
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
                shutil.copy2(Path(cover_photo_path), bindata_dir / "image2.png")

            # 4. Repack HWPX zip strictly compliant with KS X 6101 / OCF standard
            try:
                with zipfile.ZipFile(output_file, 'w') as zip_out:
                    # 1) mimetype MUST be the very first entry and stored uncompressed (ZIP_STORED)
                    mimetype_file = temp_path / "mimetype"
                    if mimetype_file.is_file():
                        zip_out.write(mimetype_file, "mimetype", compress_type=zipfile.ZIP_STORED)
                    
                    # 2) Write other entries with standard compression (ZIP_DEFLATED)
                    for file_item in sorted(temp_path.rglob("*")):
                        if file_item.is_file() and file_item.name != "mimetype":
                            arcname = file_item.relative_to(temp_path).as_posix()
                            zip_out.write(file_item, arcname, compress_type=zipfile.ZIP_DEFLATED)
            except PermissionError:
                alt_output = output_file.with_name(f"{output_file.stem}_생성본{output_file.suffix}")
                with zipfile.ZipFile(alt_output, 'w') as zip_out:
                    mimetype_file = temp_path / "mimetype"
                    if mimetype_file.is_file():
                        zip_out.write(mimetype_file, "mimetype", compress_type=zipfile.ZIP_STORED)
                    for file_item in sorted(temp_path.rglob("*")):
                        if file_item.is_file() and file_item.name != "mimetype":
                            arcname = file_item.relative_to(temp_path).as_posix()
                            zip_out.write(file_item, arcname, compress_type=zipfile.ZIP_DEFLATED)
                return alt_output

        return output_file
