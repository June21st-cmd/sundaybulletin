"""HWPX template tag substitution and flattening engine."""
import html
from pathlib import Path
import re
import tempfile
from typing import Any, Dict, List
import zipfile


class HwpxEngine:
    """Production-grade engine for HWPX template XML tag substitution."""

    def __init__(self, template_path: Path | str):
        self.template_path = Path(template_path)
        if not self.template_path.is_file():
            raise FileNotFoundError(f"HWPX template not found: {self.template_path}")

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
                    if "주기도" in confession:
                        xml_text = xml_text.replace("신 앙 고 백 송", "주 기 도 송")
                        song_target = confession if "장" in confession else "주기도송 245장"
                        xml_text = xml_text.replace("국악찬송 254장", song_target)

                    # Auto-clean any remaining unreplaced slots
                    xml_text = re.sub(r"\{\{[^}]+\}\}", "", xml_text)

                    xml_file.write_text(xml_text, encoding="utf-8")

            # 3. Repack HWPX zip
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                for file_item in temp_path.rglob("*"):
                    if file_item.is_file():
                        arcname = file_item.relative_to(temp_path)
                        zip_out.write(file_item, arcname)

        return output_file
