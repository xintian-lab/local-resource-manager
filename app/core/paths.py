from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path


APP_NAME = "Local Resource Manager"


def app_root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def project_root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return project_root_dir()


def icons_dir() -> Path:
    return resource_dir() / "assets" / "icons"


def user_data_dir() -> Path:
    if not getattr(sys, "frozen", False):
        return app_root_dir()

    base_dir = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base_dir) / APP_NAME


def data_dir() -> Path:
    path = user_data_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = user_data_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "file_index.db"


def database_path_for_root(root_path: str) -> Path:
    normalized = str(Path(root_path).expanduser().resolve())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return data_dir() / f"file_index_{digest}.db"


def bookmarks_path() -> Path:
    return config_dir() / "bookmarks.json"


def settings_path() -> Path:
    return config_dir() / "settings.json"
