from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QKeySequenceEdit,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

SETTINGS_NAV_ITEM_HEIGHT = 35
SETTINGS_NAV_ITEM_SPACING = 3

from app.core.search_constants import DEFAULT_WATCH_INDEX_CHANGES
from app.ui.settings_constants import (
    DEFAULT_CUSTOM_THEME_COLORS,
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
    THEME_COLOR_KEYS,
    THEME_COLOR_LABELS,
    THEME_CUSTOM,
    THEMES,
    normalize_custom_theme_colors,
    normalize_key_sequence,
)


class ShortcutKeySequenceEdit(QKeySequenceEdit):
    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Backspace:
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


class SearchSettingsPage(QWidget):
    def __init__(
        self,
        search_mode: str,
        debounce_ms: int,
        results_page_size: int,
        show_folder_match_counts: bool,
        watch_index_changes: bool,
        keyboard_mode_enabled: bool,
        keyboard_folder_refresh: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        title = QLabel("Search")
        title.setObjectName("settingsPageTitle")

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

        self.watch_index_changes_input = QCheckBox(
            "Watch files and update index automatically (slow on large libraries)"
        )
        self.watch_index_changes_input.setChecked(watch_index_changes)

        self.file_area_mode_group = QButtonGroup(self)
        self.file_area_mode_group.setExclusive(True)
        self.keyboard_mode_option = QPushButton("Keyboard mode")
        self.mouse_mode_option = QPushButton("Mouse mode")
        for button in (self.keyboard_mode_option, self.mouse_mode_option):
            button.setCheckable(True)
            button.setObjectName("fileAreaModeOption")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.file_area_mode_group.addButton(button)
        if keyboard_mode_enabled:
            self.keyboard_mode_option.setChecked(True)
        else:
            self.mouse_mode_option.setChecked(True)

        file_area_row = QWidget()
        file_area_row.setObjectName("fileAreaModeRow")
        file_area_layout = QHBoxLayout(file_area_row)
        file_area_layout.setContentsMargins(0, 0, 0, 0)
        file_area_layout.setSpacing(8)
        file_area_layout.addWidget(self.keyboard_mode_option)
        file_area_layout.addWidget(self.mouse_mode_option)
        file_area_layout.addStretch(1)

        self.keyboard_folder_refresh_input = QComboBox()
        self.keyboard_folder_refresh_input.addItem(
            "Refresh on each W/S key (default)",
            KEYBOARD_FOLDER_REFRESH_IMMEDIATE,
        )
        self.keyboard_folder_refresh_input.addItem(
            "Refresh when Enter is pressed (while searching)",
            KEYBOARD_FOLDER_REFRESH_ON_ENTER,
        )
        self.keyboard_folder_refresh_input.setCurrentIndex(
            self.keyboard_folder_refresh_input.findData(keyboard_folder_refresh)
            if self.keyboard_folder_refresh_input.findData(keyboard_folder_refresh) >= 0
            else self.keyboard_folder_refresh_input.findData(DEFAULT_KEYBOARD_FOLDER_REFRESH)
        )

        form = QFormLayout()
        form.addRow("Search mode", self.mode_input)
        form.addRow("Debounce delay", self.debounce_input)
        form.addRow("Results per page", self.results_page_size_input)
        form.addRow("Folder counts", self.show_folder_match_counts_input)
        form.addRow("File watching", self.watch_index_changes_input)
        form.addRow("Keyboard W/S refresh", self.keyboard_folder_refresh_input)
        form.addRow("Operation mode", file_area_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addStretch(1)

        self.file_area_mode_group.idToggled.connect(self._on_file_area_mode_toggled)
        self._update_keyboard_refresh_enabled()

    def _on_file_area_mode_toggled(self, _button_id: int, checked: bool) -> None:
        if not checked:
            return
        self._update_keyboard_refresh_enabled()

    def _update_keyboard_refresh_enabled(self) -> None:
        keyboard_mode = self.keyboard_mode_option.isChecked()
        self.keyboard_folder_refresh_input.setEnabled(keyboard_mode)

    def values(self) -> tuple[str, int, int, bool, bool, bool, str]:
        return (
            str(self.mode_input.currentData()),
            int(self.debounce_input.value()),
            int(self.results_page_size_input.value()),
            self.show_folder_match_counts_input.isChecked(),
            self.watch_index_changes_input.isChecked(),
            self.keyboard_mode_option.isChecked(),
            str(self.keyboard_folder_refresh_input.currentData()),
        )


class UISettingsPage(QWidget):
    def __init__(
        self,
        show_file_icons: bool,
        show_folder_icons: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        title = QLabel("UI")
        title.setObjectName("settingsPageTitle")

        intro = QLabel(
            "Appearance and layout options. More personalization settings will be added here."
        )
        intro.setWordWrap(True)
        intro.setObjectName("settingsPageIntro")

        self.show_file_icons_input = QCheckBox("Show file type icons in the file list")
        self.show_file_icons_input.setChecked(show_file_icons)

        self.show_folder_icons_input = QCheckBox("Show folder icons in the folder columns")
        self.show_folder_icons_input.setChecked(show_folder_icons)

        form = QFormLayout()
        form.addRow("File list", self.show_file_icons_input)
        form.addRow("Folder columns", self.show_folder_icons_input)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addStretch(1)

    def values(self) -> tuple[bool, bool]:
        return (
            self.show_file_icons_input.isChecked(),
            self.show_folder_icons_input.isChecked(),
        )


class ThemeSettingsPage(QWidget):
    preview_requested = Signal(str, object)

    def __init__(
        self,
        theme_name: str,
        custom_theme_colors: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._custom_colors = normalize_custom_theme_colors(custom_theme_colors)
        self._color_buttons: dict[str, QPushButton] = {}
        self._updating_theme_list = False

        title = QLabel("Theme")
        title.setObjectName("settingsPageTitle")

        self.theme_list = QListWidget()
        self.theme_list.setMinimumHeight(220)
        for theme_id, theme in THEMES.items():
            item = QListWidgetItem(theme["label"])
            item.setData(Qt.ItemDataRole.UserRole, theme_id)
            self.theme_list.addItem(item)
            if theme_id == theme_name:
                self.theme_list.setCurrentItem(item)
        if self.theme_list.currentItem() is None:
            self._select_theme(DEFAULT_THEME)
        self.theme_list.currentItemChanged.connect(self._handle_theme_changed)

        self.custom_panel = QWidget()
        custom_form = QFormLayout(self.custom_panel)
        custom_form.setContentsMargins(0, 8, 0, 0)
        for color_key in THEME_COLOR_KEYS:
            button = QPushButton()
            button.setObjectName("themeColorButton")
            button.setMinimumWidth(140)
            button.clicked.connect(lambda _checked=False, key=color_key: self._pick_color(key))
            self._color_buttons[color_key] = button
            custom_form.addRow(THEME_COLOR_LABELS[color_key], button)
            self._update_color_button(color_key)

        reset_button = QPushButton("Reset to Default")
        reset_button.clicked.connect(self._select_default_theme)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title)
        layout.addWidget(self.theme_list, stretch=1)
        layout.addWidget(self.custom_panel)
        layout.addWidget(reset_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self._sync_custom_panel_visibility()
        self._emit_preview()

    def value(self) -> str:
        item = self.theme_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else DEFAULT_THEME

    def custom_colors(self) -> dict[str, str]:
        return dict(self._custom_colors)

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
        if self._updating_theme_list or current is None:
            return
        self._sync_custom_panel_visibility()
        self._emit_preview()

    def _sync_custom_panel_visibility(self) -> None:
        self.custom_panel.setVisible(self.value() == THEME_CUSTOM)

    def _pick_color(self, color_key: str) -> None:
        current = QColor(self._custom_colors.get(color_key, DEFAULT_CUSTOM_THEME_COLORS[color_key]))
        chosen = QColorDialog.getColor(
            current,
            self,
            f"Choose {THEME_COLOR_LABELS.get(color_key, color_key)}",
        )
        if not chosen.isValid():
            return
        self._custom_colors[color_key] = chosen.name()
        self._update_color_button(color_key)
        if self.value() != THEME_CUSTOM:
            self._select_theme(THEME_CUSTOM)
            return
        self._emit_preview()

    def _update_color_button(self, color_key: str) -> None:
        button = self._color_buttons.get(color_key)
        if button is None:
            return
        color_value = self._custom_colors.get(color_key, DEFAULT_CUSTOM_THEME_COLORS[color_key])
        button.setText(color_value)
        button.setStyleSheet(
            f"QPushButton#themeColorButton {{ background-color: {color_value}; color: {self._button_text_color(color_value)}; }}"
        )

    def _button_text_color(self, color_value: str) -> str:
        color = QColor(color_value)
        if not color.isValid():
            return "#111111"
        luminance = (0.299 * color.red()) + (0.587 * color.green()) + (0.114 * color.blue())
        return "#111111" if luminance > 160 else "#ffffff"

    def _emit_preview(self) -> None:
        theme_name = self.value()
        custom_colors = self.custom_colors() if theme_name == THEME_CUSTOM else None
        self.preview_requested.emit(theme_name, custom_colors)


class KeyboardSettingsPage(QWidget):
    def __init__(self, key_bindings: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.inputs: dict[str, ShortcutKeySequenceEdit] = {}

        title = QLabel("Keyboard Shortcuts")
        title.setObjectName("settingsPageTitle")

        form_host = QWidget()
        form = QFormLayout(form_host)
        for action_id, label in KEY_BINDING_LABELS.items():
            editor = ShortcutKeySequenceEdit(QKeySequence(key_bindings.get(action_id, "")))
            self.inputs[action_id] = editor
            form.addRow(label, editor)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(form_host)

        reset_button = QPushButton("Reset Defaults")
        reset_button.clicked.connect(self._reset_defaults)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(reset_button, alignment=Qt.AlignmentFlag.AlignLeft)

    def values(self) -> dict[str, str]:
        return {
            action_id: normalize_key_sequence(
                editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            )
            for action_id, editor in self.inputs.items()
        }

    def duplicate_shortcut(self) -> str:
        seen: set[str] = set()
        for shortcut in self.values().values():
            if not shortcut:
                continue
            if shortcut in seen:
                return shortcut
            seen.add(shortcut)
        return ""

    def _reset_defaults(self) -> None:
        for action_id, editor in self.inputs.items():
            editor.setKeySequence(QKeySequence(DEFAULT_KEY_BINDINGS[action_id]))


class SettingsDialog(QDialog):
    preview_requested = Signal(str, object)
    apply_requested = Signal()

    def __init__(
        self,
        search_mode: str,
        debounce_ms: int,
        results_page_size: int,
        show_folder_match_counts: bool,
        watch_index_changes: bool,
        keyboard_mode_enabled: bool,
        keyboard_folder_refresh: str,
        show_file_icons: bool,
        show_folder_icons: bool,
        theme_name: str,
        custom_theme_colors: dict[str, str],
        key_bindings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(760, 520)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("settingsNav")
        self.nav_list.setFixedWidth(190)
        self.nav_list.setUniformItemSizes(True)
        self.nav_list.setSpacing(SETTINGS_NAV_ITEM_SPACING)

        self.stack = QStackedWidget()
        self.stack.setObjectName("settingsStack")

        self.search_page = SearchSettingsPage(
            search_mode,
            debounce_ms,
            results_page_size,
            show_folder_match_counts,
            watch_index_changes,
            keyboard_mode_enabled,
            keyboard_folder_refresh,
        )
        self.ui_page = UISettingsPage(show_file_icons, show_folder_icons)
        self.theme_page = ThemeSettingsPage(theme_name, custom_theme_colors)
        self.theme_page.preview_requested.connect(self.preview_requested.emit)
        self.keyboard_page = KeyboardSettingsPage(key_bindings)

        pages = [
            ("Search", self.search_page),
            ("UI", self.ui_page),
            ("Theme", self.theme_page),
            ("Keyboard Shortcuts", self.keyboard_page),
        ]
        for label, page in pages:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(0, SETTINGS_NAV_ITEM_HEIGHT))
            self.nav_list.addItem(item)
            self.stack.addWidget(page)

        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._show_page)
        self._refresh_nav_layout()

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.nav_list)
        content_layout.addWidget(self.stack, stretch=1)

        button_bar = QWidget()
        button_bar.setObjectName("settingsButtons")
        button_row = QHBoxLayout(button_bar)
        button_row.setContentsMargins(12, 8, 12, 8)
        button_row.setSpacing(8)
        button_row.addStretch()

        apply_button = QPushButton("Apply")
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        for button in (apply_button, ok_button, cancel_button):
            button.setMinimumSize(73, 25)
            button_row.addWidget(button)

        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        apply_button.clicked.connect(self._on_apply_clicked)
        ok_button.setDefault(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(content_layout, stretch=1)
        layout.addWidget(button_bar)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_nav_layout)

    def _refresh_nav_layout(self) -> None:
        for row_index in range(self.nav_list.count()):
            item = self.nav_list.item(row_index)
            if item is not None:
                item.setSizeHint(QSize(0, SETTINGS_NAV_ITEM_HEIGHT))
        self.nav_list.setUniformItemSizes(True)
        self.nav_list.doItemsLayout()
        self.nav_list.viewport().update()

    def _show_page(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
        self._refresh_nav_layout()

    def _on_apply_clicked(self) -> None:
        if self._validate():
            self.apply_requested.emit()

    def _validate(self) -> bool:
        duplicate_shortcut = self.keyboard_page.duplicate_shortcut()
        if duplicate_shortcut:
            QMessageBox.warning(
                self,
                "Shortcut Conflict",
                f"'{duplicate_shortcut}' is assigned to more than one action.\n\n"
                "Please choose a different shortcut or clear one of the bindings.",
            )
            self.nav_list.setCurrentRow(3)
            return False
        return True

    def accept(self) -> None:
        if not self._validate():
            return
        super().accept()

    def search_values(self) -> tuple[str, int, int, bool, bool, bool, str]:
        return self.search_page.values()

    def ui_values(self) -> tuple[bool, bool]:
        return self.ui_page.values()

    def theme_value(self) -> str:
        return self.theme_page.value()

    def custom_theme_colors(self) -> dict[str, str]:
        return self.theme_page.custom_colors()

    def keyboard_values(self) -> dict[str, str]:
        return self.keyboard_page.values()
