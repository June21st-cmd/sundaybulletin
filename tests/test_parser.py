"""Unit tests for bulletin data parser."""
import tempfile
import unittest
from pathlib import Path

from src.parser import load_bulletin_data


class TestBulletinParser(unittest.TestCase):
    def test_load_valid_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, encoding="utf-8") as f:
            f.write("date: '2026-08-16'\nservice_name: '주일 예배'\n")
            temp_path = f.name
        
        try:
            data = load_bulletin_data(temp_path)
            self.assertEqual(data["date"], "2026-08-16")
            self.assertEqual(data["service_name"], "주일 예배")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_bulletin_data("non_existent_file.yaml")

    def test_invalid_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("hello")
            temp_path = f.name
        
        try:
            with self.assertRaises(ValueError):
                load_bulletin_data(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
