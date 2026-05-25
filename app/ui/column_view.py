from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal, QSize
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.layout_constants import (
    CONTENT_PANEL_ID,
    FOLDER_COLUMN_ID,
    PANEL_HEADER_HEIGHT,
    PANEL_HEADER_ID,
)
from app.ui.clipboard_paths import COPY_FULL_PATH_LABEL
from app.ui.file_type_icons import FileTypeIconProvider

FolderLoader = Callable[[str, str], Sequence[object]]


class ColumnView(QWidget):
    folder_selected = Signal(str)
    bookmark_requested = Signal(str)
    copy_path_requested = Signal(str)

    def __init__(self, folder_loader: FolderLoader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.folder_loader = folder_loader
        self.root_path = ""
        self.current_path = ""
        self.pinned_path = ""
        self.search_query = ""
        self.columns: list[QListWidget] = []
        self.active_column_index = 0
        self.show_folder_icons = True
        self.scroll_animation: QPropertyAnimation | None = None

        self.setObjectName(CONTENT_PANEL_ID)

        self.header_label = QLabel("Folders")
        self.header_label.setObjectName(PANEL_HEADER_ID)
        self.header_label.setFixedHeight(PANEL_HEADER_HEIGHT)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.column_layout = QHBoxLayout(self.container)
        self.column_layout.setContentsMargins(0, 0, 0, 0)
        self.column_layout.setSpacing(0)
        self.column_layout.addStretch(1)
        self.scroll_area.setWidget(self.container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header_label)
        layout.addWidget(self.scroll_area, stretch=1)

    def set_show_folder_icons(self, enabled: bool) -> None:
        self.show_folder_icons = enabled

    def set_root(self, root_path: str, *, emit_selection: bool = True) -> None:
        self.root_path = root_path
        self.current_path = root_path
        self.active_column_index = 0
        self._clear_columns()
        self._add_column(root_path, selected_path=root_path, force=True)
        self._scroll_to_start()
        if emit_selection:
            self.folder_selected.emit(root_path)

    def set_search_query(self, query: str, *, reset_to_root: bool = False) -> None:
        self.search_query = query
        if not self.root_path:
            return
        if query.strip() and reset_to_root:
            self._show_root_only()
        else:
            self.rebuild_to_path(self.current_path)

    def _show_root_only(self) -> None:
        self._clear_columns()
        self.active_column_index = 0
        self._add_column(self.root_path, selected_path=self.root_path, force=True)
        self.current_path = self.root_path
        self._scroll_to_start()

    def set_pinned_path(self, pinned_path: str) -> None:
        self.pinned_path = pinned_path
        if self.root_path:
            self.rebuild_to_path(self.current_path)

    def rebuild_to_path(self, selected_path: str) -> None:
        if not self.root_path:
            return

        path_chain = self._path_chain(selected_path)
        self._clear_columns()
        self.active_column_index = 0

        parent_path = self.root_path
        selected_child = path_chain[1] if len(path_chain) > 1 else ""
        self._add_column(parent_path, selected_child, force=True)

        for index, parent_path in enumerate(path_chain[1:], start=1):
            selected_child = path_chain[index + 1] if index + 1 < len(path_chain) else ""
            self._add_column(parent_path, selected_child)

        self.current_path = selected_path
        self.active_column_index = max(0, len(path_chain) - 2)
        if self.columns:
            self._scroll_to_column(self.columns[-1])

    def _add_column(self, parent_path: str, selected_path: str = "", force: bool = False) -> bool:
        folders = self.folder_loader(parent_path, self.search_query)
        if not folders and not force:
            return False

        column = QListWidget()
        column.setObjectName(FOLDER_COLUMN_ID)
        column.setMinimumWidth(220)
        column.setMaximumWidth(320)
        column.setFrameShape(QFrame.Shape.NoFrame)
        column.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        column.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        column.customContextMenuRequested.connect(self._show_folder_context_menu)
        column.itemClicked.connect(self._handle_item_clicked)
        column.setProperty("parent_path", parent_path)
        self._configure_folder_column(column)

        folder_icon = (
            FileTypeIconProvider.shared().folder_icon() if self.show_folder_icons else None
        )

        root_item: QListWidgetItem | None = None
        if parent_path == self.root_path:
            root_item = QListWidgetItem(self._root_entry_label())
            root_item.setData(Qt.ItemDataRole.UserRole, self.root_path)
            if folder_icon is not None:
                root_item.setIcon(folder_icon)
            column.addItem(root_item)

        selected_item: QListWidgetItem | None = None
        for folder in folders:
            folder_path = self._row_value(folder, "path")
            item = QListWidgetItem(self._folder_label(folder))
            item.setData(Qt.ItemDataRole.UserRole, folder_path)
            if folder_icon is not None:
                item.setIcon(folder_icon)
            if self._is_strict_ancestor(folder_path, self.pinned_path):
                item.setForeground(QBrush(QColor("#888888")))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            column.addItem(item)
            if selected_path and folder_path == selected_path:
                selected_item = item

        if parent_path == self.root_path:
            if selected_path == self.root_path or (
                not selected_path and not selected_item
            ):
                selected_item = root_item
            elif not selected_item and root_item is not None:
                selected_item = root_item

        if selected_item is not None:
            column.setCurrentItem(selected_item)

        self.column_layout.insertWidget(len(self.columns), column)
        self.columns.append(column)
        return True

    def _add_empty_column(self, parent_path: str = "") -> None:
        column = QListWidget()
        column.setObjectName(FOLDER_COLUMN_ID)
        column.setMinimumWidth(220)
        column.setMaximumWidth(320)
        column.setFrameShape(QFrame.Shape.NoFrame)
        column.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        column.setProperty("parent_path", parent_path)
        self.column_layout.insertWidget(len(self.columns), column)
        self.columns.append(column)

    def _handle_item_clicked(self, item: QListWidgetItem) -> None:
        column = item.listWidget()
        if column is None:
            return

        column_index = self.columns.index(column)
        selected_path = str(item.data(Qt.ItemDataRole.UserRole))
        self.active_column_index = column_index
        self._select_item_in_column(column_index, item)

    def _show_folder_context_menu(self, position) -> None:
        column = self.sender()
        if not isinstance(column, QListWidget):
            return

        item = column.itemAt(position)
        if item is None:
            return

        folder_path = str(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        save_action = menu.addAction("Save to Tabs")
        copy_path_action = menu.addAction(COPY_FULL_PATH_LABEL)
        chosen = menu.exec(column.mapToGlobal(position))
        if chosen is save_action:
            self.bookmark_requested.emit(folder_path)
        elif chosen is copy_path_action:
            self.copy_path_requested.emit(folder_path)

    def _remove_columns_after(self, column_index: int) -> None:
        while len(self.columns) > column_index + 1:
            column = self.columns.pop()
            self.column_layout.removeWidget(column)
            column.deleteLater()

    def _clear_columns(self) -> None:
        while self.columns:
            column = self.columns.pop()
            self.column_layout.removeWidget(column)
            column.deleteLater()

    def _scroll_to_column(self, column: QListWidget) -> None:
        QTimer.singleShot(25, lambda: self._animate_to_column(column))

    def scroll_one_column_left(self) -> None:
        scrollbar = self.scroll_area.horizontalScrollBar()
        current = scrollbar.value()
        candidates = [column for column in self.columns if column.x() < current - 5]
        if candidates:
            self._animate_to_scroll_value(candidates[-1].x())

    def scroll_one_column_right(self) -> None:
        scrollbar = self.scroll_area.horizontalScrollBar()
        current = scrollbar.value()
        candidates = [column for column in self.columns if column.x() > current + 5]
        if candidates:
            self._animate_to_scroll_value(candidates[0].x())

    def select_previous_folder(
        self,
        animate_child_preview: bool = True,
        commit: bool = True,
    ) -> bool:
        return self._move_selection(-1, animate_child_preview, commit=commit)

    def select_next_folder(
        self,
        animate_child_preview: bool = True,
        commit: bool = True,
    ) -> bool:
        return self._move_selection(1, animate_child_preview, commit=commit)

    def commit_active_column_selection(self) -> bool:
        column = self._active_column()
        if column is None:
            return False

        item = column.currentItem()
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsEnabled:
            item = self._ensure_current_item(column)
        if item is None:
            return False

        selected_path = str(item.data(Qt.ItemDataRole.UserRole))
        if selected_path == self.current_path:
            return False

        self._select_item_in_column(
            self.columns.index(column),
            item,
            force_scroll_to_selected=True,
        )
        return True

    def ensure_keyboard_selection(self) -> bool:
        column = self._active_column()
        if column is None:
            return False

        item = self._ensure_current_item(column)
        if item is None:
            return False

        self._select_item_in_column(self.columns.index(column), item)
        return True

    def enter_selected_folder(self) -> bool:
        column = self._active_column()
        if column is None:
            return False

        item = self._ensure_current_item(column)
        if item is None:
            return False

        column_index = self.columns.index(column)
        selected_path = str(item.data(Qt.ItemDataRole.UserRole))
        if not self._ensure_child_preview_column(column_index, selected_path):
            return False

        child_column_index = column_index + 1
        child_column = self.columns[child_column_index]
        child_item = self._first_enabled_item(child_column)
        if child_item is None:
            return False

        self.active_column_index = child_column_index
        self._select_item_in_column(child_column_index, child_item, force_scroll_to_selected=True)
        return True

    def leave_current_folder(self) -> bool:
        if not self.columns or self.active_column_index <= 0:
            return False

        parent_column_index = self.active_column_index - 1
        parent_column = self.columns[parent_column_index]
        item = self._ensure_current_item(parent_column)
        if item is None:
            return False

        self.active_column_index = parent_column_index
        self._select_item_in_column(parent_column_index, item, force_scroll_to_selected=True)
        return True

    def _move_selection(
        self,
        direction: int,
        animate_child_preview: bool,
        commit: bool = True,
    ) -> bool:
        column = self._active_column()
        if column is None:
            return False

        column_index = self.columns.index(column)

        def apply_item(item: QListWidgetItem) -> None:
            if commit:
                self._select_item_in_column(
                    column_index,
                    item,
                    animate_child_preview=animate_child_preview,
                )
            else:
                self._highlight_item_in_column(column_index, item)

        current_item = column.currentItem()
        if current_item is None or not current_item.flags() & Qt.ItemFlag.ItemIsEnabled:
            first_item = self._first_enabled_item(column)
            if first_item is None:
                return False
            apply_item(first_item)
            return True

        current_item = self._ensure_current_item(column)
        if current_item is None:
            return False

        current_row = column.row(current_item)
        stop = column.count() if direction > 0 else -1
        row_range = range(current_row + direction, stop, direction)
        for row_index in row_range:
            item = column.item(row_index)
            if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                apply_item(item)
                return True

        wrap_target = (
            self._first_enabled_item(column)
            if direction > 0
            else self._last_enabled_item(column)
        )
        if wrap_target is not None and wrap_target is not current_item:
            apply_item(wrap_target)
            return True
        return False

    def _highlight_item_in_column(self, column_index: int, item: QListWidgetItem) -> None:
        column = self.columns[column_index]
        column.setCurrentItem(item)
        column.scrollToItem(item)

    def _select_item_in_column(
        self,
        column_index: int,
        item: QListWidgetItem,
        force_scroll_to_selected: bool = False,
        animate_child_preview: bool = True,
    ) -> None:
        column = self.columns[column_index]
        column.setCurrentItem(item)
        selected_path = str(item.data(Qt.ItemDataRole.UserRole))
        if selected_path == self.root_path:
            self._remove_columns_after(column_index)
            self.current_path = selected_path
            self.folder_selected.emit(selected_path)
            self._scroll_to_column(column)
            return

        previous_column_count = len(self.columns)
        had_next_column = previous_column_count > column_index + 1
        added_child_column = self._update_child_preview_columns(
            column_index,
            selected_path,
            keep_column_count=had_next_column,
            minimum_column_count=previous_column_count,
        )

        self.current_path = selected_path
        self.folder_selected.emit(selected_path)

        if force_scroll_to_selected:
            self._scroll_to_column(column)
        elif animate_child_preview and added_child_column and len(self.columns) > column_index + 1:
            self._scroll_to_column(self.columns[column_index + 1])
        elif not had_next_column:
            self._scroll_to_column(column)

    def _ensure_child_preview_column(self, column_index: int, selected_path: str) -> bool:
        if len(self.columns) > column_index + 1:
            child_column = self.columns[column_index + 1]
            if child_column.property("parent_path") == selected_path:
                return child_column.count() > 0

        if not self.folder_loader(selected_path, self.search_query):
            return False

        return self._update_child_preview_columns(
            column_index,
            selected_path,
            keep_column_count=False,
            minimum_column_count=len(self.columns),
        )

    def _update_child_preview_columns(
        self,
        column_index: int,
        selected_path: str,
        keep_column_count: bool,
        minimum_column_count: int,
    ) -> bool:
        self._remove_columns_after(column_index)
        added_child_column = self._add_column(selected_path)
        if not added_child_column and keep_column_count:
            self._add_empty_column(selected_path)
        while keep_column_count and len(self.columns) < minimum_column_count:
            self._add_empty_column()
        return added_child_column

    def _active_column(self) -> QListWidget | None:
        if not self.columns:
            return None

        self.active_column_index = max(
            0,
            min(self.active_column_index, len(self.columns) - 1),
        )
        return self.columns[self.active_column_index]

    def _ensure_current_item(self, column: QListWidget) -> QListWidgetItem | None:
        current_item = column.currentItem()
        if current_item and current_item.flags() & Qt.ItemFlag.ItemIsEnabled:
            return current_item

        first_item = self._first_enabled_item(column)
        if first_item:
            column.setCurrentItem(first_item)
        return first_item

    def _first_enabled_item(self, column: QListWidget) -> QListWidgetItem | None:
        for row_index in range(column.count()):
            item = column.item(row_index)
            if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                return item
        return None

    def _last_enabled_item(self, column: QListWidget) -> QListWidgetItem | None:
        for row_index in range(column.count() - 1, -1, -1):
            item = column.item(row_index)
            if item and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                return item
        return None

    def _animate_to_column(self, column: QListWidget) -> None:
        if column not in self.columns:
            return

        self.container.adjustSize()
        self.container.updateGeometry()
        self.scroll_area.updateGeometry()
        scrollbar = self.scroll_area.horizontalScrollBar()
        scrollbar.setValue(scrollbar.value())
        viewport_width = self.scroll_area.viewport().width()
        column_left = column.x()
        column_right = column_left + column.width()
        current = scrollbar.value()
        target = current

        if column_right > current + viewport_width:
            target = column_right - viewport_width
        elif column_left < current:
            target = column_left

        target = max(scrollbar.minimum(), min(target, scrollbar.maximum()))
        if target == current:
            return

        self._animate_to_scroll_value(target)

    def _animate_to_scroll_value(self, target: int) -> None:
        scrollbar = self.scroll_area.horizontalScrollBar()
        current = scrollbar.value()
        target = max(scrollbar.minimum(), min(target, scrollbar.maximum()))
        if target == current:
            return

        self.scroll_animation = QPropertyAnimation(scrollbar, b"value", self)
        self.scroll_animation.setDuration(180)
        self.scroll_animation.setStartValue(current)
        self.scroll_animation.setEndValue(target)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scroll_animation.start()

    def _scroll_to_start(self) -> None:
        def reset_scroll() -> None:
            scrollbar = self.scroll_area.horizontalScrollBar()
            if self.scroll_animation:
                self.scroll_animation.stop()
            scrollbar.setValue(scrollbar.minimum())

        QTimer.singleShot(0, reset_scroll)
        QTimer.singleShot(25, reset_scroll)

    def _path_chain(self, selected_path: str) -> list[str]:
        if not selected_path or selected_path == self.root_path:
            return [self.root_path]

        normalized_root = self.root_path.rstrip("\\/")
        normalized_selected = selected_path.rstrip("\\/")
        if not normalized_selected.startswith(normalized_root):
            return [self.root_path]

        separator = "\\" if "\\" in normalized_selected else "/"
        relative = normalized_selected[len(normalized_root) :].strip("\\/")
        if not relative:
            return [self.root_path]

        chain = [self.root_path]
        current = normalized_root
        for part in relative.split(separator):
            current = f"{current}{separator}{part}"
            chain.append(current)
        return chain

    def _row_value(self, row: object, key: str) -> str:
        try:
            return str(row[key])  # type: ignore[index]
        except (AttributeError, IndexError, KeyError, TypeError):
            return str(getattr(row, key, ""))

    def _configure_folder_column(self, column: QListWidget) -> None:
        column.setIconSize(QSize(16, 16))
        column.setSpacing(2)

    def _root_entry_label(self) -> str:
        name = Path(self.root_path).name or self.root_path
        return f"[Root] {name}"

    def _folder_label(self, folder: object) -> str:
        name = self._row_value(folder, "name")
        match_count = self._row_value(folder, "match_count")
        if not match_count:
            return name
        return f"{name} ({match_count})"

    def _is_strict_ancestor(self, ancestor: str, path: str) -> bool:
        if not ancestor or not path or ancestor == path:
            return False

        separator = "\\" if "\\" in path else "/"
        normalized_ancestor = ancestor.rstrip("\\/")
        normalized_path = path.rstrip("\\/")
        return normalized_path.startswith(f"{normalized_ancestor}{separator}")
