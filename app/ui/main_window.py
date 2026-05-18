from __future__ import annotations

import json
import os
import time
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QCursor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QKeySequenceEdit,
    QSplitter,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.core.file_ops import copy_file_to_folder, delete_file, move_file_to_folder
from app.core.indexer import FileIndexer
from app.core.paths import settings_path
from app.core.scanner import FileScanner, ScanResult, normalize_path
from app.core.search import SearchService
from app.ui.column_view import ColumnView
from app.ui.file_table import FileTable


SETTINGS_PATH = settings_path()
SEARCH_MODE_DEBOUNCED = "debounced"
SEARCH_MODE_ENTER = "enter"
DEFAULT_SEARCH_MODE = SEARCH_MODE_ENTER
DEFAULT_DEBOUNCE_MS = 300
DEFAULT_RESULTS_PAGE_SIZE = 300
DEFAULT_THEME = "classic_dark"
THEMES = {
    "classic_dark": {
        "label": "Classic Dark (Default)",
        "background": "#1e1e1e",
        "surface": "#252526",
        "text": "#cccccc",
        "border": "#3c3c3c",
    },
    "light": {
        "label": "Light White",
        "background": "#ffffff",
        "surface": "#ffffff",
        "text": "#111111",
        "border": "#d0d7de",
    },
    "warm": {
        "label": "Warm Cream",
        "background": "#fff7ed",
        "surface": "#fffaf3",
        "text": "#1f1f1f",
        "border": "#ead6bd",
    },
    "mung_bean": {
        "label": "Mung Bean Green",
        "background": "#c7edcc",
        "surface": "#ddf4df",
        "text": "#1f2d1f",
        "border": "#9fc9a4",
    },
    "sakura": {
        "label": "Sakura Pink",
        "background": "#f8d7df",
        "surface": "#fde8ed",
        "text": "#2d1f25",
        "border": "#e5a8b8",
    },
    "cool": {
        "label": "Cool Blue",
        "background": "#eff6ff",
        "surface": "#f8fbff",
        "text": "#111827",
        "border": "#bfdbfe",
    },
    "gray": {
        "label": "Light Gray",
        "background": "#f3f4f6",
        "surface": "#ffffff",
        "text": "#111827",
        "border": "#d1d5db",
    },
    "dark": {
        "label": "Dark Slate",
        "background": "#1f2937",
        "surface": "#111827",
        "text": "#f9fafb",
        "border": "#4b5563",
    },
}
DEFAULT_KEY_BINDINGS = {
    "focus_search": "Ctrl+F",
    "clear_search": "Esc",
    "select_root": "Ctrl+O",
    "pin_folder": "Ctrl+P",
    "copy_file": "Ctrl+C",
    "cut_file": "Ctrl+X",
    "paste_file": "Ctrl+V",
    "delete_file": "Del",
    "scroll_folders_left": "A",
    "scroll_folders_right": "D",
    "scroll_files_up": "W",
    "scroll_files_down": "S",
}
KEY_BINDING_LABELS = {
    "focus_search": "Focus search box",
    "clear_search": "Clear search",
    "select_root": "Select root folder",
    "pin_folder": "Pin/unpin folder",
    "copy_file": "Copy selected file",
    "cut_file": "Cut selected file",
    "paste_file": "Paste into current folder",
    "delete_file": "Delete selected file",
    "scroll_folders_left": "Folder columns left",
    "scroll_folders_right": "Folder columns right",
    "scroll_files_up": "Hovered area up",
    "scroll_files_down": "Hovered area down",
}


def _normalize_key_sequence(value: object) -> str:
    sequence = QKeySequence(str(value or ""))
    normalized = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    if normalized == "Backspace":
        return ""
    return normalized


class SearchSettingsDialog(QDialog):
    def __init__(
        self,
        search_mode: str,
        debounce_ms: int,
        results_page_size: int,
        show_folder_match_counts: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Search Settings")

        self.mode_input = QComboBox()
        self.mode_input.addItem("Search while typing (debounced)", SEARCH_MODE_DEBOUNCED)
        self.mode_input.addItem("Search when pressing Enter", SEARCH_MODE_ENTER)
        self.mode_input.setCurrentIndex(
            self.mode_input.findData(search_mode)
            if self.mode_input.findData(search_mode) >= 0
            else self.mode_input.findData(DEFAULT_SEARCH_MODE)
        )

        self.debounce_input = QSpinBox()
        self.debounce_input.setRange(50, 5000)
        self.debounce_input.setSingleStep(50)
        self.debounce_input.setSuffix(" ms")
        self.debounce_input.setValue(debounce_ms)

        self.results_page_size_input = QSpinBox()
        self.results_page_size_input.setRange(50, 5000)
        self.results_page_size_input.setSingleStep(50)
        self.results_page_size_input.setSuffix(" results")
        self.results_page_size_input.setValue(results_page_size)

        self.show_folder_match_counts_input = QCheckBox("Show matching file counts beside folders")
        self.show_folder_match_counts_input.setChecked(show_folder_match_counts)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow("Search mode", self.mode_input)
        layout.addRow("Debounce delay", self.debounce_input)
        layout.addRow("Results per page", self.results_page_size_input)
        layout.addRow("Folder counts", self.show_folder_match_counts_input)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, int, int, bool]:
        return (
            str(self.mode_input.currentData()),
            int(self.debounce_input.value()),
            int(self.results_page_size_input.value()),
            self.show_folder_match_counts_input.isChecked(),
        )


class ThemeSettingsDialog(QDialog):
    preview_requested = Signal(str)

    def __init__(self, theme_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Theme Settings")
        self.resize(420, 360)

        self.theme_list = QListWidget()
        self.theme_list.setMinimumHeight(240)
        for theme_id, theme in THEMES.items():
            item = QListWidgetItem(theme["label"])
            item.setData(Qt.ItemDataRole.UserRole, theme_id)
            self.theme_list.addItem(item)
            if theme_id == theme_name:
                self.theme_list.setCurrentItem(item)
        if self.theme_list.currentItem() is None:
            self._select_theme(DEFAULT_THEME)
        self.theme_list.currentItemChanged.connect(self._handle_theme_changed)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        default_button = buttons.addButton("Default", QDialogButtonBox.ButtonRole.ResetRole)
        default_button.clicked.connect(self._select_default_theme)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow("Background theme", self.theme_list)
        layout.addWidget(buttons)

    def value(self) -> str:
        item = self.theme_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else DEFAULT_THEME

    def _select_default_theme(self) -> None:
        self._select_theme(DEFAULT_THEME)

    def _select_theme(self, theme_name: str) -> None:
        for row_index in range(self.theme_list.count()):
            item = self.theme_list.item(row_index)
            if item.data(Qt.ItemDataRole.UserRole) == theme_name:
                self.theme_list.setCurrentItem(item)
                return

    def _handle_theme_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is not None:
            self.preview_requested.emit(str(current.data(Qt.ItemDataRole.UserRole)))


class ShortcutKeySequenceEdit(QKeySequenceEdit):
    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Backspace:
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


class KeyboardSettingsDialog(QDialog):
    def __init__(self, key_bindings: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.inputs: dict[str, QKeySequenceEdit] = {}

        layout = QFormLayout(self)
        for action_id, label in KEY_BINDING_LABELS.items():
            editor = ShortcutKeySequenceEdit(QKeySequence(key_bindings.get(action_id, "")))
            self.inputs[action_id] = editor
            layout.addRow(label, editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        reset_button = buttons.addButton("Reset Defaults", QDialogButtonBox.ButtonRole.ResetRole)
        reset_button.clicked.connect(self._reset_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {
            action_id: _normalize_key_sequence(editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
            for action_id, editor in self.inputs.items()
        }

    def accept(self) -> None:
        duplicate_shortcut = self._duplicate_shortcut()
        if duplicate_shortcut:
            QMessageBox.warning(
                self,
                "Shortcut Conflict",
                f"'{duplicate_shortcut}' is assigned to more than one action.\n\n"
                "Please choose a different shortcut or clear one of the bindings.",
            )
            return

        super().accept()

    def _reset_defaults(self) -> None:
        for action_id, editor in self.inputs.items():
            editor.setKeySequence(QKeySequence(DEFAULT_KEY_BINDINGS[action_id]))

    def _duplicate_shortcut(self) -> str:
        seen: set[str] = set()
        for shortcut in self.values().values():
            if not shortcut:
                continue
            if shortcut in seen:
                return shortcut
            seen.add(shortcut)
        return ""


class ScanWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, root_path: str, indexer: FileIndexer) -> None:
        super().__init__()
        self.root_path = root_path
        self.indexer = indexer
        self.scanner = FileScanner()

    @Slot()
    def run(self) -> None:
        try:
            result = self.scanner.scan(self.root_path, self.progress.emit)
            self.indexer.replace_index(result.files, result.folders)
            self.finished.emit(result)
        except Exception as exc:  # Keep worker errors visible instead of killing the GUI thread.
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Resource Manager")

        self.app_settings = self._load_settings()
        self.search_mode = self._normalize_search_mode(
            self.app_settings.get("search_mode", DEFAULT_SEARCH_MODE)
        )
        self.debounce_ms = self._normalize_debounce_ms(
            self.app_settings.get("debounce_ms", DEFAULT_DEBOUNCE_MS)
        )
        self.results_page_size = self._normalize_results_page_size(
            self.app_settings.get("results_page_size", DEFAULT_RESULTS_PAGE_SIZE)
        )
        self.show_folder_match_counts = bool(
            self.app_settings.get("show_folder_match_counts", True)
        )
        self.theme_name = self._normalize_theme_name(self.app_settings.get("theme", DEFAULT_THEME))
        self.keyboard_mode_enabled = bool(self.app_settings.get("keyboard_mode_enabled", False))
        self.key_bindings = self._load_key_bindings()
        self.active_search_query = ""
        self.indexer = FileIndexer()
        self.search_service = SearchService(self.indexer)
        self.root_path = ""
        self.selected_folder = ""
        self.pinned_folder_path = ""
        self.search_result_offset = 0
        self.search_result_total = 0
        self.clipboard_operation = ""
        self.clipboard_paths: list[str] = []
        self.hover_scroll_animation: QPropertyAnimation | None = None
        self.scan_thread: QThread | None = None
        self.scan_worker: ScanWorker | None = None
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.last_search_elapsed_ms: float | None = None

        self.select_root_button = QPushButton("Select Root Folder")
        self.pin_folder_button = QPushButton("Pin/Unpin Folder")
        self.pin_folder_button.setCheckable(True)
        self.keyboard_mode_button = QPushButton()
        self.keyboard_mode_button.setCheckable(True)
        self.keyboard_mode_button.setChecked(self.keyboard_mode_enabled)
        self.previous_results_button = QPushButton("Previous")
        self.next_results_button = QPushButton("Next")
        self.results_page_label = QLabel("")
        self.scope_label = QLabel("Scope: Root")
        self.search_status_label = QLabel("")
        self.root_label = QLabel("No root selected")
        self.search_input = QLineEdit()
        self._update_search_placeholder()
        self.column_view = ColumnView(self._load_child_folders)
        self.file_table = FileTable()
        self._apply_shortcut_labels()
        self.status = QStatusBar()

        self._build_ui()
        self._connect_signals()
        self._apply_theme()
        self._load_last_root_if_available()

    def _build_ui(self) -> None:
        self._build_menu()
        for button in (
            self.select_root_button,
            self.pin_folder_button,
            self.keyboard_mode_button,
            self.previous_results_button,
            self.next_results_button,
        ):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.select_root_button)
        toolbar.addWidget(self.pin_folder_button)
        toolbar.addWidget(self.keyboard_mode_button)
        toolbar.addWidget(self.scope_label)
        toolbar.addWidget(self.search_input, stretch=1)
        toolbar.addWidget(self.previous_results_button)
        toolbar.addWidget(self.next_results_button)
        toolbar.addWidget(self.results_page_label)

        splitter = QSplitter()
        splitter.addWidget(self.column_view)
        splitter.addWidget(self.file_table)
        splitter.setSizes([700, 500])

        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(splitter, stretch=1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.setStatusBar(self.status)
        self.status.addWidget(self.root_label, stretch=1)
        self.status.addPermanentWidget(self.search_status_label)
        self._apply_tooltip_show_delay()
        self.status.showMessage("Choose a root folder to scan.")

    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Settings")
        search_settings_action = settings_menu.addAction("Search Settings...")
        search_settings_action.triggered.connect(self._open_search_settings)
        theme_settings_action = settings_menu.addAction("Theme Settings...")
        theme_settings_action.triggered.connect(self._open_theme_settings)
        keyboard_settings_action = settings_menu.addAction("Keyboard Shortcuts...")
        keyboard_settings_action.triggered.connect(self._open_keyboard_settings)

    def _connect_signals(self) -> None:
        self.select_root_button.clicked.connect(self.select_root_folder)
        self.pin_folder_button.clicked.connect(self._on_pin_folder_button_clicked)
        self.keyboard_mode_button.toggled.connect(self._set_keyboard_mode_enabled)
        self.previous_results_button.clicked.connect(self._show_previous_results_page)
        self.next_results_button.clicked.connect(self._show_next_results_page)
        self.search_input.textChanged.connect(self._handle_search_changed)
        self.search_input.returnPressed.connect(self._apply_search_from_enter)
        self.column_view.folder_selected.connect(self._handle_folder_selected)
        self.file_table.add_file_requested.connect(self._add_file_to_selected_folder)
        self.file_table.copy_requested.connect(lambda paths: self._set_clipboard("copy", paths))
        self.file_table.cut_requested.connect(lambda paths: self._set_clipboard("cut", paths))
        self.file_table.delete_requested.connect(self._delete_selected_files)
        self.file_table.folder_open_requested.connect(self._navigate_to_folder)
        self.file_table.paste_requested.connect(self._paste_into_selected_folder)
        self.search_timer.timeout.connect(self._apply_search_from_input)
        QApplication.instance().installEventFilter(self)
        self._update_scope_controls()
        self._update_pagination_controls()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            self._clear_search_focus_on_external_click(watched)
            return super().eventFilter(watched, event)

        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)
        if QApplication.activeModalWidget() is not None:
            return super().eventFilter(watched, event)

        physical_action_id = self._keyboard_mode_physical_action(event)
        if physical_action_id:
            handled = self._run_keyboard_mode_navigation(
                physical_action_id,
                event.isAutoRepeat(),
            )
            if handled:
                event.accept()
                return True

        shortcut = QKeySequence(event.keyCombination()).toString(
            QKeySequence.SequenceFormat.PortableText
        )
        action_id = self._action_for_shortcut(shortcut)
        if not action_id:
            return super().eventFilter(watched, event)

        if self._text_input_has_focus() and action_id not in {"focus_search", "clear_search"}:
            return super().eventFilter(watched, event)

        handled = self._run_shortcut_action(action_id, event.isAutoRepeat())
        return handled or super().eventFilter(watched, event)

    def _keyboard_mode_physical_action(self, event: QEvent) -> str:
        if not self.keyboard_mode_enabled or self._text_input_has_focus():
            return ""
        if event.modifiers() != Qt.KeyboardModifier.NoModifier:  # type: ignore[attr-defined]
            return ""

        key_to_action = {
            Qt.Key.Key_A: "scroll_folders_left",
            Qt.Key.Key_D: "scroll_folders_right",
            Qt.Key.Key_W: "scroll_files_up",
            Qt.Key.Key_S: "scroll_files_down",
        }
        return key_to_action.get(event.key(), "")  # type: ignore[attr-defined]

    def _clear_search_focus_on_external_click(self, watched: QObject) -> None:
        if QApplication.activeModalWidget() is not None:
            return
        if not self.search_input.hasFocus():
            return
        if watched is self.search_input:
            return
        if isinstance(watched, QWidget) and self.search_input.isAncestorOf(watched):
            return

        self.search_input.clearFocus()

    @Slot()
    def select_root_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select Root Folder")
        if selected:
            self.start_scan(selected)

    def _action_for_shortcut(self, shortcut: str) -> str:
        normalized = _normalize_key_sequence(shortcut)
        for action_id, binding in self.key_bindings.items():
            if binding and binding == normalized:
                return action_id
        return ""

    def _run_shortcut_action(self, action_id: str, is_auto_repeat: bool = False) -> bool:
        if self.keyboard_mode_enabled and action_id in {
            "scroll_folders_left",
            "scroll_folders_right",
            "scroll_files_up",
            "scroll_files_down",
        }:
            return self._run_keyboard_mode_navigation(action_id, is_auto_repeat)

        actions = {
            "focus_search": self._focus_search_box,
            "clear_search": self._clear_search,
            "select_root": self.select_root_folder,
            "pin_folder": self._toggle_pin_folder,
            "copy_file": self._copy_selected_file,
            "cut_file": self._cut_selected_file,
            "paste_file": self._paste_into_selected_folder,
            "delete_file": self._delete_selected_file_from_shortcut,
            "scroll_folders_left": self.column_view.scroll_one_column_left,
            "scroll_folders_right": self.column_view.scroll_one_column_right,
            "scroll_files_up": lambda: self._scroll_hovered_area_vertically(-1),
            "scroll_files_down": lambda: self._scroll_hovered_area_vertically(1),
        }
        action = actions.get(action_id)
        if not action:
            return False
        action()
        return True

    def _run_keyboard_mode_navigation(self, action_id: str, is_auto_repeat: bool) -> bool:
        if action_id == "scroll_folders_left":
            moved = self.column_view.leave_current_folder()
        elif action_id == "scroll_folders_right":
            moved = self.column_view.enter_selected_folder()
        elif action_id == "scroll_files_up":
            moved = self.column_view.select_previous_folder(
                animate_child_preview=not is_auto_repeat
            )
        elif action_id == "scroll_files_down":
            moved = self.column_view.select_next_folder(
                animate_child_preview=not is_auto_repeat
            )
        else:
            return False

        if not moved:
            self.status.showMessage("No folder to select in that direction.")
        return True

    @Slot(bool)
    def _set_keyboard_mode_enabled(self, enabled: bool) -> None:
        self.keyboard_mode_enabled = enabled
        self._update_keyboard_mode_button()
        self._save_settings()
        if enabled:
            self.column_view.ensure_keyboard_selection()
            self.status.showMessage("Keyboard Mode enabled. Use W/S to select folders, A/D to change levels.")
        else:
            self.status.showMessage("Keyboard Mode disabled. WASD scrolling restored.")

    def _scroll_hovered_area_vertically(self, direction: int) -> None:
        scroll_area = self._hovered_scroll_area()
        if scroll_area is None:
            return

        scrollbar = scroll_area.verticalScrollBar()
        if scrollbar.maximum() <= scrollbar.minimum():
            return

        step = max(1, scrollbar.pageStep() // 3)
        target = scrollbar.value() + (step * direction)
        target = max(scrollbar.minimum(), min(target, scrollbar.maximum()))
        if target == scrollbar.value():
            return

        self.hover_scroll_animation = QPropertyAnimation(scrollbar, b"value", self)
        self.hover_scroll_animation.setDuration(120)
        self.hover_scroll_animation.setStartValue(scrollbar.value())
        self.hover_scroll_animation.setEndValue(target)
        self.hover_scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_scroll_animation.start()

    def _hovered_scroll_area(self) -> QAbstractScrollArea | None:
        widget = QApplication.widgetAt(QCursor.pos())
        while widget is not None:
            if isinstance(widget, QAbstractScrollArea):
                return widget
            widget = widget.parentWidget()
        return None

    def _focus_search_box(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _clear_search(self) -> None:
        if self.search_input.hasFocus():
            self.search_input.clearFocus()
            self.status.showMessage("Search input focus cleared.")
            return

        self.search_input.clear()
        self._apply_search("")

    def _copy_selected_file(self) -> None:
        paths = self.file_table.selected_file_paths()
        self._set_clipboard("copy", paths)

    def _cut_selected_file(self) -> None:
        paths = self.file_table.selected_file_paths()
        self._set_clipboard("cut", paths)

    def _delete_selected_file_from_shortcut(self) -> None:
        self._delete_selected_files(self.file_table.selected_file_paths())

    def _selected_file_path_for_shortcut(self) -> str:
        if self.file_table.selected_result_type() != "File":
            self.status.showMessage("Select a file first.")
            return ""
        path = self.file_table.selected_path()
        if not path:
            self.status.showMessage("Select a file first.")
        return path

    def _text_input_has_focus(self) -> bool:
        return isinstance(self.focusWidget(), QLineEdit)

    def start_scan(self, root_path: str) -> None:
        if self.scan_thread is not None:
            return

        normalized_root = normalize_path(root_path)
        self.select_root_button.setEnabled(False)
        self.search_input.setEnabled(False)
        self.status.showMessage(f"Scanning {normalized_root} ...")

        thread = QThread(self)
        worker = ScanWorker(normalized_root, self.indexer)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._handle_scan_progress)
        worker.finished.connect(self._handle_scan_finished)
        worker.failed.connect(self._handle_scan_failed)
        worker.finished.connect(lambda _result: thread.quit())
        worker.failed.connect(lambda _message: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_scan_thread)

        self.scan_thread = thread
        self.scan_worker = worker
        thread.start()

    @Slot(int, int)
    def _handle_scan_progress(self, file_count: int, folder_count: int) -> None:
        self.status.showMessage(
            f"Scanning ... {file_count:,} files, {folder_count:,} folders indexed in memory"
        )

    @Slot(object)
    def _handle_scan_finished(self, result: ScanResult) -> None:
        self.search_service.clear_cache()
        self.root_path = result.root_path
        self.selected_folder = result.root_path
        self.pinned_folder_path = ""
        self.root_label.setText(result.root_path)
        self._save_settings()
        self.column_view.set_root(result.root_path)
        if self.keyboard_mode_enabled:
            self.column_view.ensure_keyboard_selection()
        self._refresh_files()
        self._update_scope_controls()

        message = (
            f"Scan complete: {len(result.files):,} files, "
            f"{len(result.folders):,} folders in {result.elapsed_seconds:.2f}s"
        )
        if result.errors:
            message += f" ({len(result.errors):,} skipped)"
        self.status.showMessage(message)

    @Slot(str)
    def _handle_scan_failed(self, message: str) -> None:
        self.status.showMessage(f"Scan failed: {message}")

    @Slot()
    def _cleanup_scan_thread(self) -> None:
        self.scan_thread = None
        self.scan_worker = None
        self.select_root_button.setEnabled(True)
        self.search_input.setEnabled(True)
        self._update_scope_controls()

    @Slot(str)
    def _handle_search_changed(self, _query: str) -> None:
        if not self.root_path:
            return

        if self.search_mode == SEARCH_MODE_DEBOUNCED:
            self.search_timer.start(self.debounce_ms)

    @Slot()
    def _apply_search_from_input(self) -> None:
        self._apply_search(self.search_input.text())

    @Slot()
    def _apply_search_from_enter(self) -> None:
        self._apply_search_from_input()
        if self.keyboard_mode_enabled:
            self.search_input.clearFocus()

    def _apply_search(self, query: str, show_status: bool = True) -> None:
        if not self.root_path:
            return

        self.search_timer.stop()
        self.active_search_query = query
        self.search_result_offset = 0
        self.column_view.set_search_query(self.active_search_query)
        started = time.perf_counter()
        self._refresh_files()
        if self.active_search_query.strip():
            self.last_search_elapsed_ms = (time.perf_counter() - started) * 1000
        else:
            self.last_search_elapsed_ms = None
        self._update_search_status_label()

    @Slot(str)
    def _handle_folder_selected(self, folder_path: str) -> None:
        self.selected_folder = folder_path
        self.search_result_offset = 0
        self._refresh_files()
        self._update_scope_controls()

    def _refresh_files(self) -> None:
        if not self.selected_folder:
            self.file_table.set_files([])
            self.search_result_total = 0
            self._update_pagination_controls()
            return

        if self.active_search_query.strip():
            results, total = self.search_service.results_in_folder_tree(
                self.selected_folder,
                self.active_search_query,
                self.results_page_size,
                self.search_result_offset,
            )
            self.search_result_total = total
            self.file_table.set_results(results)
        else:
            self.search_result_total = 0
            files = self.search_service.files_in_folder(self.selected_folder)
            self.file_table.set_files(files)
        self._update_pagination_controls()

    @Slot()
    def _show_previous_results_page(self) -> None:
        if self.search_result_offset <= 0:
            return

        self.search_result_offset = max(0, self.search_result_offset - self.results_page_size)
        self._refresh_files()

    @Slot()
    def _show_next_results_page(self) -> None:
        next_offset = self.search_result_offset + self.results_page_size
        if next_offset >= self.search_result_total:
            return

        self.search_result_offset = next_offset
        self._refresh_files()

    def _load_child_folders(self, parent_path: str, query: str) -> list[object]:
        if not self.pinned_folder_path:
            return self.search_service.child_folders(
                parent_path,
                query,
                self.show_folder_match_counts,
            )

        if self._is_strict_ancestor(parent_path, self.pinned_folder_path):
            children = self.search_service.child_folders(parent_path, "")
            filtered_children = [
                child
                for child in children
                if self._is_same_or_descendant(self.pinned_folder_path, str(child["path"]))
            ]
            return self._with_folder_match_counts(filtered_children, query)

        if self._is_same_or_descendant(parent_path, self.pinned_folder_path):
            return self.search_service.child_folders(
                parent_path,
                query,
                self.show_folder_match_counts,
            )

        return []

    def _toggle_pin_folder(self) -> None:
        if self.pinned_folder_path:
            self._unpin_folder()
        else:
            self._pin_selected_folder()

    @Slot(bool)
    def _on_pin_folder_button_clicked(self, checked: bool) -> None:
        if checked:
            before = self.pinned_folder_path
            self._pin_selected_folder()
            if self.pinned_folder_path == before:
                self.pin_folder_button.blockSignals(True)
                self.pin_folder_button.setChecked(False)
                self.pin_folder_button.blockSignals(False)
        else:
            self._unpin_folder()

    @Slot()
    def _pin_selected_folder(self) -> None:
        if not self.root_path or not self.selected_folder:
            self.status.showMessage("Select a folder before pinning.")
            return

        self.pinned_folder_path = self.selected_folder
        self.search_result_offset = 0
        self.column_view.set_pinned_path(self.pinned_folder_path)
        self.column_view.rebuild_to_path(self.selected_folder)
        self._refresh_files()
        self._update_scope_controls()
        self.status.showMessage(f"Pinned search scope: {self.pinned_folder_path}")

    @Slot()
    def _unpin_folder(self) -> None:
        if not self.root_path:
            return

        self.pinned_folder_path = ""
        self.search_result_offset = 0
        self.column_view.set_pinned_path("")
        self.column_view.rebuild_to_path(self.selected_folder)
        self._refresh_files()
        self._update_scope_controls()
        self.status.showMessage("Search scope restored to root.")

    @Slot(str)
    def _navigate_to_folder(self, folder_path: str) -> None:
        if not self.root_path:
            return

        self.selected_folder = folder_path
        self.search_result_offset = 0
        self.column_view.rebuild_to_path(folder_path)
        self._refresh_files()
        self._update_scope_controls()
        self.status.showMessage(f"Opened folder: {folder_path}")

    def _set_clipboard(self, operation: str, paths: list[str]) -> None:
        if not paths:
            self.status.showMessage("Select one or more files first.")
            return

        self.clipboard_operation = operation
        self.clipboard_paths = paths
        label = "Copied" if operation == "copy" else "Cut"
        if len(paths) == 1:
            self.status.showMessage(f"{label}: {Path(paths[0]).name}")
        else:
            self.status.showMessage(f"{label}: {len(paths)} files")

    @Slot(list)
    def _delete_selected_files(self, paths: list[str]) -> None:
        if not paths:
            self.status.showMessage("Select one or more files first.")
            return

        message = (
            f"Delete {len(paths)} files permanently?"
            if len(paths) > 1
            else f"Delete this file permanently?\n\n{paths[0]}"
        )
        response = QMessageBox.question(
            self,
            "Delete Files" if len(paths) > 1 else "Delete File",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        failures: list[tuple[str, str]] = []
        deleted_count = 0
        for path in paths:
            try:
                delete_file(path)
                self.indexer.delete_file(path)
                deleted_count += 1
            except OSError as exc:
                failures.append((path, str(exc)))

        self._refresh_after_file_change()
        self._show_batch_result("Delete", deleted_count, failures)

    @Slot()
    def _add_file_to_selected_folder(self) -> None:
        if not self.selected_folder:
            self.status.showMessage("Select a folder before adding a file.")
            return

        source_path, _filter = QFileDialog.getOpenFileName(self, "Add File")
        if not source_path:
            return

        try:
            file_record = copy_file_to_folder(source_path, self.selected_folder)
            self.indexer.upsert_file(file_record)
            self._refresh_after_file_change()
            self.status.showMessage(f"Added: {file_record.name}")
        except OSError as exc:
            self._show_error("Add File Failed", str(exc))

    @Slot()
    def _paste_into_selected_folder(self) -> None:
        if not self.selected_folder:
            self.status.showMessage("Select a folder before pasting.")
            return
        if not self.clipboard_operation or not self.clipboard_paths:
            self.status.showMessage("Nothing to paste.")
            return

        failures: list[tuple[str, str]] = []
        completed_count = 0
        for source_path in list(self.clipboard_paths):
            source = Path(source_path)
            try:
                if not source.exists():
                    raise FileNotFoundError("Clipboard file no longer exists.")
                if self.clipboard_operation == "copy":
                    file_record = copy_file_to_folder(source, self.selected_folder)
                    self.indexer.upsert_file(file_record)
                    completed_count += 1
                elif self.clipboard_operation == "cut":
                    if source.parent.resolve() == Path(self.selected_folder).resolve():
                        raise OSError("File is already in the selected folder.")
                    old_path = str(source.resolve())
                    file_record = move_file_to_folder(source, self.selected_folder)
                    self.indexer.move_file_record(old_path, file_record)
                    completed_count += 1
                else:
                    raise OSError("Unsupported clipboard operation.")
            except OSError as exc:
                failures.append((source_path, str(exc)))

        operation = "Copy" if self.clipboard_operation == "copy" else "Move"
        if self.clipboard_operation == "cut" and not failures:
            self.clipboard_operation = ""
            self.clipboard_paths = []
        elif self.clipboard_operation == "cut":
            self.clipboard_paths = [path for path, _message in failures]

        self._refresh_after_file_change()
        self._show_batch_result(operation, completed_count, failures)

    def _refresh_after_file_change(self) -> None:
        self.search_service.clear_cache()
        if self.root_path:
            self.column_view.set_search_query(self.active_search_query)
        self._refresh_files()

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)
        self.status.showMessage(message)

    def _show_batch_result(
        self,
        operation: str,
        completed_count: int,
        failures: list[tuple[str, str]],
    ) -> None:
        if not failures:
            self.status.showMessage(f"{operation} complete: {completed_count} files")
            return

        failed_count = len(failures)
        shown_failures = failures[:10]
        details = "\n".join(
            f"- {Path(path).name}: {message}"
            for path, message in shown_failures
        )
        if failed_count > len(shown_failures):
            details += f"\n... and {failed_count - len(shown_failures)} more"

        QMessageBox.warning(
            self,
            f"{operation} Partially Failed",
            (
                f"{operation} complete: {completed_count} files\n"
                f"Failed: {failed_count} files\n\n"
                f"{details}"
            ),
        )
        self.status.showMessage(
            f"{operation} complete: {completed_count}, failed: {failed_count}"
        )

    @Slot()
    def _open_search_settings(self) -> None:
        dialog = SearchSettingsDialog(
            self.search_mode,
            self.debounce_ms,
            self.results_page_size,
            self.show_folder_match_counts,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        (
            self.search_mode,
            self.debounce_ms,
            self.results_page_size,
            self.show_folder_match_counts,
        ) = dialog.values()
        self.search_mode = self._normalize_search_mode(self.search_mode)
        self.debounce_ms = self._normalize_debounce_ms(self.debounce_ms)
        self.results_page_size = self._normalize_results_page_size(self.results_page_size)
        self.search_result_offset = 0
        self._update_search_placeholder()
        self._save_settings()
        self.column_view.set_search_query(self.active_search_query)
        self._refresh_files()

        if self.search_mode == SEARCH_MODE_DEBOUNCED:
            self.status.showMessage(f"Search while typing enabled ({self.debounce_ms} ms).")
            if self.root_path:
                self.search_timer.start(self.debounce_ms)
        else:
            self.search_timer.stop()
            self.status.showMessage("Enter search enabled. Press Enter to apply search text.")

    @Slot()
    def _open_theme_settings(self) -> None:
        original_theme_name = self.theme_name
        dialog = ThemeSettingsDialog(self.theme_name, self)
        dialog.preview_requested.connect(self._preview_theme)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.theme_name = original_theme_name
            self._apply_theme()
            self.status.showMessage("Theme preview canceled.")
            return

        self.theme_name = self._normalize_theme_name(dialog.value())
        self._apply_theme()
        self._save_settings()
        self.status.showMessage(f"Theme applied: {THEMES[self.theme_name]['label']}")

    @Slot(str)
    def _preview_theme(self, theme_name: str) -> None:
        self.theme_name = self._normalize_theme_name(theme_name)
        self._apply_theme()
        self.status.showMessage(f"Previewing theme: {THEMES[self.theme_name]['label']}")

    @Slot()
    def _open_keyboard_settings(self) -> None:
        dialog = KeyboardSettingsDialog(self.key_bindings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.key_bindings = self._normalize_key_bindings(dialog.values())
        self._apply_shortcut_labels()
        self._save_settings()
        self.status.showMessage("Keyboard shortcuts saved.")

    def _load_last_root_if_available(self) -> None:
        last_root = str(self.app_settings.get("last_root", "") or "")
        if not last_root:
            return

        self.root_label.setText(last_root)
        if Path(last_root).exists() and self.indexer.get_file_count() > 0:
            self.root_path = last_root
            self.selected_folder = last_root
            self.column_view.set_root(last_root)
            self.column_view.set_pinned_path("")
            if self.keyboard_mode_enabled:
                self.column_view.ensure_keyboard_selection()
            self._refresh_files()
            self._update_scope_controls()
            self.status.showMessage("Loaded previous index. Select a folder to rescan.")

    def _load_settings(self) -> dict[str, object]:
        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as file:
                data = json.load(file)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self) -> None:
        self.app_settings["last_root"] = self.root_path
        self.app_settings["search_mode"] = self.search_mode
        self.app_settings["debounce_ms"] = self.debounce_ms
        self.app_settings["results_page_size"] = self.results_page_size
        self.app_settings["show_folder_match_counts"] = self.show_folder_match_counts
        self.app_settings["theme"] = self.theme_name
        self.app_settings["keyboard_mode_enabled"] = self.keyboard_mode_enabled
        self.app_settings["keyboard_shortcuts"] = self.key_bindings
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SETTINGS_PATH.open("w", encoding="utf-8") as file:
            json.dump(self.app_settings, file, indent=2)

    def _load_key_bindings(self) -> dict[str, str]:
        saved = self.app_settings.get("keyboard_shortcuts", {})
        if not isinstance(saved, dict):
            saved = {}
        return self._normalize_key_bindings(saved)

    def _normalize_key_bindings(self, bindings: dict[object, object]) -> dict[str, str]:
        normalized = {}
        for action_id, default_shortcut in DEFAULT_KEY_BINDINGS.items():
            if action_id in bindings:
                normalized[action_id] = _normalize_key_sequence(bindings[action_id])
            else:
                normalized[action_id] = default_shortcut
        return normalized

    def _shortcut_label(self, action_id: str) -> str:
        return self.key_bindings.get(action_id, "")

    def _apply_shortcut_labels(self) -> None:
        self.select_root_button.setText("Select Root Folder")
        self._set_button_shortcut_tooltip(self.select_root_button, "select_root")
        self.pin_folder_button.setText("Pin/Unpin Folder")
        self._set_button_shortcut_tooltip(self.pin_folder_button, "pin_folder")
        self._update_keyboard_mode_button()
        self.file_table.set_shortcut_labels(self.key_bindings)
        self._update_search_placeholder()

    def _set_button_shortcut_tooltip(self, button: QPushButton, action_id: str) -> None:
        description = KEY_BINDING_LABELS.get(action_id, "")
        shortcut = self._shortcut_label(action_id)
        if description and shortcut:
            button.setToolTip(f"{description} ({shortcut})")
        elif shortcut:
            button.setToolTip(shortcut)
        elif description:
            button.setToolTip(description)
        else:
            button.setToolTip("")

    def _apply_tooltip_show_delay(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        hints = app.styleHints()
        setter = getattr(hints, "setToolTipShowDelay", None)
        if callable(setter):
            setter(800)

    def _update_search_status_label(self) -> None:
        if self.active_search_query.strip():
            text = f"Search applied: {self.active_search_query}"
            if self.last_search_elapsed_ms is not None:
                text += f" · {self.last_search_elapsed_ms:.1f} ms"
            self.search_status_label.setText(text)
            return

        self.search_status_label.setText("")

    def _update_keyboard_mode_button(self) -> None:
        state = "On" if self.keyboard_mode_enabled else "Off"
        self.keyboard_mode_button.setText(f"Keyboard Mode: {state}")

    def _normalize_theme_name(self, value: object) -> str:
        theme_name = str(value or "")
        return theme_name if theme_name in THEMES else DEFAULT_THEME

    def _apply_theme(self) -> None:
        theme = THEMES[self.theme_name]
        app = QApplication.instance()
        if app is None:
            return

        app.setStyleSheet(
            f"""
            QWidget {{
                background: {theme["background"]};
                color: {theme["text"]};
            }}

            QMenuBar,
            QMenu,
            QStatusBar,
            QDialog {{
                background: {theme["background"]};
                color: {theme["text"]};
            }}

            QMenu::item {{
                padding: 6px 28px 6px 12px;
                background: transparent;
            }}

            QMenu::item:selected,
            QMenu::item:hover {{
                background: #cfe8ff;
                color: #111111;
            }}

            QMenu::separator {{
                height: 1px;
                background: {theme["border"]};
                margin: 4px 8px;
            }}

            QPushButton,
            QLineEdit,
            QComboBox,
            QSpinBox,
            QKeySequenceEdit {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: 1px solid {theme["border"]};
                border-radius: 4px;
                padding: 4px;
            }}

            QPushButton:hover {{
                background: #dbeeff;
                color: #111111;
                border: 1px solid #7cb7e8;
            }}

            QPushButton:pressed,
            QPushButton:checked {{
                background: #b7dcff;
                color: #111111;
                border: 1px solid #4f9edb;
            }}

            QListWidget,
            QTableWidget,
            QHeaderView::section {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: 1px solid {theme["border"]};
            }}

            QListWidget::item:selected,
            QTableWidget::item:selected {{
                background: #cfe8ff;
                color: #111111;
            }}

            QListWidget::item:selected:active,
            QTableWidget::item:selected:active {{
                background: #b7dcff;
                color: #111111;
            }}

            QAbstractItemView {{
                outline: none;
            }}

            QListWidget,
            QListView,
            QTableWidget {{
                outline: none;
            }}

            QListWidget::item,
            QListWidget::item:selected,
            QListWidget::item:selected:!active,
            QListWidget::item:selected:active,
            QListWidget::item:!selected,
            QTableWidget::item,
            QTableWidget::item:selected,
            QTableWidget::item:selected:!active,
            QTableWidget::item:selected:active,
            QTableWidget::item:!selected {{
                border: none;
                outline: none;
            }}

            QListWidget::item:focus,
            QListWidget::item:hover,
            QListWidget::item:!active:focus,
            QTableWidget::item:focus,
            QTableWidget::item:hover {{
                border: none;
                outline: none;
            }}

            QScrollBar:vertical {{
                width: 12px;
                margin: 0;
                background: {theme["background"]};
            }}

            QScrollBar:horizontal {{
                height: 12px;
                margin: 0;
                background: {theme["background"]};
            }}

            QScrollBar::handle:vertical,
            QScrollBar::handle:horizontal {{
                background: {theme["border"]};
                border-radius: 4px;
                min-height: 24px;
            }}

            QScrollBar::handle:hover {{
                background: #888888;
            }}

            QScrollBar::add-line,
            QScrollBar::sub-line {{
                width: 0;
                height: 0;
            }}

            QScrollBar::add-page,
            QScrollBar::sub-page {{
                background: transparent;
            }}
            """
        )

    def _normalize_search_mode(self, value: object) -> str:
        if value == SEARCH_MODE_ENTER:
            return SEARCH_MODE_ENTER
        if value == SEARCH_MODE_DEBOUNCED:
            return SEARCH_MODE_DEBOUNCED
        return DEFAULT_SEARCH_MODE

    def _normalize_debounce_ms(self, value: object) -> int:
        try:
            debounce_ms = int(value)
        except (TypeError, ValueError):
            return DEFAULT_DEBOUNCE_MS
        return min(max(debounce_ms, 50), 5000)

    def _normalize_results_page_size(self, value: object) -> int:
        try:
            results_page_size = int(value)
        except (TypeError, ValueError):
            return DEFAULT_RESULTS_PAGE_SIZE
        return min(max(results_page_size, 50), 5000)

    def _update_search_placeholder(self) -> None:
        hint = "Search name or extension, e.g. report, .csv, png"
        if self.search_mode == SEARCH_MODE_DEBOUNCED:
            self.search_input.setPlaceholderText(f"{hint} ({self.debounce_ms} ms debounce)")
        else:
            self.search_input.setPlaceholderText(f"{hint} (press Enter)")

    def _update_scope_controls(self) -> None:
        has_root = bool(self.root_path)
        has_selection = bool(self.selected_folder)
        is_pinned = bool(self.pinned_folder_path)
        can_pin = (
            has_root
            and has_selection
            and self.selected_folder != self.root_path
        )

        if is_pinned:
            self.pin_folder_button.setEnabled(has_root)
        else:
            self.pin_folder_button.setEnabled(can_pin)

        self.pin_folder_button.blockSignals(True)
        self.pin_folder_button.setChecked(is_pinned)
        self.pin_folder_button.blockSignals(False)

        if is_pinned:
            self.scope_label.setText(f"Scope: {Path(self.pinned_folder_path).name}")
        else:
            self.scope_label.setText("Scope: Root")

    def _update_pagination_controls(self) -> None:
        has_search = bool(self.active_search_query.strip())
        has_previous = has_search and self.search_result_offset > 0
        has_next = (
            has_search
            and self.search_result_offset + self.results_page_size < self.search_result_total
        )

        self.previous_results_button.setEnabled(has_previous)
        self.next_results_button.setEnabled(has_next)

        if not has_search or self.search_result_total == 0:
            self.results_page_label.setText("")
            return

        start = self.search_result_offset + 1
        end = min(self.search_result_offset + self.results_page_size, self.search_result_total)
        self.results_page_label.setText(f"{start:,}-{end:,} of {self.search_result_total:,}")

    def _with_folder_match_counts(self, folders: list[object], query: str) -> list[object]:
        if not self.show_folder_match_counts or not query.strip():
            return folders

        counts = self.search_service.folder_match_counts(query)
        return [
            {
                "path": folder["path"],  # type: ignore[index]
                "name": folder["name"],  # type: ignore[index]
                "parent_path": folder["parent_path"],  # type: ignore[index]
                "match_count": counts.get(str(folder["path"]), 0),  # type: ignore[index]
            }
            for folder in folders
        ]

    def _is_same_or_descendant(self, path: str, ancestor: str) -> bool:
        normalized_path = self._normalize_for_compare(path)
        normalized_ancestor = self._normalize_for_compare(ancestor)
        return normalized_path == normalized_ancestor or normalized_path.startswith(
            f"{normalized_ancestor}{os.sep}"
        )

    def _is_strict_ancestor(self, ancestor: str, path: str) -> bool:
        normalized_path = self._normalize_for_compare(path)
        normalized_ancestor = self._normalize_for_compare(ancestor)
        return normalized_path.startswith(f"{normalized_ancestor}{os.sep}")

    def _normalize_for_compare(self, path: str) -> str:
        return os.path.normcase(os.path.normpath(path))
