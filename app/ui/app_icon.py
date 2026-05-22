from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from app.core.paths import icons_dir

ICON_BASENAMES = ("app_icon",)
ICON_EXTENSIONS = (".ico", ".png", ".jpg", ".jpeg", ".webp")


def _icon_candidates() -> list[Path]:
    icons = icons_dir()
    candidates: list[Path] = []
    for base in ICON_BASENAMES:
        for extension in ICON_EXTENSIONS:
            candidates.append(icons / f"{base}{extension}")
    return candidates


def app_icon_path() -> Path | None:
    for path in _icon_candidates():
        if path.is_file():
            return path
    return None


def load_app_icon() -> QIcon:
    path = app_icon_path()
    if path is None:
        return QIcon()

    icon = QIcon(str(path))
    if icon.isNull():
        image = QImage(str(path))
        if image.isNull():
            return QIcon()
        return QIcon(QPixmap.fromImage(image))
    return icon


def apply_app_icon(
    app: QApplication,
    window: QWidget | QMainWindow | None = None,
) -> bool:
    icon = load_app_icon()
    if icon.isNull():
        return False

    app.setWindowIcon(icon)
    if window is not None:
        window.setWindowIcon(icon)
    return True


def _png_dimensions(png_data: bytes) -> tuple[int, int]:
    if len(png_data) < 24 or png_data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG data")
    width = int.from_bytes(png_data[16:20], "big")
    height = int.from_bytes(png_data[20:24], "big")
    return width, height


def write_ico_from_png(png_path: Path, ico_path: Path) -> None:
    png_data = png_path.read_bytes()
    width, height = _png_dimensions(png_data)

    icon_dir = struct.pack("<HHH", 0, 1, 1)
    icon_entry = struct.pack(
        "<BBBBHHII",
        0 if width >= 256 else width,
        0 if height >= 256 else height,
        0,
        0,
        1,
        32,
        len(png_data),
        len(icon_dir) + 16,
    )
    ico_path.write_bytes(icon_dir + icon_entry + png_data)


def ensure_build_icons() -> Path | None:
    source = app_icon_path()
    if source is None:
        return None

    icons = icons_dir()
    icons.mkdir(parents=True, exist_ok=True)

    png_path = icons / "app_icon.png"
    ico_path = icons / "app_icon.ico"

    image = QImage(str(source))
    if image.isNull():
        return None

    if not png_path.exists() or source.resolve() != png_path.resolve():
        image.save(str(png_path), "PNG")

    if not ico_path.exists() or ico_path.stat().st_mtime < png_path.stat().st_mtime:
        write_ico_from_png(png_path, ico_path)

    return ico_path if ico_path.is_file() else None
