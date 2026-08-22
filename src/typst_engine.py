"""Typst 조판 및 PDF 생성 엔진."""
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict


class TypstEngine:
    """Engine for generating Typst source and compiling to PDF."""

    def __init__(self, template_path: Path | str):
        self.template_path = Path(template_path)
        if not self.template_path.is_file():
            raise FileNotFoundError(f"Typst template not found: {self.template_path}")

    def compile(self, output_pdf_path: Path | str, typst_bin: str = "typst") -> Path:
        """Compile Typst file into a PDF.
        
        Args:
            output_pdf_path: Target destination path for compiled PDF.
            typst_bin: Path or command name for typst executable.
            
        Returns:
            Path to the generated PDF.
            
        Raises:
            RuntimeError: If typst CLI is missing or compilation fails.
        """
        out_path = Path(output_pdf_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not shutil.which(typst_bin):
            raise RuntimeError(
                f"Typst binary '{typst_bin}' not found in PATH. "
                "Please install Typst (https://github.com/typst/typst) or use HWPX engine."
            )

        cmd = [typst_bin, "compile", str(self.template_path), str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"Typst compilation failed:\n{result.stderr}")

        return out_path
