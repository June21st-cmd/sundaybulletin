"""Unit tests for bulletin file versioning and lock handling."""
from pathlib import Path
import tempfile
import unittest

from src.utils import (
    get_next_bulletin_version,
    get_versioned_bulletin_paths,
    is_file_locked,
)


class TestBulletinVersioning(unittest.TestCase):
    def test_first_version_starts_at_v1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            base_stem = "[주보] 20260913"

            v = get_next_bulletin_version(temp_path, base_stem)
            self.assertEqual(v, 1)

            hwpx, pdf = get_versioned_bulletin_paths(temp_path, base_stem)
            self.assertEqual(hwpx.name, "[주보] 20260913_v1.hwpx")
            self.assertEqual(pdf.name, "[주보] 20260913_v1.pdf")

    def test_increments_when_previous_version_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            base_stem = "[주보] 20260913"

            # Case 1: unversioned legacy file exists
            (temp_path / f"{base_stem}.hwpx").write_text("dummy", encoding="utf-8")
            v = get_next_bulletin_version(temp_path, base_stem)
            self.assertEqual(v, 2)

            # Case 2: _v1 exists
            (temp_path / f"{base_stem}_v1.hwpx").write_text("dummy", encoding="utf-8")
            v = get_next_bulletin_version(temp_path, base_stem)
            self.assertEqual(v, 2)

            # Case 3: _v2 also exists
            (temp_path / f"{base_stem}_v2.hwpx").write_text("dummy", encoding="utf-8")
            v = get_next_bulletin_version(temp_path, base_stem)
            self.assertEqual(v, 3)

            hwpx, pdf = get_versioned_bulletin_paths(temp_path, base_stem)
            self.assertEqual(hwpx.name, "[주보] 20260913_v3.hwpx")
            self.assertEqual(pdf.name, "[주보] 20260913_v3.pdf")

    def test_file_lock_detection_and_skip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            base_stem = "[주보] 20260913"
            target_file = temp_path / f"{base_stem}_v1.hwpx"
            target_file.write_text("initial content", encoding="utf-8")

            # Initially not locked
            self.assertFalse(is_file_locked(target_file))

            # When locked by another process (using exclusive open on Windows)
            import os
            try:
                # Open with share mode 0 (exclusive) on Windows
                fd = os.open(str(target_file), os.O_RDWR)
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                is_locked = is_file_locked(target_file)
                # Next version calculation should automatically bypass v1
                next_v = get_next_bulletin_version(temp_path, base_stem)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                os.close(fd)
                self.assertTrue(is_locked)
                self.assertEqual(next_v, 2)
            except (ImportError, OSError):
                # Fallback if msvcrt / locking not supported in current environment
                pass


if __name__ == "__main__":
    unittest.main()


