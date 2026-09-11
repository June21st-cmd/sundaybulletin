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
        ("심방", -11),
        ("성서배움마당", -7),
        ("향린국악학교 수강생", -3),  # 서도민요반 줄바꿈에 맞춰 시원하게 -3%
        ("우리가락 얼쑤", -5),
        ("안병무 박사 30주기 연극", -4),
        ("기후정의행진 피켓", -3),  # 둘째 줄 '시'가 윗줄로 올라가도록 1줄 완성
        ("사진으로 보는 향린 역사", -2),  # 둘째 줄 '시'가 윗줄로 올라가도록 1줄 완성
        ("이번주 성서일과", -1),
    ]

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

            choir_title = str(worship.get("choir_song_title", "")).strip()
            choir_info = str(worship.get("choir_song_info", "")).strip()
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

                    # 1) 예배위원 3개 행(w1, w2, w3) 정규화: 템플릿의 누락/병합된 행을 6개 열(날짜, 인도, 목회기도, 성서읽기, 하늘뜻펴기, 감사기도)로 먼저 복구
                    def build_duty_row_template(prefix: str, r_idx: int) -> str:
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

                    # 미가서 본문 단일 문단 최적화 (불필요한 빈 문단 없이 4줄로 알맞게 수용)
                    if not flat_map.get("responsive_scripture_2") and not flat_map.get("responsive_scripture_3"):
                        xml_text = re.sub(
                            r'<(?:\w+:)?p\b[^>]*>\s*<(?:\w+:)?run[^>]*><(?:\w+:)?t>\{\{responsive_scripture_2\}\}</(?:\w+:)?t></(?:\w+:)?run>.*?</(?:\w+:)?p>',
                            '',
                            xml_text
                        )
                        xml_text = re.sub(
                            r'<(?:\w+:)?p\b[^>]*>\s*<(?:\w+:)?run[^>]*><(?:\w+:)?t>\{\{responsive_scripture_3\}\}</(?:\w+:)?t></(?:\w+:)?run>.*?</(?:\w+:)?p>',
                            '',
                            xml_text
                        )

                    # 건강회복 명단 2행 분리 복원 (1문단 11명, 2문단 11명으로 각각 1줄씩 깔끔 배치)
                    healing_1 = flat_map.get("healing_prayer_1", "")
                    healing_2 = flat_map.get("healing_prayer_2", "")
                    if healing_1 and healing_2:
                        clean_healing_p1 = f'<ns1:p id="2147483648" paraPrIDRef="21" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="160"><ns1:t> {html.escape(healing_1)}</ns1:t></ns1:run></ns1:p>'
                        clean_healing_p2 = f'<ns1:p id="0" paraPrIDRef="21" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="160"><ns1:t> {html.escape(healing_2)}</ns1:t></ns1:run></ns1:p>'
                        healing_block_pat = r'<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\{\{healing_prayer_1\}\}[\s\S]*?</(?:\w+:)?p>\s*<(?:\w+:)?p\b[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\{\{healing_prayer_3\}\}[\s\S]*?</(?:\w+:)?p>'
                        if re.search(healing_block_pat, xml_text):
                            xml_text = re.sub(healing_block_pat, f"{clean_healing_p1}\n{clean_healing_p2}", xml_text)

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

                    if hymn_num in ["245", "246"] or "주기도" in confession:
                        xml_text = xml_text.replace("신 앙 고 백 송", "주 기 도 송")

                    hymn_right_cell = f"국악찬송 {hymn_num}장"
                    xml_text = re.sub(r"국악찬송\s*254장", hymn_right_cell, xml_text)

                    # Dynamic lifestyle pledge substitution (향린교인 생활실천 다짐 10개 조항 순환)
                    pledge_info = data.get("lifestyle_pledge", {})
                    if isinstance(pledge_info, dict) and pledge_info.get("text"):
                        p_num = pledge_info.get("number", "")
                        p_text = pledge_info.get("text", "")
                        pledge_pattern = r'(charPrIDRef="178"[^>]*><(?:\w+:)?t>)\d+\.\s*(</(?:\w+:)?t></(?:\w+:)?run>).*?(</(?:\w+:)?p>)'
                        repl = rf'\g<1>{p_num}. \g<2><ns1:run charPrIDRef="192"><ns1:t>{html.escape(p_text)}</ns1:t></ns1:run>\g<3>'
                        xml_text = re.sub(pledge_pattern, repl, xml_text, flags=re.DOTALL)

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

                        if s1_1: xml_text = xml_text.replace('주님이여 우리들을 -', s1_1)
                        if s1_2: xml_text = xml_text.replace('불쌍하게 여기시고', s1_2)
                        if s1_3: xml_text = xml_text.replace('주의얼굴 비추시어', s1_3.rstrip('.'))

                        if s2_1: xml_text = xml_text.replace('그리하여 온세상이 -', s2_1)
                        if s2_2: xml_text = xml_text.replace('주님의뜻 알게하고 ', s2_2)
                        if s2_3: xml_text = xml_text.replace('온나라가 주님구원', s2_3.rstrip('.'))

                        if s3_1: xml_text = xml_text.replace('주님이여 민족들이 -', s3_1)
                        if s3_2: xml_text = xml_text.replace('찬양하게 하옵소서 ', s3_2)
                        if s3_3: xml_text = xml_text.replace('모든민족 주님에게', s3_3.rstrip('.'))

                        if s1_end: xml_text = xml_text.replace('복을내려 주옵소서', s1_end.rstrip('.'))
                        if s2_end: xml_text = xml_text.replace('알게하여 주옵소서', s2_end.rstrip('.'))
                        xml_text = xml_text.replace('>찬 양하게<', '>않 게하여<')

                        # 교독송 마지막 마디 가사: 주(음표1), 옵(음표2), 소(음표3), 서(음표4, 이음줄 시작), -(음표5), -(음표6) 정밀 정렬
                        col5_new = (
                            '<ns1:run charPrIDRef="86"><ns1:t>주</ns1:t></ns1:run>'
                            '<ns1:run charPrIDRef="86"><ns1:t> 옵소</ns1:t></ns1:run>'
                            '<ns1:run charPrIDRef="87"><ns1:t> 서</ns1:t></ns1:run>'
                            '<ns1:run charPrIDRef="87"><ns1:t>  -  -</ns1:t></ns1:run>'
                            '<ns1:run charPrIDRef="90" />'
                        )
                        pattern_col5 = r'<(?:\w+:)?run charPrIDRef="86"><(?:\w+:)?t>하</(?:\w+:)?t></(?:\w+:)?run>[\s\S]*?<(?:\w+:)?run charPrIDRef="87"><(?:\w+:)?t>-   -</(?:\w+:)?t></(?:\w+:)?run>(?:<(?:\w+:)?run charPrIDRef="90"\s*/>)?'
                        xml_text = re.sub(pattern_col5, col5_new, xml_text)

                        xml_text = xml_text.replace(
                            '주님이여 우리들을 -불쌍하게 여기시고주의얼굴 비추시어.그리하여 온세상이 -주님의뜻 알게하고 온나라가 주님구원. 주님이여 민족들이 -찬양하게 하옵소서 모든민족 주님에게.',
                            f'{s1_1}{s1_2}{s1_3}{s2_1}{s2_2}{s2_3} {s3_1}{s3_2}{s3_3}'
                        )
                        xml_text = xml_text.replace(
                            '복을내려 주옵소서.찬 양하게  -   -  -하 옵소서 -   -알게하여 주옵소서.',
                            f'{s1_end}않 게하여  -   -  -주 옵소 서  -  -{s2_end}'
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
                        f'<ns1:run charPrIDRef="119"><ns1:t> ╻방송실</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(av_txt)})</ns1:t></ns1:run>'
                        f'</ns1:p>'
                    )
                    clean_service_p2 = (
                        f'<ns1:p id="2147483648" paraPrIDRef="74" styleIDRef="33" pageBreak="0" columnBreak="0" merged="0">'
                        f'<ns1:run charPrIDRef="119"><ns1:t>헌금계수</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(finance_txt)})</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="119"><ns1:t> ╻주차</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(parking_txt)})</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="119"><ns1:t> ╻공동식사</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="122"><ns1:t>({html.escape(meal_txt)})</ns1:t></ns1:run>'
                        f'<ns1:run charPrIDRef="119"><ns1:t> ╻분리배출</ns1:t></ns1:run>'
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
                                        # 길목 청년활동가 지원 사업 또는 사용자 지정 이미지 항목 처리
                                        has_qr = ("청년활동가" in i_title) or (isinstance(item, dict) and item.get("image"))
                                        qr_pic_xml = ""
                                        if has_qr:
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

                                        # 신도회 월례회 항목 직후 신도회 장소 안내 표(박스) 자동 삽입
                                        if i_title == "신도회 월례회":
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

                                p_blank = '<ns1:p id="0" paraPrIDRef="95" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><ns1:run charPrIDRef="125" /></ns1:p>'
                                p_list.append(p_blank)

                            return "\n".join(p_list)

                        new_ann_xml = generate_announcements_xml(ann_sections)
                        ann_pat = r'<(?:\w+:)?p [^>]*paraPrIDRef="94"[^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?1\.\s*오늘\s*일정\s*안내[\s\S]*?(?=<(?:\w+:)?p [^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?\[온라인헌금\s*안내\])'
                        if re.search(ann_pat, xml_text):
                            xml_text = re.sub(ann_pat, new_ann_xml + "\n", xml_text, count=1)

                    # 교회 탄소중립 최신 수치 갱신 (8월 데이터)
                    xml_text = xml_text.replace("7월전기 ", "8월전기 ")
                    xml_text = xml_text.replace("5.86MWh", "6.89MWh")
                    xml_text = xml_text.replace("전년5.91MWh", "전년6.90MWh")
                    xml_text = xml_text.replace("1.08MWh", "1.31MWh")
                    xml_text = xml_text.replace("전년1.26MWh", "전년1.29MWh")

                    # 5. 등록 새교우 (new_members) 치환
                    new_members = data.get("new_members", [])
                    if new_members:
                        p_list = []
                        for i, line_str in enumerate(new_members):
                            pid = "2147483648" if i == 0 else "0"
                            p_list.append(
                                f'<ns1:p id="{pid}" paraPrIDRef="96" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                                f'<ns1:run charPrIDRef="21"><ns1:t> {html.escape(line_str.strip())}</ns1:t></ns1:run>'
                                f'</ns1:p>'
                            )
                        new_members_xml = "\n".join(p_list)
                        nm_pat = r'(<(?:\w+:)?run [^>]*charPrIDRef="66"[^>]*><(?:\w+:)?t>▯등록 새교우 \(2026\)</(?:\w+:)?t></(?:\w+:)?run>[\s\S]*?</(?:\w+:)?p>)(?:(?!<(?:\w+:)?p [^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?<(?:\w+:)?t>▯건강회복)[\s\S])*?(?=<(?:\w+:)?p [^>]*>(?:(?!</(?:\w+:)?p>)[\s\S])*?<(?:\w+:)?run [^>]*charPrIDRef="(?:160|166)"[^>]*>)'
                        if re.search(nm_pat, xml_text):
                            xml_text = re.sub(nm_pat, r'\g<1>' + '\n' + new_members_xml, xml_text, count=1)

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

                    # 함께 읽는 말씀 본문이 4줄로 알맞게 수용되도록 charPr id="173" 장평/자간 최적화
                    # (ratio 77 -> 75, spacing -10 -> -12)
                    h_text = re.sub(
                        r'(<hh:charPr id="173"[^>]*>\s*<hh:fontRef[^>]*/>\s*<hh:ratio )[^>]+(/>\s*<hh:spacing )[^>]+(/>)',
                        r'\g<1>hangul="75" latin="75" hanja="75" japanese="75" other="75" symbol="75" user="75"\g<2>hangul="-12" latin="-12" hanja="-12" japanese="-12" other="-12" symbol="-12" user="-12"\g<3>',
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

                    # 미적 조판용 미세 자간 charPr 등록 (-1% ~ -11%)
                    new_charpr_xml = []
                    for sp, (b_id, r_id) in self.SPACING_CID_MAP.items():
                        # Bold
                        new_charpr_xml.append(
                            f'<hh:charPr id="{b_id}" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="9">'
                            f'<hh:fontRef hangul="3" latin="3" hanja="3" japanese="3" other="3" symbol="3" user="3"/>'
                            f'<hh:ratio hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"/>'
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
                        # Regular
                        new_charpr_xml.append(
                            f'<hh:charPr id="{r_id}" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="9">'
                            f'<hh:fontRef hangul="3" latin="3" hanja="3" japanese="3" other="3" symbol="3" user="3"/>'
                            f'<hh:ratio hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"/>'
                            f'<hh:spacing hangul="{sp}" latin="{sp}" hanja="{sp}" japanese="{sp}" other="{sp}" symbol="{sp}" user="{sp}"/>'
                            f'<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
                            f'<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                            f'<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
                            f'<hh:strikeout shape="NONE" color="#000000"/>'
                            f'<hh:outline type="NONE"/>'
                            f'<hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>'
                            f'</hh:charPr>'
                        )
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
            if hl_left and hl_right:
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
            elif not cover_photo_path or not Path(cover_photo_path).is_file():
                # 사진이 없을 때는 '╻' 단 한 줄만 유지 (규칙 13)
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

            # 3-4. User custom asset (예: 길목 청년활동가 지원 사업 QR코드 2gtkk.png) 주입 및 매니페스트 동기화
            # 주의: 교독송 악보(image5.bmp, image6.bmp)와 절대 충돌하지 않도록 독립 ID인 image8 사용
            asset_qr = Path("data/assets/images/2gtkk.png")
            if not asset_qr.is_file():
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

            # 3-5. 8페이지 목회마당 포스터 제거 시 BinData/image1.jpg 및 content.hpf 정리
            if pastoral_text:
                bindata_dir = temp_path / "BinData"
                img1_file = bindata_dir / "image1.jpg"
                if img1_file.is_file():
                    img1_file.unlink()
                hpf_file = contents_dir / "content.hpf"
                if hpf_file.is_file():
                    hpf_text = hpf_file.read_text(encoding="utf-8")
                    hpf_text = re.sub(r'<opf:item id="image1"[^>]*/>\s*', '', hpf_text)
                    hpf_file.write_text(hpf_text, encoding="utf-8")

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
                from src.utils import get_next_bulletin_version
                base_stem = re.sub(r"_v\d+$", "", output_file.stem)
                next_v = get_next_bulletin_version(output_file.parent, base_stem)
                alt_output = output_file.parent / f"{base_stem}_v{next_v}{output_file.suffix}"
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

