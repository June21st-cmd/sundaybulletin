"""HWPX template tag substitution engine."""
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict
import zipfile


class HwpxEngine:
    """Engine for manipulating HWPX XML documents."""

    def __init__(self, template_path: Path | str):
        self.template_path = Path(template_path)
        if not self.template_path.is_file():
            raise FileNotFoundError(f"HWPX template not found: {self.template_path}")

    def generate(self, data: Dict[str, Any], output_path: Path | str) -> Path:
        """Generate a new HWPX file by substituting text placeholders in XML.
        
        Args:
            data: Key-value pairs to substitute.
            output_path: Target destination path for generated HWPX.
            
        Returns:
            Path to the generated HWPX file.
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extract HWPX zip
            with zipfile.ZipFile(self.template_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)

            # Look for XML section files (Contents/section0.xml, etc.)
            contents_dir = temp_path / "Contents"
            if contents_dir.is_dir():
                for xml_file in contents_dir.glob("section*.xml"):
                    text = xml_file.read_text(encoding="utf-8")
                    for key, val in data.items():
                        placeholder = f"{{{{{key}}}}}"
                        text = text.replace(placeholder, str(val))
                    xml_file.write_text(text, encoding="utf-8")

            # Repack into target HWPX
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                for file_item in temp_path.rglob("*"):
                    if file_item.is_file():
                        arcname = file_item.relative_to(temp_path)
                        zip_out.write(file_item, arcname)

        return output_file
