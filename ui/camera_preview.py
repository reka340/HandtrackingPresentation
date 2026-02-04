"""Small camera-feed picture-in-picture widget."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget


class CameraPreview(QWidget):
    """Displays the live webcam feed in a small widget, including the
    MediaPipe hand skeleton overlay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame: QImage | None = None
        self.setFixedSize(240, 180)

    def update_frame(self, frame_rgb: np.ndarray) -> None:
        """Accept a RGB numpy array and queue a repaint."""
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        self._frame = QImage(
            frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
        )
        # Deep copy so the numpy buffer can be reused
        self._frame = self._frame.copy()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Rounded-rect clip
        painter.setClipRect(self.rect())

        if self._frame:
            painter.drawImage(self.rect(), self._frame)
        else:
            painter.fillRect(self.rect(), QColor("#2a2a2a"))
            painter.setPen(QColor("#888888"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No Camera"
            )

        # Border
        painter.setClipping(False)
        painter.setPen(QColor("#555555"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), 6.0, 6.0
        )

        painter.end()
