"""Utility functions for bulletin file management and versioning."""
import os
from pathlib import Path
import re
from typing import Tuple


def get_next_bulletin_version(directory: Path | str, base_stem: str) -> int:
    """Find the next version number for a bulletin file set.

    Scans the directory for existing files matching the base stem, e.g.:
      - [주보] 20260913.hwpx / .pdf -> counts as v1
      - [주보] 20260913_v1.hwpx / .pdf -> counts as v1
      - [주보] 20260913_v2.hwpx / .pdf -> counts as v2

    Returns:
        Next integer version number (starts at 1 if none exist).
    """
    directory = Path(directory)
    if not directory.is_dir():
        return 1

    pattern = re.compile(
        rf"^{re.escape(base_stem)}(?:_v(\d+))?(?:\.(?:hwpx|pdf|hwp))?$",
        re.IGNORECASE,
    )

    max_version = 0
    found_any = False

    for item in directory.iterdir():
        if not item.is_file():
            continue
        m = pattern.match(item.name)
        if m:
            found_any = True
            v_str = m.group(1)
            if v_str:
                max_version = max(max_version, int(v_str))
            else:
                max_version = max(max_version, 1)

    next_version = max_version + 1 if found_any else 1

    # Ensure the proposed version is not locked by any active process (e.g. 한컴오피스)
    while True:
        candidate_hwpx = directory / f"{base_stem}_v{next_version}.hwpx"
        if candidate_hwpx.exists() and is_file_locked(candidate_hwpx):
            next_version += 1
            continue
        break

    return next_version


def is_file_locked(file_path: Path | str) -> bool:
    """Check if a file is currently open/locked exclusively by another process (e.g., Hancom Office)."""
    p = Path(file_path)
    if not p.exists():
        return False

    # 1. On Windows, renaming a file to itself raises PermissionError / WinError 32 if open in Hancom Office
    try:
        os.rename(str(p), str(p))
    except (PermissionError, OSError):
        return True

    # 2. Test read-write mode
    try:
        with open(p, "r+b"):
            pass
        return False
    except (PermissionError, OSError):
        return True



def get_versioned_bulletin_paths(
    directory: Path | str,
    base_stem: str,
    version: int | None = None,
) -> Tuple[Path, Path]:
    """Get paired HWPX and PDF output paths with matching version number.

    Args:
        directory: Destination directory (e.g., output/)
        base_stem: File stem without version/extension (e.g. "[주보] 20260913")
        version: Explicit version number. If None, auto-calculated as next available.

    Returns:
        Tuple of (hwpx_path, pdf_path)
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    if version is None:
        version = get_next_bulletin_version(dir_path, base_stem)

    hwpx_path = dir_path / f"{base_stem}_v{version}.hwpx"
    pdf_path = dir_path / f"{base_stem}_v{version}.pdf"
    return hwpx_path, pdf_path
