"""Unit tests for HWPX template engine."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.hwpx_engine import HwpxEngine


class TestHwpxEngine(unittest.TestCase):
    def test_hwpx_substitution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create a mock HWPX (zip containing Contents/section0.xml)
            mock_hwpx = temp_path / "mock.hwpx"
            contents_dir = temp_path / "src_mock" / "Contents"
            contents_dir.mkdir(parents=True, exist_ok=True)
            xml_file = contents_dir / "section0.xml"
            xml_file.write_text("<p>{{sermon_title}}</p>", encoding="utf-8")

            with zipfile.ZipFile(mock_hwpx, "w") as z:
                z.write(xml_file, "Contents/section0.xml")

            engine = HwpxEngine(mock_hwpx)
            out_hwpx = temp_path / "out.hwpx"
            result = engine.generate({"sermon_title": "선한 이웃"}, out_hwpx)
            
            self.assertTrue(result.is_file())
            
            # Verify output content
            with zipfile.ZipFile(result, "r") as z_out:
                extracted_xml = z_out.read("Contents/section0.xml").decode("utf-8")
                self.assertIn("선한 이웃", extracted_xml)
                self.assertNotIn("{{sermon_title}}", extracted_xml)


if __name__ == "__main__":
    unittest.main()
