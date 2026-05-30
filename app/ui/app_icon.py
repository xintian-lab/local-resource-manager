from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from app.core.paths import icons_dir

ICON_BASENAMES = ("app_icon",)
ICON_EXTENSIONS = (".ico", ".icns", ".png", ".jpg", ".jpeg", ".webp")


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


_MAC_ICNS_SIZES: tuple[tuple[int, str], ...] = (
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
)


def write_icns_from_png(png_path: Path, icns_path: Path) -> bool:
    if sys.platform != "darwin":
        return False

    image = QImage(str(png_path))
    if image.isNull():
        return False

    with tempfile.TemporaryDirectory() as tmp_dir:
        iconset = Path(tmp_dir) / "AppIcon.iconset"
        iconset.mkdir()
        transform = Qt.TransformationMode.SmoothTransformation
        aspect = Qt.AspectRatioMode.IgnoreAspectRatio
        for size, filename in _MAC_ICNS_SIZES:
            scaled = image.scaled(size, size, aspect, transform)
            if scaled.isNull() or not scaled.save(str(iconset / filename), "PNG"):
                return False

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(icns_path)],
            check=True,
            capture_output=True,
        )

    return icns_path.is_file()


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

    if sys.platform == "darwin":
        icns_path = icons / "app_icon.icns"
        if not icns_path.exists() or icns_path.stat().st_mtime < png_path.stat().st_mtime:
            if not write_icns_from_png(png_path, icns_path):
                return None
        return icns_path if icns_path.is_file() else None

    return ico_path if ico_path.is_file() else None
