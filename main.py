from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.ui.app_icon import apply_app_icon
from app.ui.file_type_icons import FileTypeIconProvider
from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local Resource Manager")
    QTimer.singleShot(0, FileTypeIconProvider.shared().preload_common)

    window = MainWindow()
    apply_app_icon(app, window)
    window.resize(1200, 720)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
