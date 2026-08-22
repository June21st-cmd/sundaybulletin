"""Project path configurations and constants."""
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Standard directory paths
TEMPLATES_DIR = PROJECT_ROOT / "templates"
HWPX_TEMPLATE_DIR = TEMPLATES_DIR / "hwpx"
TYPST_TEMPLATE_DIR = TEMPLATES_DIR / "typst"

DATA_DIR = PROJECT_ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
INPUTS_DIR = DATA_DIR / "inputs"

OUTPUT_DIR = PROJECT_ROOT / "output"
DOCS_DIR = PROJECT_ROOT / "docs"

# Default template files
DEFAULT_HWPX_TEMPLATE = HWPX_TEMPLATE_DIR / "template.hwpx"
DEFAULT_TYPST_TEMPLATE = TYPST_TEMPLATE_DIR / "bulletin.typ"
