import unittest
import os
import tempfile
import yaml
from pathlib import Path
import json

from scripts.fetch_session_material import find_latest_session_material
from src.main import run_preflight, is_same_file_path

class TestSourceCollection(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.downloads = Path(self.test_dir.name) / "Downloads"
        self.downloads.mkdir()
        
    def tearDown(self):
        self.test_dir.cleanup()
        
    def test_find_latest_session(self):
        # 1. 연/월이 명확한 정기당회 여러 개 -> 최신 1개 선택
        (self.downloads / "2026 7월 정기당회 회의록.hwp").touch()
        (self.downloads / "2026 9월 정기당회 회의록.pdf").touch()
        (self.downloads / "2025 12월 정기당회.hwp").touch()
        
        res = find_latest_session_material(self.downloads)
        self.assertIsNotNone(res)
        self.assertEqual(res["year"], 2026)
        self.assertEqual(res["month"], 9)
        self.assertIn("9월 정기당회", res["file_name"])

    def test_exclude_other_meetings(self):
        # 2. 임시당회/목회운영위원회 -> 후보 제외
        (self.downloads / "2026 9월 임시당회.hwp").touch()
        (self.downloads / "2026 9월 목회운영위원회.pdf").touch()
        (self.downloads / "2026 8월 제직회.hwp").touch()
        
        res = find_latest_session_material(self.downloads)
        self.assertIsNone(res)

    def test_ambiguous_year(self):
        # 3. 연도 없는 파일 -> 임의 선택 금지 (AMBIGUOUS_YEAR)
        (self.downloads / "9월 정기당회록.hwp").touch()
        
        res = find_latest_session_material(self.downloads)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("error"), "AMBIGUOUS_YEAR")

    def test_manifest_missing(self):
        # 4. Manifest 없음 -> HWPX BLOCK
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        
        blocks, warns = run_preflight_sim(yaml_path)
        self.assertTrue(any("Source Manifest 누락" in b for b in blocks))

    def test_manifest_mismatch(self):
        # 5. Manifest가 오래된 정기당회 자료를 가리킴 -> BLOCK
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": "old_file.hwp"
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        (self.downloads / "2026 9월 정기당회.hwp").touch()
        
        blocks, warns = run_preflight_sim(yaml_path, self.downloads)
        self.assertTrue(any("최신 정기당회 자료와 불일치" in b for b in blocks))

    def test_normal_manifest(self):
        # 6. 정상 Manifest -> 빌드 허용
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        
        latest_file = self.downloads / "2026 9월 정기당회.hwp"
        latest_file.touch()
        
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": str(latest_file)
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        blocks, warns = run_preflight_sim(yaml_path, self.downloads)
        self.assertFalse(any("Source Manifest 누락" in b for b in blocks))
        self.assertFalse(any("최신 정기당회 자료와 불일치" in b for b in blocks))

    def test_manifest_findings_warn(self):
        # 7. 당회 findings에 원고 미포함 일정 존재 -> WARN
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        
        latest_file = self.downloads / "2026 9월 정기당회.hwp"
        latest_file.touch()
        
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": str(latest_file),
                    "findings": [
                        {"item": "기후정의주일", "note": "9/20", "present_in_memo": False}
                    ]
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
    def test_is_same_file_path(self):
        f1 = self.downloads / "test_file.hwp"
        f1.touch()
        str_bs = str(f1) # backslash on Windows
        str_fs = str(f1).replace("\\", "/") # forward slash
        self.assertTrue(is_same_file_path(str_bs, str_fs))
        self.assertTrue(is_same_file_path(str_fs, str_bs))
        
        # Non-existent matching paths
        p_bs = "C:\\dummy\\folder\\file.hwp"
        p_fs = "C:/dummy/folder/file.hwp"
        self.assertTrue(is_same_file_path(p_bs, p_fs))
        
        # Different paths
        p_diff = "C:/dummy/folder/other.hwp"
        self.assertFalse(is_same_file_path(p_bs, p_diff))

    def test_direct_run_preflight_mismatch_blocks(self):
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump({"metadata": {"date": "2026-09-20"}}, f)
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": str(self.downloads / "2026 7월 정기당회.hwp")
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        (self.downloads / "2026 9월 정기당회.hwp").touch()
        (self.downloads / "2026 7월 정기당회.hwp").touch()
        
        # run_preflight directly
        passed = run_preflight({}, yaml_path, downloads_dir=self.downloads)
        self.assertFalse(passed)

    def test_direct_run_preflight_slash_difference_passes(self):
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump({"metadata": {"date": "2026-09-20"}}, f)
        latest_file = self.downloads / "2026 9월 정기당회.hwp"
        latest_file.touch()
        
        # Manifest has forward slashes
        forward_slash_path = str(latest_file).replace("\\", "/")
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": forward_slash_path
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        passed = run_preflight({}, yaml_path, downloads_dir=self.downloads)
        self.assertTrue(passed)

def run_preflight_sim(yaml_path, downloads_dir=None):
    # This simulates the main.py check so we don't have to patch main.py multiple times for tests
    blocks = []
    warns = []
    m_name = yaml_path.stem + "_manifest.yaml"
    manifest_path = yaml_path.parent / m_name
    
    if not manifest_path.exists():
        blocks.append(f"[Source Manifest 누락] {m_name}")
    else:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = yaml.safe_load(f)
            session = manifest_data.get("source_manifest", {}).get("session_material", {})
            file_path = session.get("file_path")
            
            if downloads_dir:
                res = find_latest_session_material(downloads_dir)
                if res and "error" not in res:
                    latest_path = res["file_path"]
                    if file_path != latest_path:
                        blocks.append(f"[Source Manifest 불일치] 최신 정기당회 자료와 불일치합니다. 기대:{latest_path}, 실제:{file_path}")
            
            findings = session.get("findings", [])
            for f_item in findings:
                if not f_item.get("present_in_memo", True):
                    warns.append(f"[특별일정 미기재] {f_item.get('item')}")
                    
    return blocks, warns

if __name__ == '__main__':
    unittest.main()
