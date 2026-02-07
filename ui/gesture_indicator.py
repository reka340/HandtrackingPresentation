"""Widget that displays the currently-detected gesture and confidence level."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

GESTURE_LABELS: dict[str, tuple[str, str]] = {
    "none": ("No Gesture", "#888888"),
    "pointer": ("Pointer", "#FF6B6B"),
    "draw": ("Drawing", "#4ECDC4"),
    "pinky_next": ("Next Slide  \u2192", "#F7DC6F"),
    "thumb_prev": ("\u2190  Prev Slide", "#F7DC6F"),
    "fist": ("Hold to Erase", "#E74C3C"),
}


class GestureIndicator(QWidget):
    """Shows the active gesture name with a confidence progress bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(240, 80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self._label = QLabel("No Gesture")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._label.setStyleSheet("color: #888888; background: transparent;")

        self._confidence_bar = QProgressBar()
        self._confidence_bar.setRange(0, 100)
        self._confidence_bar.setValue(0)
        self._confidence_bar.setFixedHeight(8)
        self._confidence_bar.setTextVisible(False)

        layout.addWidget(self._label)
        layout.addWidget(self._confidence_bar)

    def set_gesture(self, gesture_name: str, confidence: float = 0.0) -> None:
        """Update the displayed gesture and confidence value."""
        label_text, color = GESTURE_LABELS.get(
            gesture_name, ("Unknown", "#888888")
        )
        self._label.setText(label_text)
        self._label.setStyleSheet(
            f"color: {color}; background: transparent;"
        )
        self._confidence_bar.setValue(int(confidence * 100))
