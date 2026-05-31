from __future__ import annotations

import os
import sys
from pathlib import Path


def get_data_dir() -> Path:
    if data_dir := os.getenv("HELIX_DATA_DIR"):
        return Path(data_dir)

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Helix"
    if sys.platform == "win32":
        app_data = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(app_data) / "Helix"

    return Path.home() / ".local" / "share" / "helix"


def get_plugins_dir() -> Path:
    return get_data_dir() / "plugins"
