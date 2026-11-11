"""Paths are anchored to the checkout, independent of the launch directory."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT_DIR / "backend" / "static"
DATA_DIR = Path(os.environ.get("WEDDING_MIX_DATA_DIR", ROOT_DIR / "data")).resolve()
HOST = "127.0.0.1"
PORT = 8000


def prepare_data_directories() -> None:
    for name in ("originals", "work", "peaks", "exports", "previews"):
        (DATA_DIR / name).mkdir(parents=True, exist_ok=True)

