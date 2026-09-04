"""Unit tests for HWPX template engine."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.hwpx_engine import HwpxEngine
from src.parser import load_bulletin_data


class TestHwpxEngine(unittest.TestCase):
    def test_hwpx_flattening(self):
        data = {
            "metadata": {
                "foundation_year": "73",
                "season": "성령강림주일",
                "headline_left": "초청 하늘뜻펴기",
            },
            "worship_1": {
                "sermon_title": "새 하늘과 새 땅",
            },
            "announcements": [
                {"title": "광고1번", "content": "내용1"},
                {"title": "광고2번", "content": "내용2"},
            ],
        }
        flat = HwpxEngine.flatten_data(data)
        self.assertEqual(flat["foundation_year"], "73")
        self.assertEqual(flat["창립주년"], "73")
        self.assertEqual(flat["설교제목"], "새 하늘과 새 땅")
        self.assertEqual(flat["광고1_제목"], "광고1번")
        self.assertEqual(flat["ad1_title"], "광고1번")
        self.assertEqual(flat["ad3_title"], "")

    def test_mock_substitution_and_autoclean(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            mock_hwpx = temp_path / "mock.hwpx"
            contents_dir = temp_path / "src_mock" / "Contents"
            contents_dir.mkdir(parents=True, exist_ok=True)
            xml_file = contents_dir / "section0.xml"
            xml_file.write_text("<p>{{설교제목}}</p><p>{{ad1_title}}</p><p>{{ad5_title}}</p>", encoding="utf-8")

            with zipfile.ZipFile(mock_hwpx, "w") as z:
                z.write(xml_file, "Contents/section0.xml")

            engine = HwpxEngine(mock_hwpx)
            out_hwpx = temp_path / "out.hwpx"
            data = {
                "worship_1": {"sermon_title": "희망의 노래"},
                "announcements": [{"title": "첫번째 광고"}],
            }
            result = engine.generate(data, out_hwpx)
            
            with zipfile.ZipFile(result, "r") as z_out:
                extracted_xml = z_out.read("Contents/section0.xml").decode("utf-8")
                self.assertIn("희망의 노래", extracted_xml)
                self.assertIn("첫번째 광고", extracted_xml)
                self.assertNotIn("{{ad5_title}}", extracted_xml)

    def test_liturgical_hymn_substitution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            mock_hwpx = temp_path / "mock.hwpx"
            contents_dir = temp_path / "src_mock" / "Contents"
            contents_dir.mkdir(parents=True, exist_ok=True)
            xml_file = contents_dir / "section0.xml"
            xml_template = "<p>신 앙 고 백 송</p><p>국악찬송 254장</p>"

            # 1. 1,5,9월: 주기도문송(1) 245장 입력 시 -> 주기도송(1) 245장으로 정규화 및 치환
            xml_file.write_text(xml_template, encoding="utf-8")
            with zipfile.ZipFile(mock_hwpx, "w") as z:
                z.write(xml_file, "Contents/section0.xml")

            engine = HwpxEngine(mock_hwpx)
            out_hwpx1 = temp_path / "out1.hwpx"
            data1 = {
                "metadata": {"date": "2026-09-13"},
                "worship_1": {"confession_or_lord_prayer": "주기도문송(1) 245장"},
            }
            engine.generate(data1, out_hwpx1)
            with zipfile.ZipFile(out_hwpx1, "r") as z_out:
                res1 = z_out.read("Contents/section0.xml").decode("utf-8")
                self.assertIn("주 기 도 송", res1)
                self.assertIn("주기도송(1) 245장", res1)
                self.assertNotIn("주기도문송", res1)
                self.assertNotIn("신 앙 고 백 송", res1)

            # 2. 3,7,11월: 3월에 "주기도송"만 지정 시 -> 주기도송(2) 246장 기본값 보완
            out_hwpx2 = temp_path / "out2.hwpx"
            data2 = {
                "metadata": {"date": "2026-03-08"},
                "worship_1": {"confession_or_lord_prayer": "주기도송"},
            }
            engine.generate(data2, out_hwpx2)
            with zipfile.ZipFile(out_hwpx2, "r") as z_out:
                res2 = z_out.read("Contents/section0.xml").decode("utf-8")
                self.assertIn("주 기 도 송", res2)
                self.assertIn("주기도송(2) 246장", res2)

    def test_real_master_template_generation(self):
        template_path = Path("templates/hwpx/template.hwpx")
        sample_data_path = Path("data/samples/sample_hyanglin_20260816.yaml")
        
        if template_path.is_file() and sample_data_path.is_file():
            data = load_bulletin_data(sample_data_path)
            engine = HwpxEngine(template_path)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                out_path = Path(temp_dir) / "[주보] 20260816.hwpx"
                result = engine.generate(data, out_path)
                self.assertTrue(result.is_file())
                self.assertGreater(result.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
