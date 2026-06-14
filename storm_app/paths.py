from __future__ import annotations

import sys
import shutil
from pathlib import Path


FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
SCRIPTS_DIR = (BUNDLE_ROOT / "scripts") if FROZEN else ROOT / "scripts"
OUTPUT_DIR = ROOT / "scraper_outputs"
BUNDLED_CONFIG_DIR = BUNDLE_ROOT / "config"
BUNDLED_TEMPLATE_PATH = BUNDLE_ROOT / "Competitors Analysis Blank Template.xlsx"
APP_TEMPLATE_PATH = ROOT / "Competitors Analysis Blank Template.xlsx"


def ensure_script_imports() -> None:
    scripts_path = str(SCRIPTS_DIR)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)


def ensure_external_resources() -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    if BUNDLED_CONFIG_DIR.exists():
        for source in BUNDLED_CONFIG_DIR.glob("*.json"):
            target = CONFIG_DIR / source.name
            if not target.exists():
                shutil.copy2(source, target)
    if BUNDLED_TEMPLATE_PATH.exists() and not APP_TEMPLATE_PATH.exists():
        shutil.copy2(BUNDLED_TEMPLATE_PATH, APP_TEMPLATE_PATH)
