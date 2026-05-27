from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.core.file_ops import get_path_stat


def _format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


class PropertiesDialog(QDialog):
    def __init__(
        self,
        path: str,
        item_type: str,
        *,
        folder_file_count: int | None = None,
        folder_total_size: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        target = Path(path)
        self.setWindowTitle("Properties")
        self.setModal(True)
        self.resize(520, 260)

        stat_result = get_path_stat(target)
        created_time = getattr(stat_result, "st_birthtime", stat_result.st_ctime)

        form = QFormLayout()
        form.addRow("Name:", QLabel(target.name))
        form.addRow("Type:", QLabel("Folder" if item_type == "Folder" else "File"))

        location = QLabel(str(target))
        location.setWordWrap(True)
        form.addRow("Location:", location)

        if item_type == "Folder":
            file_count = folder_file_count if folder_file_count is not None else 0
            total_size = folder_total_size if folder_total_size is not None else 0
            form.addRow("Indexed files:", QLabel(str(file_count)))
            form.addRow("Indexed size:", QLabel(_format_size(total_size)))
        else:
            form.addRow("Size:", QLabel(_format_size(int(stat_result.st_size))))

        form.addRow("Modified:", QLabel(_format_timestamp(stat_result.st_mtime)))
        form.addRow("Created:", QLabel(_format_timestamp(float(created_time))))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
