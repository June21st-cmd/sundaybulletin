"""Parser and validator for weekly bulletin input data (YAML/JSON/Raw Text)."""
import json
from pathlib import Path
import re
from typing import Any, Dict
import yaml


def validate_bulletin_data(data: Dict[str, Any]) -> bool:
    """Validate structure of loaded bulletin data dictionary.
    
    Args:
        data: Parsed dictionary.
        
    Returns:
        True if valid.
        
    Raises:
        ValueError: If essential fields are missing.
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid bulletin data format: root must be a dictionary.")

    # Check metadata or date
    meta = data.get("metadata", {})
    if not meta and not data.get("date") and not data.get("date_korean"):
        raise ValueError("Bulletin data missing date/metadata information.")

    return True


def load_bulletin_data(file_path: Path | str) -> Dict[str, Any]:
    """Load and parse bulletin data from a YAML or JSON file.
    
    Args:
        file_path: Path to the input file.
        
    Returns:
        Dict containing structured bulletin data.
        
    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is unsupported or invalid.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    content = path.read_text(encoding="utf-8")
    
    if path.suffix.lower() in [".yaml", ".yml"]:
        data = yaml.safe_load(content)
    elif path.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}. Expected .yaml or .json")

    validate_bulletin_data(data)
    return data


def parse_raw_text_to_dict(raw_text: str) -> Dict[str, Any]:
    """Helper to parse unstructured raw memo text into bulletin data dictionary.
    
    Supports basic patterns like:
    설교: [제목] / [본문] / [설교자]
    날짜: [일자]
    광고:
    1. ...
    2. ...
    """
    data: Dict[str, Any] = {
        "metadata": {},
        "worship_1": {},
        "announcements": [],
        "prayer_requests": [],
    }

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    current_section = None

    for line in lines:
        if line.startswith("날짜:"):
            data["metadata"]["date_korean"] = line.replace("날짜:", "").strip()
        elif line.startswith("절기:"):
            data["metadata"]["season"] = line.replace("절기:", "").strip()
        elif line.startswith("설교:") or line.startswith("말씀:"):
            sermon_part = line.split(":", 1)[1].strip()
            parts = [p.strip() for p in sermon_part.split("/")]
            if len(parts) >= 1:
                data["worship_1"]["sermon_title"] = parts[0]
            if len(parts) >= 2:
                data["worship_1"]["scripture"] = parts[1]
            if len(parts) >= 3:
                data["worship_1"]["preacher"] = parts[2]
        elif line.startswith("광고:") or line.startswith("알림:"):
            current_section = "announcements"
        elif line.startswith("기도:") or line.startswith("기도나눔:"):
            current_section = "prayers"
        elif current_section == "announcements":
            # Match 1. Title - Content or 1. Title
            clean_item = re.sub(r"^\d+[\.\)]\s*", "", line)
            if " - " in clean_item:
                title, content = clean_item.split(" - ", 1)
                data["announcements"].append({"title": title.strip(), "content": content.strip()})
            else:
                data["announcements"].append({"title": clean_item.strip(), "content": ""})
        elif current_section == "prayers":
            data["prayer_requests"].append({"name": line, "content": ""})

    return data
