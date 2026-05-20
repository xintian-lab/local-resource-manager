from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.bookmarks import BookmarkTab
from app.ui.clipboard_paths import COPY_FULL_PATH_LABEL


class ClosableTabBar(QTabBar):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("bookmarkTabBar")
        self.setMovable(True)
        self.setTabsClosable(False)
        self.setExpanding(False)
        self.setUsesScrollButtons(True)
        self.setDocumentMode(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def tabInserted(self, index: int) -> None:
        super().tabInserted(index)
        QTimer.singleShot(0, lambda: self._install_close_button(index))

    def _install_close_button(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return

        host = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if host is not None and host.objectName() == "bookmarkTabCloseHost":
            close_btn = host.findChild(QToolButton, "bookmarkTabCloseButton")
            if close_btn is not None:
                self._style_close_button(close_btn)
            return

        close_btn = QToolButton(self)
        close_btn.setObjectName("bookmarkTabCloseButton")
        close_btn.setText("×")
        close_btn.setToolTip("Close tab")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(16, 16)
        close_btn.setIcon(QIcon())
        close_btn.setAutoRaise(True)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self._emit_close_for_sender)

        host = QWidget(self)
        host.setObjectName("bookmarkTabCloseHost")
        host.setFixedWidth(18)
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 2, 0)
        host_layout.setSpacing(0)
        host_layout.addWidget(
            close_btn,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )
        host_layout.addStretch(1)

        self.setTabButton(index, QTabBar.ButtonPosition.RightSide, host)
        self._style_close_button(close_btn)

    def _style_all_close_buttons(self) -> None:
        for index in range(self.count()):
            self._install_close_button(index)

    def _style_close_button(self, button: QToolButton) -> None:
        text_color = self.palette().color(QPalette.ColorRole.WindowText)
        palette = button.palette()
        palette.setColor(QPalette.ColorRole.ButtonText, text_color)
        palette.setColor(QPalette.ColorRole.WindowText, text_color)
        button.setPalette(palette)
        font = button.font()
        font.setPointSize(11)
        font.setBold(True)
        button.setFont(font)

    def _emit_close_for_sender(self) -> None:
        button = self.sender()
        if not isinstance(button, QToolButton):
            return
        for index in range(self.count()):
            host = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if host is None:
                continue
            close_btn = host.findChild(QToolButton, "bookmarkTabCloseButton")
            if close_btn is button:
                self.tabCloseRequested.emit(index)
                return

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            index = self.tabAt(event.pos())
            if index >= 0:
                self.tabCloseRequested.emit(index)
                event.accept()
                return
        super().mousePressEvent(event)


class BookmarkTabBar(QWidget):
    current_changed = Signal(int)
    tab_clicked = Signal(int)
    tab_close_requested = Signal(int)
    tab_delete_requested = Signal(int)
    tab_delete_by_id_requested = Signal(str)
    copy_path_requested = Signal(int)
    copy_path_by_id_requested = Signal(str)
    reopen_tab_requested = Signal(str)
    new_tab_requested = Signal()
    tabs_reordered = Signal(int, int)
    rename_requested = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabs: list[BookmarkTab] = []
        self._closed_tabs: list[BookmarkTab] = []
        self._block_current_changed = False

        self.tab_bar = ClosableTabBar()
        self.tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_bar.customContextMenuRequested.connect(self._show_tab_context_menu)
        self.tab_bar.currentChanged.connect(self._handle_current_changed)
        self.tab_bar.tabBarClicked.connect(self.tab_clicked.emit)
        self.tab_bar.tabCloseRequested.connect(self.tab_close_requested.emit)
        self.tab_bar.tabMoved.connect(self._handle_tab_moved)

        self.new_tab_button = QPushButton("+")
        self.new_tab_button.setObjectName("tabBarActionButton")
        self.new_tab_button.setFixedWidth(28)
        self.new_tab_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.new_tab_button.setToolTip("New tab")
        self.new_tab_button.clicked.connect(self.new_tab_requested.emit)

        self.overflow_button = QPushButton(">>")
        self.overflow_button.setObjectName("tabBarActionButton")
        self.overflow_button.setFixedWidth(28)
        self.overflow_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.overflow_button.setToolTip("All tabs and closed bookmarks")
        self.overflow_button.setVisible(False)
        self.overflow_button.clicked.connect(self._show_overflow_popup)

        self._overflow_popup: QWidget | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.tab_bar, stretch=1)
        layout.addWidget(self.new_tab_button)
        layout.addWidget(self.overflow_button)

        self.setFixedHeight(34)

    def refresh_close_button_styles(self) -> None:
        self.tab_bar._style_all_close_buttons()

    def set_tabs(self, tabs: list[BookmarkTab]) -> None:
        self._tabs = list(tabs)
        self._rebuild_tab_bar()

    def set_closed_tabs(self, tabs: list[BookmarkTab]) -> None:
        self._closed_tabs = list(tabs)
        self._update_overflow_button()

    def tabs(self) -> list[BookmarkTab]:
        return self._tabs

    def set_current_index(self, index: int) -> None:
        if index < 0:
            return
        if index >= self.tab_bar.count():
            return
        self._block_current_changed = True
        self.tab_bar.setCurrentIndex(index)
        self._block_current_changed = False

    def current_index(self) -> int:
        return self.tab_bar.currentIndex()

    def add_tab(self, tab: BookmarkTab) -> None:
        self._tabs.append(tab)
        self._append_tab_widget(tab)
        self._update_overflow_button()

    def remove_tab(self, index: int) -> None:
        if index < 0 or index >= len(self._tabs):
            return
        self._tabs.pop(index)
        self.tab_bar.removeTab(index)
        self._update_overflow_button()

    def update_tab(self, index: int, tab: BookmarkTab) -> None:
        if index < 0 or index >= len(self._tabs):
            return
        self._tabs[index] = tab
        self.tab_bar.setTabText(index, tab.display_label())
        self.tab_bar.setTabToolTip(index, tab.tooltip())

    def move_tab(self, from_index: int, to_index: int) -> None:
        if (
            from_index < 0
            or to_index < 0
            or from_index >= len(self._tabs)
            or to_index >= len(self._tabs)
            or from_index == to_index
        ):
            return
        tab = self._tabs.pop(from_index)
        self._tabs.insert(to_index, tab)
        self._rebuild_tab_bar()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_overflow_button)

    def _rebuild_tab_bar(self) -> None:
        current_id = ""
        current = self.tab_bar.currentIndex()
        if 0 <= current < len(self._tabs):
            current_id = self._tabs[current].id

        self._block_current_changed = True
        while self.tab_bar.count():
            self.tab_bar.removeTab(0)
        for tab in self._tabs:
            self._append_tab_widget(tab)

        if current_id:
            for index, tab in enumerate(self._tabs):
                if tab.id == current_id:
                    self.tab_bar.setCurrentIndex(index)
                    break
        self._block_current_changed = False
        self._update_overflow_button()
        self.refresh_close_button_styles()

    def _append_tab_widget(self, tab: BookmarkTab) -> None:
        index = self.tab_bar.addTab(tab.display_label())
        self.tab_bar.setTabToolTip(index, tab.tooltip())
        QTimer.singleShot(0, self.refresh_close_button_styles)

    def _handle_current_changed(self, index: int) -> None:
        if self._block_current_changed or index < 0:
            return
        self.current_changed.emit(index)

    def _handle_tab_moved(self, from_index: int, to_index: int) -> None:
        if from_index == to_index:
            return
        tab = self._tabs.pop(from_index)
        self._tabs.insert(to_index, tab)
        self.tabs_reordered.emit(from_index, to_index)
        QTimer.singleShot(0, self.refresh_close_button_styles)

    def _show_tab_actions_menu(
        self,
        *,
        tab: BookmarkTab,
        visible_index: int | None,
        global_position,
    ) -> None:
        menu = QMenu(self)
        is_open = visible_index is not None and visible_index >= 0

        rename_action = None
        close_action = None
        if is_open:
            rename_action = menu.addAction("Rename Tab")
        copy_path_action = menu.addAction(COPY_FULL_PATH_LABEL)
        if is_open:
            menu.addSeparator()
            close_action = menu.addAction("Close Tab")
        delete_action = menu.addAction("Delete Tab...")

        chosen = menu.exec(global_position)
        if chosen is None:
            return
        if chosen is rename_action and is_open:
            self._rename_tab(visible_index)
        elif chosen is copy_path_action:
            if is_open:
                self.copy_path_requested.emit(visible_index)
            else:
                self.copy_path_by_id_requested.emit(tab.id)
        elif chosen is close_action and is_open:
            self.tab_close_requested.emit(visible_index)
        elif chosen is delete_action:
            if is_open:
                self.tab_delete_requested.emit(visible_index)
            else:
                self.tab_delete_by_id_requested.emit(tab.id)

    def _show_tab_context_menu(self, position) -> None:
        index = self.tab_bar.tabAt(position)
        if index < 0 or index >= len(self._tabs):
            return
        self._show_tab_actions_menu(
            tab=self._tabs[index],
            visible_index=index,
            global_position=self.tab_bar.mapToGlobal(position),
        )

    def _rename_tab(self, index: int) -> None:
        if index < 0 or index >= len(self._tabs):
            return
        tab = self._tabs[index]
        text, accepted = QInputDialog.getText(
            self,
            "Rename Tab",
            "Tab name:",
            text=tab.display_label(),
        )
        if not accepted:
            return
        cleaned = text.strip()
        if not cleaned:
            return
        self.rename_requested.emit(index, cleaned)

    def _show_overflow_popup(self) -> None:
        if not self._tabs and not self._closed_tabs:
            return

        if self._overflow_popup is not None:
            self._overflow_popup.close()

        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setObjectName("tabOverflowPopup")
        popup.setFrameShape(QFrame.Shape.StyledPanel)

        list_widget = QListWidget(popup)
        list_widget.setObjectName("tabOverflowList")
        list_widget.setMinimumWidth(240)
        list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        current = self.tab_bar.currentIndex()
        for index, tab in enumerate(self._tabs):
            label = tab.display_label()
            if index == current:
                label = f"✓ {label}"
            item = QListWidgetItem(label)
            item.setToolTip(tab.tooltip())
            item.setData(Qt.ItemDataRole.UserRole, ("open", index, tab.id))
            list_widget.addItem(item)

        if self._closed_tabs:
            if self._tabs:
                separator = QListWidgetItem("Closed bookmarks")
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                list_widget.addItem(separator)
            for tab in self._closed_tabs:
                item = QListWidgetItem(f"↺ {tab.display_label()}")
                item.setToolTip(tab.tooltip())
                item.setData(Qt.ItemDataRole.UserRole, ("closed", -1, tab.id))
                list_widget.addItem(item)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(list_widget)

        def handle_item_click(item: QListWidgetItem) -> None:
            payload = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(payload, tuple) or len(payload) != 3:
                return
            state, visible_index, tab_id = payload
            if state == "open":
                self._activate_overflow_tab(int(visible_index))
            else:
                self.reopen_tab_requested.emit(str(tab_id))
            popup.close()

        def handle_context_menu(position) -> None:
            item = list_widget.itemAt(position)
            if item is None:
                return
            payload = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(payload, tuple) or len(payload) != 3:
                return
            state, visible_index, tab_id = payload
            tab = self._find_tab_by_id(str(tab_id))
            if tab is None:
                return
            visible = int(visible_index) if state == "open" else None
            self._show_tab_actions_menu(
                tab=tab,
                visible_index=visible,
                global_position=list_widget.mapToGlobal(position),
            )

        list_widget.itemClicked.connect(handle_item_click)
        list_widget.customContextMenuRequested.connect(handle_context_menu)

        popup.adjustSize()
        anchor = self.overflow_button.mapToGlobal(self.overflow_button.rect().bottomLeft())
        popup.move(anchor)
        self._overflow_popup = popup
        popup.show()

    def _find_tab_by_id(self, tab_id: str) -> BookmarkTab | None:
        for tab in self._tabs:
            if tab.id == tab_id:
                return tab
        for tab in self._closed_tabs:
            if tab.id == tab_id:
                return tab
        return None

    def _activate_overflow_tab(self, index: int) -> None:
        self.set_current_index(index)
        self.current_changed.emit(index)

    def _update_overflow_button(self) -> None:
        if not self._tabs and not self._closed_tabs:
            self.overflow_button.setVisible(False)
            return

        if self._closed_tabs:
            self.overflow_button.setVisible(True)
            return

        total_width = 0
        for index in range(self.tab_bar.count()):
            total_width += self.tab_bar.tabRect(index).width()
        available = max(0, self.tab_bar.width() - 8)
        self.overflow_button.setVisible(total_width > available)
