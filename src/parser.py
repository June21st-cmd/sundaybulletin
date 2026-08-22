"""Parser for weekly bulletin input data (YAML/JSON)."""
import json
from pathlib import Path
from typing import Any, Dict
import yaml


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

    if not isinstance(data, dict):
        raise ValueError("Invalid bulletin data format: expected root dictionary.")

    return data
