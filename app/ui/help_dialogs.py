from __future__ import annotations

from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.app_icon import load_app_icon
from app.version import (
    APP_NAME,
    AUTHOR_EMAIL,
    AUTHOR_NAME,
    COPYRIGHT_YEAR,
    GITHUB_REPO_URL,
    LICENSE_NAME,
    __version__,
)


def open_external_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def open_author_email() -> None:
    subject = quote(f"{APP_NAME} feedback")
    QDesktopServices.openUrl(QUrl(f"mailto:{AUTHOR_EMAIL}?subject={subject}"))


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        self.resize(420, 280)

        icon_label = QLabel()
        icon = load_app_icon()
        if not icon.isNull():
            pixmap = icon.pixmap(64, 64)
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(f"<b>{APP_NAME}</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        version_label = QLabel(f"Version {__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        copyright_label = QLabel(
            f"Copyright © {COPYRIGHT_YEAR} {AUTHOR_NAME}<br>"
            f"Licensed under the {LICENSE_NAME}."
        )
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_label.setWordWrap(True)

        description = QLabel(
            "A desktop file explorer for ultrafast local search "
            "and multi-column folder navigation."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel(
            'Keyboard shortcuts and other options are in <b>Settings</b> '
            "→ Keyboard Shortcuts."
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        repo_button = QPushButton("Open GitHub Repository")
        repo_button.clicked.connect(lambda: open_external_url(GITHUB_REPO_URL))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(icon_label)
        layout.addWidget(title)
        layout.addWidget(version_label)
        layout.addWidget(copyright_label)
        layout.addWidget(description)
        layout.addWidget(hint)
        layout.addWidget(repo_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(buttons)
