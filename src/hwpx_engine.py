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
            motto_parts = motto.split("\n") if "\n" in motto else [motto, ""]
            flat_map["motto_line1"] = str(meta.get("motto_line1", motto_parts[0]))
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

            flat_map["worship_scripture"] = str(worship.get("scripture", ""))
            flat_map["성서읽기"] = flat_map["worship_scripture"]
            flat_map["성경본문"] = flat_map["worship_scripture"]

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

            flat_map["worship_offering_hymn"] = str(worship.get("offering_hymn", ""))
            flat_map["봉헌찬송"] = flat_map["worship_offering_hymn"]

            flat_map["worship_benediction"] = str(worship.get("benediction", ""))
            flat_map["축복기도"] = flat_map["worship_benediction"]

        # 3. Announcements slot mapping (up to 15 slots)
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

        # 4. Prayer requests slot mapping (up to 10 slots)
        prayers = data.get("prayer_requests", [])
        if isinstance(prayers, list):
            for i in range(10):
                slot_idx = i + 1
                if i < len(prayers):
                    item = prayers[i]
                    if isinstance(item, dict):
                        name = str(item.get("name", ""))
                        content = str(item.get("content", ""))
                    else:
                        name = str(item)
                        content = ""
                else:
                    name = ""
                    content = ""

                flat_map[f"prayer{slot_idx}_name"] = name
                flat_map[f"기도나눔{slot_idx}_이름"] = name
                flat_map[f"prayer{slot_idx}_content"] = content
                flat_map[f"기도나눔{slot_idx}_내용"] = content

        # 5. Direct top-level key-values
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
                        # Replace {{key}}
                        xml_text = xml_text.replace(f"{{{{{key}}}}}", escaped_val)
                        # Replace {{ key }} with spaces
                        xml_text = xml_text.replace(f"{{{{ {key} }}}}", escaped_val)

                    # Auto-clean any remaining unreplaced ad/prayer slots
                    xml_text = re.sub(r"\{\{(ad\d+_[a-z]+|광고\d+_[가-힣]+|prayer\d+_[a-z]+|기도나눔\d+_[가-힣]+)\}\}", "", xml_text)

                    xml_file.write_text(xml_text, encoding="utf-8")

            # 3. Repack HWPX zip
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                for file_item in temp_path.rglob("*"):
                    if file_item.is_file():
                        arcname = file_item.relative_to(temp_path)
                        zip_out.write(file_item, arcname)

        return output_file
