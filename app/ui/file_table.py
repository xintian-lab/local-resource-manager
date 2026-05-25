from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QFileDialog,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from app.ui.layout_constants import CONTENT_PANEL_ID, PANEL_HEADER_HEIGHT
from app.ui.clipboard_paths import COPY_FULL_PATH_LABEL
from app.ui.file_type_icons import FileTypeIconProvider

from app.core.file_ops import open_containing_folder, open_file, open_file_with


class FileTable(QTableWidget):
    add_file_requested = Signal()
    copy_requested = Signal(list)
    cut_requested = Signal(list)
    delete_requested = Signal(list)
    folder_open_requested = Signal(str)
    paste_requested = Signal()
    copy_path_requested = Signal(str)

    headers = ["Name", "Extension", "Size", "Modified", "Folder"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scroll_animation: QPropertyAnimation | None = None
        self.shortcut_labels: dict[str, str] = {}
        self.show_file_icons = True
        self.setObjectName(CONTENT_PANEL_ID)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCornerButtonEnabled(False)
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.setIconSize(QSize(16, 16))
        header = self.horizontalHeader()
        header.setFixedHeight(PANEL_HEADER_HEIGHT)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(0, 240)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.itemDoubleClicked.connect(self._open_selected_file)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_show_file_icons(self, enabled: bool) -> None:
        self.show_file_icons = enabled

    def set_files(self, files: Sequence[object]) -> None:
        self.set_results(
            [
                {
                    "result_type": "File",
                    "name": self._row_value(file_row, "name"),
                    "extension": self._row_value(file_row, "extension"),
                    "size": self._row_value(file_row, "size"),
                    "modified_time": self._row_value(file_row, "modified_time"),
                    "path": self._row_value(file_row, "path"),
                    "folder_path": self._row_value(file_row, "folder_path"),
                }
                for file_row in files
            ]
        )

    def set_results(self, results: Sequence[object]) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(len(results))
        icon_provider = FileTypeIconProvider.shared() if self.show_file_icons else None

        for row_index, result_row in enumerate(results):
            path = self._row_value(result_row, "path")
            result_type = self._row_value(result_row, "result_type") or "File"
            size = self._row_value(result_row, "size")
            modified_time = self._row_value(result_row, "modified_time")
            file_name = self._row_value(result_row, "name")
            file_extension = self._row_value(result_row, "extension")
            values = [
                file_name,
                file_extension,
                self._format_size(int(size)) if size else "",
                self._format_modified(float(modified_time)) if modified_time else "",
                self._row_value(result_row, "folder_path"),
            ]

            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setData(Qt.ItemDataRole.UserRole + 1, result_type)
                if column_index == 0 and result_type == "File" and icon_provider is not None:
                    item.setIcon(
                        icon_provider.icon_for_file(name=file_name, extension=file_extension)
                    )
                if column_index == 2 and size:
                    item.setData(Qt.ItemDataRole.UserRole + 2, int(size))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(row_index, column_index, item)

        self.setSortingEnabled(True)

    def set_shortcut_labels(self, shortcut_labels: dict[str, str]) -> None:
        self.shortcut_labels = shortcut_labels

    def scroll_vertically(self, direction: int) -> None:
        scrollbar = self.verticalScrollBar()
        step = max(1, scrollbar.pageStep() // 3)
        target = scrollbar.value() + (step * direction)
        target = max(scrollbar.minimum(), min(target, scrollbar.maximum()))
        if target == scrollbar.value():
            return

        self.scroll_animation = QPropertyAnimation(scrollbar, b"value", self)
        self.scroll_animation.setDuration(120)
        self.scroll_animation.setStartValue(scrollbar.value())
        self.scroll_animation.setEndValue(target)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scroll_animation.start()

    def _show_context_menu(self, position: QPoint) -> None:
        file_path = self._path_at_position(position)
        result_type = self._type_at_position(position)
        selected_file_paths = self.selected_file_paths()
        action_file_paths = (
            selected_file_paths
            if file_path in selected_file_paths
            else [file_path] if file_path and result_type == "File" else []
        )

        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        open_action = None
        open_with_action = None
        open_folder_action = None
        copy_action = None
        cut_action = None
        delete_action = None
        copy_path_action = None

        if action_file_paths:
            open_action = menu.addAction("Open File")
            open_with_action = menu.addAction("Open With...")
            open_folder_action = menu.addAction("Open Containing Folder")
            menu.addSeparator()
            copy_action = menu.addAction(self._action_label("Copy", "copy_file"))
            cut_action = menu.addAction(self._action_label("Cut", "cut_file"))
            delete_action = menu.addAction(self._action_label("Delete", "delete_file"))
            menu.addSeparator()
            copy_path_action = menu.addAction(COPY_FULL_PATH_LABEL)
            menu.addSeparator()
        elif file_path and result_type == "Folder":
            open_action = menu.addAction("Open Folder")
            open_folder_action = menu.addAction("Open Containing Folder")
            menu.addSeparator()
            copy_path_action = menu.addAction(COPY_FULL_PATH_LABEL)
            menu.addSeparator()

        add_file_action = menu.addAction("Add File...")
        paste_action = menu.addAction(self._action_label("Paste", "paste_file"))
        selected_action = menu.exec(self.viewport().mapToGlobal(position))
        if selected_action is None:
            return

        if selected_action == open_action:
            if result_type == "Folder":
                self.folder_open_requested.emit(file_path)
            else:
                open_file(action_file_paths[0])
        elif selected_action == open_with_action:
            self._open_file_with(action_file_paths[0])
        elif selected_action == open_folder_action:
            target_path = action_file_paths[0] if action_file_paths else file_path
            open_containing_folder(target_path)
        elif selected_action == copy_action:
            self.copy_requested.emit(action_file_paths)
        elif selected_action == cut_action:
            self.cut_requested.emit(action_file_paths)
        elif selected_action == delete_action:
            self.delete_requested.emit(action_file_paths)
        elif selected_action == copy_path_action and file_path:
            self.copy_path_requested.emit(file_path)
        elif selected_action == add_file_action:
            self.add_file_requested.emit()
        elif selected_action == paste_action:
            self.paste_requested.emit()

    def _open_file_with(self, file_path: str) -> None:
        try:
            if platform.system() == "Windows":
                open_file_with(file_path)
                return
        except OSError as exc:
            if platform.system() != "Windows":
                raise
            reply = QMessageBox.question(
                self,
                "Open With",
                (
                    "Could not open the system 'Open with' dialog.\n\n"
                    f"{exc}\n\n"
                    "Choose an application manually?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        application, _filter = QFileDialog.getOpenFileName(
            self,
            "Open With",
            "",
            "Applications (*.exe);;All Files (*)",
        )
        if not application:
            return
        try:
            open_file_with(file_path, application)
        except OSError as exc:
            QMessageBox.warning(self, "Open With", str(exc))

    def _open_selected_file(self, *_args: object) -> None:
        file_path = self._selected_path()
        result_type = self._selected_type()
        if file_path and result_type == "Folder":
            self.folder_open_requested.emit(file_path)
        elif file_path:
            open_file(file_path)

    def _path_at_position(self, position: QPoint) -> str:
        row = self.rowAt(position.y())
        if row < 0:
            return ""
        item = self.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def _type_at_position(self, position: QPoint) -> str:
        row = self.rowAt(position.y())
        if row < 0:
            return ""
        item = self.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole + 1)) if item else ""

    def _selected_path(self) -> str:
        selected_items = self.selectedItems()
        if not selected_items:
            return ""
        return str(selected_items[0].data(Qt.ItemDataRole.UserRole))

    def _selected_type(self) -> str:
        selected_items = self.selectedItems()
        if not selected_items:
            return ""
        return str(selected_items[0].data(Qt.ItemDataRole.UserRole + 1))

    def selected_path(self) -> str:
        return self._selected_path()

    def selected_result_type(self) -> str:
        return self._selected_type()

    def selected_file_paths(self) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for item in self.selectedItems():
            path = str(item.data(Qt.ItemDataRole.UserRole))
            result_type = str(item.data(Qt.ItemDataRole.UserRole + 1))
            if result_type == "File" and path and path not in seen:
                paths.append(path)
                seen.add(path)
        return paths

    def _action_label(self, label: str, action_id: str) -> str:
        shortcut = self.shortcut_labels.get(action_id, "")
        return f"{label} ({shortcut})" if shortcut else label

    def _row_value(self, row: object, key: str) -> str:
        try:
            return str(row[key])  # type: ignore[index]
        except (KeyError, TypeError):
            return str(getattr(row, key))

    def _format_size(self, size: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        unit_index = 0
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1
        if unit_index == 0:
            return f"{int(value)} {units[unit_index]}"
        return f"{value:.1f} {units[unit_index]}"

    def _format_modified(self, timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    def selected_file_path(self) -> Path | None:
        selected_path = self._selected_path()
        return Path(selected_path) if selected_path else None
