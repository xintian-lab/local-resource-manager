from __future__ import annotations

from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider

# Pre-warm Windows/shell icons for common extensions at startup.
COMMON_EXTENSIONS: tuple[str, ...] = (
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
    "md",
    "rtf",
    "mp3",
    "wav",
    "flac",
    "m4a",
    "aac",
    "ogg",
    "wma",
    "mp4",
    "mov",
    "mkv",
    "avi",
    "webm",
    "wmv",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "bmp",
    "svg",
    "tif",
    "tiff",
    "heic",
    "py",
    "pyw",
    "js",
    "ts",
    "jsx",
    "tsx",
    "html",
    "htm",
    "css",
    "json",
    "xml",
    "yaml",
    "yml",
    "java",
    "cpp",
    "c",
    "h",
    "cs",
    "go",
    "rs",
    "rb",
    "php",
    "sql",
    "zip",
    "rar",
    "7z",
    "tar",
    "gz",
    "bz2",
    "exe",
    "msi",
    "dll",
    "csv",
    "ini",
    "log",
)


class FileTypeIconProvider:
    """Extension-based file icons: shell icons on Windows, cached per extension."""

    _shared: FileTypeIconProvider | None = None

    def __init__(self) -> None:
        self._provider = QFileIconProvider()
        self._cache: dict[str, QIcon] = {}
        self._default_icon = self._provider.icon(QFileIconProvider.IconType.File)
        self._folder_icon: QIcon | None = None

    @classmethod
    def shared(cls) -> FileTypeIconProvider:
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def folder_icon(self) -> QIcon:
        if self._folder_icon is None:
            icon = self._provider.icon(QFileIconProvider.IconType.Folder)
            self._folder_icon = icon if not icon.isNull() else self._default_icon
        return self._folder_icon

    def preload_common(self) -> None:
        self.folder_icon()
        for extension in COMMON_EXTENSIONS:
            self.icon_for_extension(extension)

    def icon_for_extension(self, extension: str) -> QIcon:
        normalized = extension.lower().lstrip(".")
        if not normalized:
            return self._default_icon
        if normalized in self._cache:
            return self._cache[normalized]

        icon = self._provider.icon(QFileInfo(f"__file_type__.{normalized}"))
        if icon.isNull():
            icon = self._default_icon
        self._cache[normalized] = icon
        return icon

    def icon_for_file(self, *, name: str, extension: str) -> QIcon:
        normalized = extension.lower().lstrip(".")
        if not normalized and "." in name:
            normalized = name.rsplit(".", 1)[-1].lower()
        return self.icon_for_extension(normalized)
