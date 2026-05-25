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
from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence
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

from app.core.bookmarks import BookmarkTab, load_bookmarks, save_bookmarks
from app.core.file_ops import copy_file_to_folder, delete_file, move_file_to_folder
from app.core.indexer import FileIndexer
from app.core.index_watcher import IndexWatcher
from app.core.paths import database_path_for_root, database_path, settings_path
from app.core.scanner import FileScanner, ScanCancelledError, ScanResult, normalize_path
from app.core.search import SearchService
from app.core.search_constants import (
    DEFAULT_SEARCH_SUBTREE_RESULTS,
    DEFAULT_SHOW_FOLDER_MATCH_COUNTS,
    DEFAULT_WATCH_INDEX_CHANGES,
    LARGE_INDEX_FILE_COUNT,
    MIN_SEARCH_QUERY_LENGTH,
)
from app.ui.bookmark_tab_bar import BookmarkTabBar
from app.ui.clipboard_paths import COPY_FULL_PATH_LABEL
from app.ui.column_view import ColumnView
from app.ui.file_table import FileTable
from app.ui.scan_control_buttons import ScanPlayButton, ScanStopButton
from app.ui.settings_constants import (
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_KEY_BINDINGS,
    DEFAULT_KEYBOARD_FOLDER_REFRESH,
    DEFAULT_RESULTS_PAGE_SIZE,
    DEFAULT_SEARCH_MODE,
    DEFAULT_SHOW_FILE_ICONS,
    DEFAULT_SHOW_FOLDER_ICONS,
    DEFAULT_THEME,
    KEY_BINDING_LABELS,
    KEYBOARD_FOLDER_REFRESH_IMMEDIATE,
    KEYBOARD_FOLDER_REFRESH_ON_ENTER,
    SEARCH_MODE_DEBOUNCED,
    SEARCH_MODE_ENTER,
    THEMES,
    normalize_custom_theme_colors,
    normalize_key_sequence,
    resolve_theme,
)
from app.ui.settings_dialog import SettingsDialog


SETTINGS_PATH = settings_path()


class ScanWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, root_path: str, indexer: FileIndexer) -> None:
        super().__init__()
        self.root_path = root_path
        self.indexer = indexer
        self.scanner = FileScanner()
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    @Slot()
    def run(self) -> None:
        try:
            result = self.scanner.scan(
                self.root_path,
                self.progress.emit,
                cancel_check=lambda: self._cancel_requested,
            )
            if self._cancel_requested:
                self.cancelled.emit()
                return
            self.indexer.replace_index(
                result.files,
                result.folders,
                cancel_check=lambda: self._cancel_requested,
            )
            if self._cancel_requested:
                self.cancelled.emit()
                return
            self.finished.emit(result)
        except ScanCancelledError:
            self.cancelled.emit()
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
            self.app_settings.get(
                "show_folder_match_counts",
                DEFAULT_SHOW_FOLDER_MATCH_COUNTS,
            )
        )
        self.watch_index_changes = bool(
            self.app_settings.get(
                "watch_index_changes",
                DEFAULT_WATCH_INDEX_CHANGES,
            )
        )
        self.search_subtree_results = bool(
            self.app_settings.get(
                "search_subtree_results",
                self.app_settings.get(
                    "global_search_results",
                    DEFAULT_SEARCH_SUBTREE_RESULTS,
                ),
            )
        )
        self.keyboard_folder_refresh = self._normalize_keyboard_folder_refresh(
            self.app_settings.get("keyboard_folder_refresh", DEFAULT_KEYBOARD_FOLDER_REFRESH)
        )
        self.theme_name = self._normalize_theme_name(self.app_settings.get("theme", DEFAULT_THEME))
        self.custom_theme_colors = normalize_custom_theme_colors(
            self.app_settings.get("custom_theme_colors")
        )
        self.show_file_icons = bool(
            self.app_settings.get("show_file_icons", DEFAULT_SHOW_FILE_ICONS)
        )
        self.show_folder_icons = bool(
            self.app_settings.get("show_folder_icons", DEFAULT_SHOW_FOLDER_ICONS)
        )
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
        self.index_watcher = IndexWatcher(self)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.last_search_elapsed_ms: float | None = None
        self.tabs: list[BookmarkTab] = []
        self.active_tab_index = -1
        self.active_tab_id = ""
        self._pending_tab_restore: BookmarkTab | None = None
        self._indexed_file_count = 0
        self._tab_activation_in_progress = False

        self.select_root_button = QPushButton("Select Root Folder")
        self.pin_folder_button = QPushButton("Pin/Unpin Folder")
        self.pin_folder_button.setCheckable(True)
        self.search_scope_button = QPushButton()
        self.search_scope_button.setCheckable(True)
        self.search_scope_button.setChecked(self.search_subtree_results)
        self.search_scope_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._update_search_scope_button()
        self.previous_results_button = QPushButton("Previous")
        self.next_results_button = QPushButton("Next")
        self.results_page_label = QLabel("")
        self.search_status_label = QLabel("")
        self.root_label = QLabel("No root selected")
        self.scan_play_button = ScanPlayButton()
        self.scan_stop_button = ScanStopButton()
        self.search_input = QLineEdit()
        self._update_search_placeholder()
        self.save_tab_button = QPushButton("☆")
        self.save_tab_button.setObjectName("saveTabButton")
        self.save_tab_button.setFixedWidth(32)
        self.save_tab_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.save_tab_button.setToolTip("Save current location to tabs (stored in bookmarks.json)")
        self.search_box_container = QWidget()
        search_box_layout = QHBoxLayout(self.search_box_container)
        search_box_layout.setContentsMargins(0, 0, 0, 0)
        search_box_layout.setSpacing(4)
        search_box_layout.addWidget(self.scan_play_button)
        search_box_layout.addWidget(self.scan_stop_button)
        search_box_layout.addWidget(self.search_input, stretch=1)
        search_box_layout.addWidget(self.save_tab_button)
        self.bookmark_tab_bar = BookmarkTabBar()
        self.column_view = ColumnView(self._load_child_folders)
        self.file_table = FileTable()
        self.column_view.set_show_folder_icons(self.show_folder_icons)
        self.file_table.set_show_file_icons(self.show_file_icons)
        self._apply_shortcut_labels()
        self.status = QStatusBar()

        self._build_ui()
        self._connect_signals()
        self._apply_theme()
        self._load_bookmarks()
        if self.tabs:
            self._sync_tab_bar()
            visible = self._visible_tabs()
            if visible and self.active_tab_id:
                visible_index = self._visible_index_for_id(self.active_tab_id)
                if visible_index >= 0:
                    self._activate_tab(visible_index, initial=True)
        else:
            self._load_last_root_if_available()
        self._update_scan_controls()

    def _build_ui(self) -> None:
        self._build_menu()
        for button in (
            self.select_root_button,
            self.pin_folder_button,
            self.search_scope_button,
            self.previous_results_button,
            self.next_results_button,
            self.save_tab_button,
            self.scan_play_button,
            self.scan_stop_button,
        ):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.select_root_button)
        toolbar.addWidget(self.pin_folder_button)
        toolbar.addWidget(self.search_scope_button)
        toolbar.addWidget(self.search_box_container, stretch=1)
        toolbar.addWidget(self.previous_results_button)
        toolbar.addWidget(self.next_results_button)
        toolbar.addWidget(self.results_page_label)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.column_view)
        splitter.addWidget(self.file_table)
        splitter.setSizes([700, 500])

        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(self.bookmark_tab_bar)
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
        settings_action = self.menuBar().addAction("Settings")
        settings_action.triggered.connect(self._open_settings)

    def _connect_signals(self) -> None:
        self.select_root_button.clicked.connect(self.select_root_folder)
        self.pin_folder_button.clicked.connect(self._on_pin_folder_button_clicked)
        self.search_scope_button.toggled.connect(self._set_search_subtree_results)
        self.previous_results_button.clicked.connect(self._show_previous_results_page)
        self.next_results_button.clicked.connect(self._show_next_results_page)
        self.scan_play_button.clicked.connect(self._start_root_scan)
        self.scan_stop_button.clicked.connect(self._stop_background_tasks)
        self.search_input.textChanged.connect(self._handle_search_changed)
        self.search_input.returnPressed.connect(self._apply_search_from_enter)
        self.save_tab_button.clicked.connect(self._save_current_location_to_tabs)
        self.bookmark_tab_bar.current_changed.connect(self._on_tab_bar_current_changed)
        self.bookmark_tab_bar.tab_clicked.connect(self._on_tab_bar_clicked)
        self.bookmark_tab_bar.tab_close_requested.connect(self._close_tab)
        self.bookmark_tab_bar.tab_delete_requested.connect(self._delete_tab)
        self.bookmark_tab_bar.tab_delete_by_id_requested.connect(self._delete_tab_by_id)
        self.bookmark_tab_bar.copy_path_requested.connect(self._copy_tab_path)
        self.bookmark_tab_bar.copy_path_by_id_requested.connect(self._copy_tab_path_by_id)
        self.bookmark_tab_bar.reopen_tab_requested.connect(self._reopen_tab)
        self.bookmark_tab_bar.new_tab_requested.connect(self._create_tab_from_current_location)
        self.bookmark_tab_bar.tabs_reordered.connect(self._on_tabs_reordered)
        self.bookmark_tab_bar.rename_requested.connect(self._rename_tab)
        self.bookmark_tab_bar.update_tab_requested.connect(self._update_tab_from_current_state)
        self.column_view.folder_selected.connect(self._handle_folder_selected)
        self.column_view.bookmark_requested.connect(self._save_folder_to_tabs)
        self.column_view.copy_path_requested.connect(self._copy_path_to_clipboard)
        self.file_table.add_file_requested.connect(self._add_file_to_selected_folder)
        self.file_table.copy_requested.connect(lambda paths: self._set_clipboard("copy", paths))
        self.file_table.cut_requested.connect(lambda paths: self._set_clipboard("cut", paths))
        self.file_table.delete_requested.connect(self._delete_selected_files)
        self.file_table.folder_open_requested.connect(self._navigate_to_folder)
        self.file_table.paste_requested.connect(self._paste_into_selected_folder)
        self.file_table.copy_path_requested.connect(self._copy_path_to_clipboard)
        self.index_watcher.changes_ready.connect(self._handle_index_changes)
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

        if (
            not self._text_input_has_focus()
            and self._keyboard_folder_refresh_on_enter()
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)  # type: ignore[attr-defined]
        ):
            if self.column_view.commit_active_column_selection():
                self.status.showMessage("Folder selection applied.")
                event.accept()
                return True

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

    @Slot()
    def _start_root_scan(self) -> None:
        if self.scan_thread is not None:
            return
        if not self.root_path:
            self.status.showMessage("Select a root folder first.")
            return
        self.start_scan(self.root_path)

    @Slot()
    def _stop_background_tasks(self) -> None:
        self.search_timer.stop()
        self._stop_index_watcher()

        if self.scan_worker is None and self.scan_thread is None:
            self.status.showMessage("Background tasks stopped.")
            return

        if self.scan_worker is not None:
            self.scan_worker.request_cancel()

        thread = self.scan_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            deadline = time.monotonic() + 3.0
            while thread.isRunning() and time.monotonic() < deadline:
                QApplication.processEvents()
                thread.wait(100)
            if thread.isRunning():
                thread.terminate()
                thread.wait(1000)

        if self.scan_thread is not None:
            self._pending_tab_restore = None
            self._cleanup_scan_thread()
            if self.root_path:
                self._switch_indexer_for_root(self.root_path)
            self.status.showMessage("Scan stopped.")

    @Slot()
    def _handle_scan_cancelled(self) -> None:
        self._pending_tab_restore = None
        if self.root_path:
            self._switch_indexer_for_root(self.root_path)
        self.status.showMessage("Scan stopped.")

    def _action_for_shortcut(self, shortcut: str) -> str:
        normalized = normalize_key_sequence(shortcut)
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
            "new_tab": self._create_tab_from_current_location,
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
        commit_folder = self._keyboard_folder_navigation_commit()
        if action_id == "scroll_folders_left":
            moved = self.column_view.leave_current_folder()
        elif action_id == "scroll_folders_right":
            moved = self.column_view.enter_selected_folder()
        elif action_id == "scroll_files_up":
            moved = self.column_view.select_previous_folder(
                animate_child_preview=not is_auto_repeat,
                commit=commit_folder,
            )
        elif action_id == "scroll_files_down":
            moved = self.column_view.select_next_folder(
                animate_child_preview=not is_auto_repeat,
                commit=commit_folder,
            )
        else:
            return False

        if not moved:
            self.status.showMessage("No folder to select in that direction.")
        elif not commit_folder:
            self.status.showMessage("Folder highlighted. Press Enter to refresh results.")
        return True

    def _keyboard_folder_refresh_on_enter(self) -> bool:
        return (
            self.keyboard_mode_enabled
            and bool(self.active_search_query.strip())
            and self.keyboard_folder_refresh == KEYBOARD_FOLDER_REFRESH_ON_ENTER
        )

    def _keyboard_folder_navigation_commit(self) -> bool:
        if self._keyboard_folder_refresh_on_enter():
            return False
        return True

    @Slot(bool)
    def _set_keyboard_mode_enabled(self, enabled: bool) -> None:
        self.keyboard_mode_enabled = enabled
        self._save_settings()
        if enabled:
            self.column_view.ensure_keyboard_selection()
            self.status.showMessage("Keyboard mode enabled. Use W/S to select folders, A/D to change levels.")
        else:
            self.status.showMessage("Mouse mode enabled. WASD shortcuts scroll the view.")

    @Slot(bool)
    def _set_search_subtree_results(self, enabled: bool) -> None:
        self.search_subtree_results = enabled
        self._update_search_scope_button()
        self._save_settings()
        if not self.root_path:
            return
        self.search_result_offset = 0
        self._refresh_files()
        self._update_search_status_label()
        if enabled:
            self.status.showMessage("Search scope: current folder and subfolders.")
        else:
            self.status.showMessage("Search scope: current folder only.")

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

    def start_scan(self, root_path: str, *, restore_tab: BookmarkTab | None = None) -> None:
        if self.scan_thread is not None:
            return

        self._stop_index_watcher()
        normalized_root = normalize_path(root_path)
        self._pending_tab_restore = restore_tab
        db_path = database_path_for_root(normalized_root)
        self.indexer = FileIndexer(db_path)
        self.search_service = SearchService(self.indexer)
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
        worker.cancelled.connect(self._handle_scan_cancelled)
        worker.finished.connect(lambda _result: thread.quit())
        worker.failed.connect(lambda _message: thread.quit())
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_scan_thread)

        self.scan_thread = thread
        self.scan_worker = worker
        self._update_scan_controls()
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
        self.root_label.setText(result.root_path)
        self._save_settings()

        pending_tab = self._pending_tab_restore
        self._pending_tab_restore = None

        if pending_tab is not None:
            self.pinned_folder_path = ""
            self.column_view.set_pinned_path("")
            self._apply_tab_state(pending_tab)
            self._update_active_tab_ui()
        else:
            self.selected_folder = result.root_path
            self.pinned_folder_path = ""
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
        self._indexed_file_count = len(result.files)
        self._start_index_watcher()

    @Slot(str)
    def _handle_scan_failed(self, message: str) -> None:
        self._pending_tab_restore = None
        self.status.showMessage(f"Scan failed: {message}")

    @Slot()
    def _cleanup_scan_thread(self) -> None:
        self.scan_thread = None
        self.scan_worker = None
        self.select_root_button.setEnabled(True)
        self.search_input.setEnabled(True)
        self._update_scope_controls()
        self._update_scan_controls()

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

    def _apply_search(
        self,
        query: str,
        show_status: bool = True,
        *,
        anchor_folder: str | None = None,
    ) -> None:
        if not self.root_path:
            return

        stripped = query.strip()
        if stripped and not SearchService.is_searchable(stripped):
            if show_status:
                self.status.showMessage(
                    f"Enter at least {MIN_SEARCH_QUERY_LENGTH} characters to search."
                )
            return

        self.search_timer.stop()
        self.active_search_query = query
        self.search_result_offset = 0

        reset_to_root = bool(stripped) and anchor_folder is None
        if stripped:
            self.selected_folder = normalize_path(anchor_folder) if anchor_folder else self.root_path
        self.column_view.set_search_query(
            self.active_search_query,
            reset_to_root=reset_to_root,
        )

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
            if self.search_subtree_results:
                results, total = self.search_service.results_in_folder_tree(
                    self.selected_folder,
                    self.active_search_query,
                    self.results_page_size,
                    self.search_result_offset,
                )
                self.search_result_total = total
                self.file_table.set_results(results)
            else:
                files, total = self.search_service.files_in_folder(
                    self.selected_folder,
                    self.active_search_query,
                    limit=self.results_page_size,
                    offset=self.search_result_offset,
                )
                self.search_result_total = total
                self.file_table.set_files(files)
        else:
            files, total = self.search_service.files_in_folder(
                self.selected_folder,
                limit=self.results_page_size,
                offset=self.search_result_offset,
            )
            self.search_result_total = total
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
                self._folder_match_counts_enabled(),
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
                self._folder_match_counts_enabled(),
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

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_index_watcher()
        self._save_bookmarks()
        super().closeEvent(event)

    def _load_bookmarks(self) -> None:
        tabs, active_tab_id = load_bookmarks()
        self.tabs = tabs
        self.active_tab_id = active_tab_id
        self.active_tab_index = -1
        if not self.tabs:
            return

        active_tab = self._tab_by_id(self.active_tab_id)
        visible = self._visible_tabs()
        if active_tab is None or not active_tab.open:
            if visible:
                self.active_tab_id = visible[0].id
            else:
                self.active_tab_id = ""

    def _visible_tabs(self) -> list[BookmarkTab]:
        return [tab for tab in self.tabs if tab.open]

    def _closed_tabs(self) -> list[BookmarkTab]:
        return [tab for tab in self.tabs if not tab.open]

    def _tab_by_id(self, tab_id: str) -> BookmarkTab | None:
        if not tab_id:
            return None
        for tab in self.tabs:
            if tab.id == tab_id:
                return tab
        return None

    def _visible_index_for_id(self, tab_id: str) -> int:
        for index, tab in enumerate(self._visible_tabs()):
            if tab.id == tab_id:
                return index
        return -1

    def _visible_tab_at(self, visible_index: int) -> BookmarkTab | None:
        visible = self._visible_tabs()
        if 0 <= visible_index < len(visible):
            return visible[visible_index]
        return None

    def _sync_tab_bar(self) -> None:
        visible = self._visible_tabs()
        self.bookmark_tab_bar.set_tabs(visible)
        self.bookmark_tab_bar.set_closed_tabs(self._closed_tabs())
        visible_index = self._visible_index_for_id(self.active_tab_id)
        if visible_index >= 0:
            self.active_tab_index = visible_index
            self.bookmark_tab_bar.set_current_index(visible_index)
        else:
            self.active_tab_index = -1

    def _save_bookmarks(self) -> None:
        save_bookmarks(self.tabs, self.active_tab_id)

    def _switch_indexer_for_root(self, root_path: str) -> bool:
        normalized_root = normalize_path(root_path)
        db_path = database_path_for_root(normalized_root)
        if not db_path.exists():
            legacy_path = database_path()
            last_root = str(self.app_settings.get("last_root", "") or "")
            if legacy_path.exists() and normalize_path(last_root) == normalized_root:
                db_path = legacy_path

        if not db_path.exists():
            return False

        self.indexer = FileIndexer(db_path)
        self.search_service = SearchService(self.indexer)
        self._indexed_file_count = self.indexer.get_file_count()
        return self._indexed_file_count > 0

    def _confirm_root_switch(self, tab: BookmarkTab) -> bool | None:
        message = (
            "This tab uses a different root directory:\n\n"
            f"{tab.root_path}\n\n"
            "Switching will trigger a rescan. Continue?"
        )
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Different Root Directory")
        dialog.setText(message)
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Yes)
        result = dialog.exec()
        if result == QMessageBox.StandardButton.Yes:
            return True
        if result == QMessageBox.StandardButton.No:
            return False
        return None

    def _clear_pin_for_tab_switch(self) -> None:
        if not self.pinned_folder_path:
            return
        self.pinned_folder_path = ""
        self.search_result_offset = 0
        self.column_view.set_pinned_path("")
        self._update_scope_controls()

    def _apply_tab_state(self, tab: BookmarkTab) -> None:
        target_root = normalize_path(tab.root_path)
        folder_path = normalize_path(tab.folder_path)
        self.root_path = target_root
        self.root_label.setText(target_root)

        self.selected_folder = folder_path
        self.search_result_offset = 0
        if normalize_path(self.column_view.root_path) != target_root:
            self.column_view.set_root(target_root, emit_selection=False)
        self.column_view.rebuild_to_path(folder_path)

        self.search_input.blockSignals(True)
        self.search_input.setText(tab.search_query)
        self.search_input.blockSignals(False)
        self._apply_search(
            tab.search_query,
            show_status=False,
            anchor_folder=folder_path if tab.search_query.strip() else None,
        )

        if self.keyboard_mode_enabled:
            self.column_view.ensure_keyboard_selection()
        self._update_scope_controls()

    def _update_active_tab_ui(self) -> None:
        visible_index = self._visible_index_for_id(self.active_tab_id)
        if visible_index < 0:
            self.active_tab_index = -1
            return
        self.active_tab_index = visible_index
        self.bookmark_tab_bar.set_current_index(visible_index)

    def _is_at_tab_location(self, tab: BookmarkTab) -> bool:
        if normalize_path(self.root_path or "") != normalize_path(tab.root_path):
            return False
        if normalize_path(self.selected_folder or "") != normalize_path(tab.folder_path):
            return False
        return self.active_search_query.strip() == tab.search_query.strip()

    def _activate_tab(self, visible_index: int, *, initial: bool = False) -> None:
        tab = self._visible_tab_at(visible_index)
        if tab is None:
            return
        if self._tab_activation_in_progress:
            return
        if (
            not initial
            and tab.id == self.active_tab_id
            and self._is_at_tab_location(tab)
        ):
            return

        previous_id = self.active_tab_id
        self._clear_pin_for_tab_switch()

        current_root = normalize_path(self.root_path) if self.root_path else ""
        target_root = normalize_path(tab.root_path)

        self._tab_activation_in_progress = True
        try:
            if current_root and current_root == target_root:
                self.active_tab_id = tab.id
                self._apply_tab_state(tab)
                self._update_active_tab_ui()
                self._save_bookmarks()
                return

            if self._switch_indexer_for_root(tab.root_path):
                self.root_path = target_root
                self.root_label.setText(target_root)
                self.active_tab_id = tab.id
                self._apply_tab_state(tab)
                self._update_active_tab_ui()
                self._save_settings()
                self._save_bookmarks()
                self._start_index_watcher()
                return

            if initial:
                self.active_tab_id = tab.id
                self._update_active_tab_ui()
                self.start_scan(tab.root_path, restore_tab=tab)
                return

            choice = self._confirm_root_switch(tab)
            if choice is not True:
                self.active_tab_id = previous_id
                self._update_active_tab_ui()
                if choice is False:
                    self.status.showMessage("Tab switch cancelled.")
                return

            self.active_tab_id = tab.id
            self._update_active_tab_ui()
            self.start_scan(tab.root_path, restore_tab=tab)
        finally:
            self._tab_activation_in_progress = False

    @Slot(int)
    def _on_tab_bar_current_changed(self, visible_index: int) -> None:
        if self._visible_tab_at(visible_index) is None:
            return
        self._activate_tab(visible_index)

    @Slot(int)
    def _on_tab_bar_clicked(self, visible_index: int) -> None:
        if self._visible_tab_at(visible_index) is None:
            return
        self._activate_tab(visible_index)

    @Slot(int, int)
    def _on_tabs_reordered(self, from_index: int, to_index: int) -> None:
        visible = self._visible_tabs()
        if (
            from_index < 0
            or to_index < 0
            or from_index >= len(visible)
            or to_index >= len(visible)
            or from_index == to_index
        ):
            return
        tab = visible.pop(from_index)
        visible.insert(to_index, tab)
        self.tabs = visible + self._closed_tabs()
        self._sync_tab_bar()
        self._save_bookmarks()

    @Slot(int, str)
    def _rename_tab(self, visible_index: int, label: str) -> None:
        tab = self._visible_tab_at(visible_index)
        if tab is None:
            return
        tab.label = label.strip()
        self._sync_tab_bar()
        self._save_bookmarks()

    @Slot(int)
    def _update_tab_from_current_state(self, visible_index: int) -> None:
        tab = self._visible_tab_at(visible_index)
        if tab is None or tab.id != self.active_tab_id:
            return
        if not self.root_path:
            self.status.showMessage("Select a root folder before updating a tab.")
            return

        tab.root_path = normalize_path(self.root_path)
        tab.folder_path = normalize_path(self.selected_folder or self.root_path)
        tab.search_query = self.active_search_query.strip()
        self._sync_tab_bar()
        self._save_bookmarks()
        detail = tab.folder_path
        if tab.search_query:
            detail += f" · search: {tab.search_query}"
        self.status.showMessage(f"Updated tab: {tab.display_label()} ({detail})")

    @Slot(int)
    def _close_tab(self, visible_index: int) -> None:
        tab = self._visible_tab_at(visible_index)
        if tab is None:
            return

        closing_active = tab.id == self.active_tab_id
        tab.open = False
        visible = self._visible_tabs()

        if not visible:
            self.active_tab_id = ""
            self.active_tab_index = -1
            self._sync_tab_bar()
            self._save_bookmarks()
            self.status.showMessage(
                f"Closed tab: {tab.display_label()}. Reopen it from >> → Closed bookmarks."
            )
            return

        if closing_active:
            next_index = min(visible_index, len(visible) - 1)
            next_tab = visible[next_index]
            self.active_tab_id = next_tab.id
            self._sync_tab_bar()
            self._activate_tab(next_index)
        else:
            self._sync_tab_bar()

        self._save_bookmarks()
        self.status.showMessage(
            f"Closed tab: {tab.display_label()}. Bookmark kept — reopen from >>."
        )

    @Slot(int)
    def _delete_tab(self, visible_index: int) -> None:
        tab = self._visible_tab_at(visible_index)
        if tab is None:
            return

        dialog_parent = self.bookmark_tab_bar.modal_dialog_parent()
        response = QMessageBox.question(
            dialog_parent,
            "Delete Tab",
            f"Delete this saved tab permanently?\n\n{tab.folder_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        deleting_active = tab.id == self.active_tab_id
        self.tabs = [saved_tab for saved_tab in self.tabs if saved_tab.id != tab.id]
        visible = self._visible_tabs()

        if not visible:
            self.active_tab_id = ""
            self.active_tab_index = -1
            self._sync_tab_bar()
            self._save_bookmarks()
            self.status.showMessage(f"Deleted tab: {tab.display_label()}")
            return

        if deleting_active:
            next_index = min(visible_index, len(visible) - 1)
            self.active_tab_id = visible[next_index].id
            self._sync_tab_bar()
            self._activate_tab(next_index)
        else:
            self._sync_tab_bar()

        self._save_bookmarks()
        self.status.showMessage(f"Deleted tab: {tab.display_label()}")

    @Slot(str)
    def _reopen_tab(self, tab_id: str) -> None:
        tab = self._tab_by_id(tab_id)
        if tab is None or tab.open:
            return

        tab.open = True
        self._sync_tab_bar()
        visible_index = self._visible_index_for_id(tab.id)
        if visible_index >= 0:
            self._activate_tab(visible_index)
        self._save_bookmarks()
        self.status.showMessage(f"Reopened tab: {tab.display_label()}")

    def _copy_path_to_clipboard(self, path: str) -> None:
        if not path:
            return
        QGuiApplication.clipboard().setText(path)
        self.status.showMessage(f"Copied full path: {path}")

    def _copy_tab_path(self, visible_index: int) -> None:
        tab = self._visible_tab_at(visible_index)
        if tab is None:
            return
        self._copy_path_to_clipboard(tab.folder_path)

    def _copy_tab_path_by_id(self, tab_id: str) -> None:
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return
        self._copy_path_to_clipboard(tab.folder_path)

    @Slot(str)
    def _delete_tab_by_id(self, tab_id: str) -> None:
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return

        dialog_parent = self.bookmark_tab_bar.modal_dialog_parent()
        response = QMessageBox.question(
            dialog_parent,
            "Delete Tab",
            f"Delete this saved tab permanently?\n\n{tab.folder_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        deleting_active = tab.id == self.active_tab_id
        self.tabs = [saved_tab for saved_tab in self.tabs if saved_tab.id != tab_id]
        visible = self._visible_tabs()

        if not visible:
            self.active_tab_id = ""
            self.active_tab_index = -1
            self._sync_tab_bar()
            self._save_bookmarks()
            self.status.showMessage(f"Deleted tab: {tab.display_label()}")
            return

        if deleting_active:
            self.active_tab_id = visible[0].id
            self._sync_tab_bar()
            self._activate_tab(0)
        else:
            self._sync_tab_bar()

        self._save_bookmarks()
        self.status.showMessage(f"Deleted tab: {tab.display_label()}")

    def _create_tab_from_current_location(self) -> None:
        self._add_tab_from_state()

    @Slot()
    def _save_current_location_to_tabs(self) -> None:
        self._add_tab_from_state()

    @Slot(str)
    def _save_folder_to_tabs(self, folder_path: str) -> None:
        self._add_tab_from_state(folder_path=folder_path)

    def _add_tab_from_state(
        self,
        *,
        folder_path: str | None = None,
        search_query: str | None = None,
    ) -> None:
        if not self.root_path:
            self.status.showMessage("Select a root folder before saving a tab.")
            return

        folder = folder_path or self.selected_folder or self.root_path
        search = self.active_search_query if search_query is None else search_query
        normalized_root = normalize_path(self.root_path)
        normalized_folder = normalize_path(folder)
        normalized_search = search.strip()

        tab = BookmarkTab(
            root_path=normalized_root,
            folder_path=normalized_folder,
            search_query=normalized_search,
        )
        self.tabs.append(tab)
        self.active_tab_id = tab.id
        self._sync_tab_bar()
        visible_index = self._visible_index_for_id(tab.id)
        if visible_index >= 0:
            self.bookmark_tab_bar.set_current_index(visible_index)
        self._save_bookmarks()
        self.status.showMessage(f"Saved tab: {tab.display_label()}")

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

    def _start_index_watcher(self) -> None:
        if not self.root_path or not self.watch_index_changes:
            return
        if self._indexed_file_count > LARGE_INDEX_FILE_COUNT:
            self.status.showMessage(
                "File watching skipped for large indexes (>100k files)."
            )
            return
        self.index_watcher.start(self.root_path, self.indexer)

    def _stop_index_watcher(self) -> None:
        self.index_watcher.stop()

    @Slot(object)
    def _handle_index_changes(self, affected_folders: set[str]) -> None:
        if not self.root_path or not affected_folders:
            return

        self.search_service.clear_cache()
        current_folder = self.selected_folder or self.root_path
        if not self._index_change_affects_view(current_folder, affected_folders):
            self.status.showMessage("Index updated from file changes.")
            return

        if self.active_search_query.strip():
            self.column_view.set_search_query(self.active_search_query)
            self._refresh_files()
        else:
            self.column_view.rebuild_to_path(current_folder)
            self._refresh_files()
        self.status.showMessage("Index updated from file changes.")

    def _index_change_affects_view(
        self,
        current_folder: str,
        affected_folders: set[str],
    ) -> bool:
        normalized_current = normalize_path(current_folder)
        for folder in affected_folders:
            normalized_folder = normalize_path(folder)
            if normalized_folder == normalized_current:
                return True
            if self._is_same_or_descendant(normalized_current, normalized_folder):
                return True
            if self._is_same_or_descendant(normalized_folder, normalized_current):
                return True
        return False

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
    def _open_settings(self) -> None:
        applied_snapshot = self._capture_settings_snapshot()
        dialog = SettingsDialog(
            self.search_mode,
            self.debounce_ms,
            self.results_page_size,
            self.show_folder_match_counts,
            self.watch_index_changes,
            self.keyboard_mode_enabled,
            self.keyboard_folder_refresh,
            self.show_file_icons,
            self.show_folder_icons,
            self.theme_name,
            self.custom_theme_colors,
            self.key_bindings,
            self,
        )
        dialog.preview_requested.connect(self._preview_theme)
        dialog.apply_requested.connect(
            lambda: self._handle_settings_apply(dialog, applied_snapshot)
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._restore_settings_snapshot(applied_snapshot)
            self.status.showMessage("Settings canceled.")
            return

        self._apply_settings_from_dialog(dialog)
        self.status.showMessage("Settings saved.")

    def _capture_settings_snapshot(self) -> dict[str, object]:
        return {
            "search_mode": self.search_mode,
            "debounce_ms": self.debounce_ms,
            "results_page_size": self.results_page_size,
            "show_folder_match_counts": self.show_folder_match_counts,
            "watch_index_changes": self.watch_index_changes,
            "search_subtree_results": self.search_subtree_results,
            "keyboard_mode_enabled": self.keyboard_mode_enabled,
            "keyboard_folder_refresh": self.keyboard_folder_refresh,
            "theme_name": self.theme_name,
            "custom_theme_colors": dict(self.custom_theme_colors),
            "show_file_icons": self.show_file_icons,
            "show_folder_icons": self.show_folder_icons,
            "key_bindings": dict(self.key_bindings),
        }

    def _restore_settings_snapshot(self, snapshot: dict[str, object]) -> None:
        self.search_mode = self._normalize_search_mode(snapshot["search_mode"])
        self.debounce_ms = self._normalize_debounce_ms(snapshot["debounce_ms"])
        self.results_page_size = self._normalize_results_page_size(snapshot["results_page_size"])
        self.show_folder_match_counts = bool(snapshot["show_folder_match_counts"])
        self.watch_index_changes = bool(
            snapshot.get("watch_index_changes", DEFAULT_WATCH_INDEX_CHANGES)
        )
        self.search_subtree_results = bool(
            snapshot.get("search_subtree_results", DEFAULT_SEARCH_SUBTREE_RESULTS)
        )
        self.keyboard_mode_enabled = bool(snapshot.get("keyboard_mode_enabled", False))
        self.keyboard_folder_refresh = self._normalize_keyboard_folder_refresh(
            snapshot["keyboard_folder_refresh"]
        )
        self.theme_name = self._normalize_theme_name(snapshot["theme_name"])
        self.custom_theme_colors = normalize_custom_theme_colors(
            snapshot.get("custom_theme_colors")
        )
        self.show_file_icons = bool(snapshot.get("show_file_icons", DEFAULT_SHOW_FILE_ICONS))
        self.show_folder_icons = bool(snapshot.get("show_folder_icons", DEFAULT_SHOW_FOLDER_ICONS))
        self.key_bindings = self._normalize_key_bindings(snapshot["key_bindings"])
        self._apply_settings_effects(refresh_files=True, save_disk=False)

    def _apply_settings_from_dialog(self, dialog: SettingsDialog) -> None:
        (
            self.search_mode,
            self.debounce_ms,
            self.results_page_size,
            self.show_folder_match_counts,
            self.watch_index_changes,
            self.keyboard_mode_enabled,
            self.keyboard_folder_refresh,
        ) = dialog.search_values()
        self.search_mode = self._normalize_search_mode(self.search_mode)
        self.debounce_ms = self._normalize_debounce_ms(self.debounce_ms)
        self.results_page_size = self._normalize_results_page_size(self.results_page_size)
        self.keyboard_folder_refresh = self._normalize_keyboard_folder_refresh(
            self.keyboard_folder_refresh
        )
        self.show_file_icons, self.show_folder_icons = dialog.ui_values()
        self.theme_name = self._normalize_theme_name(dialog.theme_value())
        self.custom_theme_colors = normalize_custom_theme_colors(dialog.custom_theme_colors())
        self.key_bindings = self._normalize_key_bindings(dialog.keyboard_values())
        self._apply_settings_effects(refresh_files=True, save_disk=True)

    def _handle_settings_apply(
        self,
        dialog: SettingsDialog,
        applied_snapshot: dict[str, object],
    ) -> None:
        self._apply_settings_from_dialog(dialog)
        applied_snapshot.clear()
        applied_snapshot.update(self._capture_settings_snapshot())
        if self.search_mode == SEARCH_MODE_DEBOUNCED:
            self.status.showMessage(f"Settings applied. Search while typing ({self.debounce_ms} ms).")
        else:
            self.status.showMessage("Settings applied.")

    def _apply_settings_effects(self, *, refresh_files: bool, save_disk: bool) -> None:
        self.search_result_offset = 0
        self._update_search_placeholder()
        self.file_table.set_show_file_icons(self.show_file_icons)
        self.column_view.set_show_folder_icons(self.show_folder_icons)
        self._apply_theme()
        self._apply_shortcut_labels()
        if save_disk:
            self._save_settings()
        if refresh_files and self.root_path:
            self.column_view.set_search_query(self.active_search_query)
            if self.selected_folder:
                self.column_view.rebuild_to_path(self.selected_folder)
            self._refresh_files()
        if self.watch_index_changes and self.root_path:
            self._start_index_watcher()
        else:
            self._stop_index_watcher()
        if self.search_mode == SEARCH_MODE_DEBOUNCED:
            if self.root_path:
                self.search_timer.start(self.debounce_ms)
        else:
            self.search_timer.stop()
        if self.keyboard_mode_enabled and self.root_path:
            self.column_view.ensure_keyboard_selection()

    @Slot(str)
    @Slot(str, object)
    def _preview_theme(self, theme_name: str, custom_colors: object = None) -> None:
        self.theme_name = self._normalize_theme_name(theme_name)
        if custom_colors is not None:
            self.custom_theme_colors = normalize_custom_theme_colors(custom_colors)
        theme = resolve_theme(self.theme_name, self.custom_theme_colors)
        self._apply_theme()
        self.status.showMessage(f"Previewing theme: {theme['label']}")

    def _load_last_root_if_available(self) -> None:
        last_root = str(self.app_settings.get("last_root", "") or "")
        if not last_root:
            return

        self.root_label.setText(last_root)
        if Path(last_root).exists() and self._switch_indexer_for_root(last_root):
            self.root_path = normalize_path(last_root)
            self.selected_folder = self.root_path
            self.column_view.set_root(self.root_path)
            self.column_view.set_pinned_path("")
            if self.keyboard_mode_enabled:
                self.column_view.ensure_keyboard_selection()
            self._refresh_files()
            self._update_scope_controls()
            self._start_index_watcher()
            self.status.showMessage("Loaded previous index. Use the scan button if files look out of date.")

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
        self.app_settings["watch_index_changes"] = self.watch_index_changes
        self.app_settings["search_subtree_results"] = self.search_subtree_results
        self.app_settings["keyboard_folder_refresh"] = self.keyboard_folder_refresh
        self.app_settings["theme"] = self.theme_name
        self.app_settings["custom_theme_colors"] = dict(self.custom_theme_colors)
        self.app_settings["show_file_icons"] = self.show_file_icons
        self.app_settings["show_folder_icons"] = self.show_folder_icons
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
                normalized[action_id] = normalize_key_sequence(bindings[action_id])
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
        self._update_search_scope_button()
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
            if self.search_subtree_results:
                text += " · subtree"
            else:
                text += " · folder only"
            if self.last_search_elapsed_ms is not None:
                text += f" · {self.last_search_elapsed_ms:.1f} ms"
            self.search_status_label.setText(text)
            return

        self.search_status_label.setText("")

    def _update_search_scope_button(self) -> None:
        self.search_scope_button.blockSignals(True)
        self.search_scope_button.setChecked(self.search_subtree_results)
        self.search_scope_button.blockSignals(False)
        if self.search_subtree_results:
            self.search_scope_button.setText("Search: Subtree")
            self.search_scope_button.setToolTip(
                "Searching current folder and all subfolders. Click to switch to folder-only."
            )
        else:
            self.search_scope_button.setText("Search: Folder")
            self.search_scope_button.setToolTip(
                "Searching current folder only. Click to switch to subtree."
            )

    def _normalize_theme_name(self, value: object) -> str:
        theme_name = str(value or "")
        return theme_name if theme_name in THEMES else DEFAULT_THEME

    def _apply_theme(self) -> None:
        theme = resolve_theme(self.theme_name, self.custom_theme_colors)
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

            QWidget#contentPanel,
            QTableWidget#contentPanel {{
                background: {theme["surface"]};
                border: 1px solid {theme["border"]};
            }}

            QLabel#panelHeader {{
                background: {theme["surface"]};
                color: {theme["text"]};
                padding: 4px 8px;
                border-bottom: 1px solid {theme["border"]};
            }}

            QHeaderView::section {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: none;
                border-bottom: 1px solid {theme["border"]};
                border-right: 1px solid {theme["border"]};
                padding: 4px 8px;
            }}

            QListWidget {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: 1px solid {theme["border"]};
            }}

            QListWidget#folderColumnList {{
                border: none;
                border-right: 1px solid {theme["border"]};
            }}

            QTableWidget {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: none;
                alternate-background-color: {theme["alternate_surface"]};
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

            QTabBar::tab {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: 1px solid {theme["border"]};
                border-bottom: none;
                padding: 2px 20px 3px 10px;
                margin-right: 2px;
                min-height: 24px;
            }}

            QTabBar::tab:selected {{
                background: {theme["background"]};
                color: {theme["text"]};
                border-bottom: 1px solid {theme["background"]};
            }}

            QTabBar::tab:selected:hover {{
                color: {theme["text"]};
            }}

            QTabBar::tab:hover {{
                background: #dbeeff;
                color: #111111;
            }}

            QTabBar::close-button {{
                width: 0;
                height: 0;
                border: none;
                image: none;
            }}

            QToolButton#bookmarkTabCloseButton {{
                color: {theme["text"]};
                background: transparent;
                border: none;
                padding: 0;
                margin: 0;
                font-size: 13px;
                font-weight: 700;
            }}

            QToolButton#bookmarkTabCloseButton:hover {{
                background: rgba(0, 0, 0, 0.12);
                color: {theme["text"]};
                border-radius: 3px;
            }}

            QToolButton#bookmarkTabCloseButton:pressed {{
                background: rgba(0, 0, 0, 0.2);
                color: {theme["text"]};
            }}

            QPushButton#tabBarActionButton {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: 1px solid {theme["border"]};
                border-radius: 4px;
                padding: 2px 4px;
            }}

            QPushButton#tabBarActionButton:hover {{
                background: #dbeeff;
                color: #111111;
                border: 1px solid #7cb7e8;
            }}

            QPushButton#tabBarActionButton:pressed {{
                background: #b7dcff;
                color: #111111;
                border: 1px solid #4f9edb;
            }}

            QFrame#tabOverflowPopup {{
                background: {theme["surface"]};
                border: 1px solid {theme["border"]};
            }}

            QListWidget#tabOverflowList {{
                background: {theme["surface"]};
                color: {theme["text"]};
                border: none;
                outline: none;
            }}

            QListWidget#tabOverflowList::item:selected {{
                background: #cfe8ff;
                color: #111111;
            }}

            QListWidget#tabOverflowList::item:hover {{
                background: #dbeeff;
                color: #111111;
            }}

            QPushButton#saveTabButton {{
                font-size: 16px;
                padding: 2px 4px;
            }}

            QPushButton#scanPlayButton,
            QPushButton#scanStopButton {{
                background: transparent;
                border: none;
                padding: 2px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}

            QPushButton#scanPlayButton:hover,
            QPushButton#scanStopButton:hover {{
                background: {theme["alternate_surface"]};
                border: none;
            }}

            QPushButton#scanPlayButton:pressed,
            QPushButton#scanStopButton:pressed {{
                background: {theme["border"]};
                border: none;
            }}

            QPushButton#scanPlayButton:disabled,
            QPushButton#scanStopButton:disabled {{
                background: transparent;
                border: none;
            }}

            QListWidget#settingsNav {{
                background: {theme["background"]};
                border: none;
                border-right: 1px solid {theme["border"]};
                outline: none;
                padding: 6px 0;
            }}

            QListWidget#settingsNav::item {{
                padding: 6px 16px;
                margin: 1px 8px;
                border: none;
                min-height: 22px;
            }}

            QListWidget#settingsNav::item:selected {{
                background: #cfe8ff;
                color: #111111;
                border-radius: 4px;
            }}

            QListWidget#settingsNav::item:hover {{
                background: #dbeeff;
                color: #111111;
                border-radius: 4px;
            }}

            QStackedWidget#settingsStack {{
                background: {theme["surface"]};
                border: none;
            }}

            QLabel#settingsPageTitle {{
                font-size: 20px;
                font-weight: 600;
                padding-bottom: 8px;
            }}

            QLabel#settingsPageIntro {{
                color: {theme["text"]};
                padding-bottom: 12px;
            }}

            QPushButton#themeColorButton {{
                min-height: 26px;
                padding: 4px 10px;
                border: 1px solid {theme["border"]};
                border-radius: 4px;
            }}

            QLabel#settingsSectionTitle {{
                font-size: 14px;
                font-weight: 600;
                padding-top: 12px;
                padding-bottom: 4px;
            }}

            QWidget#fileAreaModeRow QPushButton#fileAreaModeOption {{
                min-width: 0;
                min-height: 26px;
                padding: 3px 14px;
                border: 1px solid {theme["border"]};
                border-radius: 4px;
                background: {theme["background"]};
                color: {theme["text"]};
            }}

            QWidget#fileAreaModeRow QPushButton#fileAreaModeOption:checked {{
                background: #4f9edb;
                color: #ffffff;
                border: 1px solid #357abd;
            }}

            QWidget#fileAreaModeRow QPushButton#fileAreaModeOption:hover:!checked {{
                background: {theme["alternate_surface"]};
            }}

            QWidget#settingsButtons {{
                padding: 0;
            }}

            QWidget#settingsButtons QPushButton {{
                min-width: 73px;
                min-height: 25px;
                padding: 5px 14px;
            }}
            """
        )
        self.bookmark_tab_bar.refresh_close_button_styles()

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

    def _normalize_keyboard_folder_refresh(self, value: object) -> str:
        if value == KEYBOARD_FOLDER_REFRESH_ON_ENTER:
            return KEYBOARD_FOLDER_REFRESH_ON_ENTER
        return DEFAULT_KEYBOARD_FOLDER_REFRESH

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

    def _update_scan_controls(self) -> None:
        scanning = self.scan_thread is not None
        self.scan_play_button.setEnabled(not scanning and bool(self.root_path))
        self.scan_stop_button.setEnabled(True)
        self.scan_play_button.update()
        self.scan_stop_button.update()

    def _update_pagination_controls(self) -> None:
        if not self.selected_folder:
            self.previous_results_button.setEnabled(False)
            self.next_results_button.setEnabled(False)
            self.results_page_label.setText("")
            return

        has_previous = self.search_result_offset > 0
        has_next = (
            self.search_result_offset + self.results_page_size < self.search_result_total
        )

        self.previous_results_button.setEnabled(has_previous)
        self.next_results_button.setEnabled(has_next)

        if self.search_result_total == 0:
            self.results_page_label.setText("0 items")
            return

        start = self.search_result_offset + 1
        end = min(self.search_result_offset + self.results_page_size, self.search_result_total)
        self.results_page_label.setText(f"{start:,}-{end:,} of {self.search_result_total:,}")

    def _folder_match_counts_enabled(self) -> bool:
        return (
            self.show_folder_match_counts
            and self._indexed_file_count <= LARGE_INDEX_FILE_COUNT
        )

    def _with_folder_match_counts(self, folders: list[object], query: str) -> list[object]:
        if not self._folder_match_counts_enabled() or not query.strip():
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
