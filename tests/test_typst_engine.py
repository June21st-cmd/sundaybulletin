"""Unit tests for Typst engine."""
import tempfile
import unittest
from pathlib import Path

from src.typst_engine import TypstEngine


class TestTypstEngine(unittest.TestCase):
    def test_template_not_found(self):
        with self.assertRaises(FileNotFoundError):
            TypstEngine("non_existent_template.typ")

    def test_init_valid_template(self):
        with tempfile.NamedTemporaryFile(suffix=".typ", mode="w", delete=False, encoding="utf-8") as f:
            f.write("#set page(paper: 'a4')\n[Hello Typst]")
            temp_path = f.name
        
        try:
            engine = TypstEngine(temp_path)
            self.assertEqual(engine.template_path, Path(temp_path))
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
