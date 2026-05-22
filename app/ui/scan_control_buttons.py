from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPalette, QPolygonF
from PySide6.QtWidgets import QPushButton


def _button_background_color(button: QPushButton) -> QColor | None:
    if not button.isEnabled():
        return None
    palette = button.palette()
    if button.isDown():
        return palette.color(QPalette.ColorRole.Mid)
    if button.underMouse():
        return palette.color(QPalette.ColorRole.AlternateBase)
    return None


class ScanPlayButton(QPushButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scanPlayButton")
        self.setFixedSize(28, 28)
        self.setToolTip("Scan root folder")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFlat(True)

    def sizeHint(self) -> QSize:
        return QSize(28, 28)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        try:
            background = _button_background_color(self)
            if background is not None:
                painter.fillRect(self.rect(), background)

            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            size = min(self.width(), self.height())
            painter.translate((self.width() - size) / 2, (self.height() - size) / 2)
            color = QColor("#2ecc71") if self.isEnabled() else QColor("#6b8f74")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            inset = size * 0.28
            triangle = QPolygonF(
                [
                    QPointF(inset, inset),
                    QPointF(size - inset, size * 0.5),
                    QPointF(inset, size - inset),
                ]
            )
            painter.drawPolygon(triangle)
        finally:
            painter.end()


class ScanStopButton(QPushButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scanStopButton")
        self.setFixedSize(28, 28)
        self.setToolTip("Stop scan and background tasks")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFlat(True)

    def sizeHint(self) -> QSize:
        return QSize(28, 28)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        try:
            background = _button_background_color(self)
            if background is not None:
                painter.fillRect(self.rect(), background)

            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            size = min(self.width(), self.height())
            painter.translate((self.width() - size) / 2, (self.height() - size) / 2)
            color = QColor("#e74c3c") if self.isEnabled() else QColor("#8f6b6b")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            center = size * 0.5
            radius = size * 0.34
            sides = 8
            points = QPolygonF()
            for index in range(sides):
                angle = (index / sides) * (2 * math.pi) - (math.pi / 8)
                points.append(
                    QPointF(
                        center + radius * math.cos(angle),
                        center + radius * math.sin(angle),
                    )
                )
            painter.drawPolygon(points)
        finally:
            painter.end()
