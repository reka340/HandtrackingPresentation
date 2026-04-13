"""Settings dialog for camera, detection, and gesture configuration."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    """Modal dialog for editing application settings."""

    settings_changed = Signal(dict)

    def __init__(
        self, current_settings: dict, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self._settings = current_settings.copy()
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Camera ---
        camera_group = QGroupBox("Camera")
        camera_layout = QFormLayout()
        self._camera_index = QSpinBox()
        self._camera_index.setRange(0, 10)
        self._camera_index.setValue(
            self._settings.get("camera_index", 0)
        )
        camera_layout.addRow("Camera Index:", self._camera_index)
        camera_group.setLayout(camera_layout)
        layout.addWidget(camera_group)

        # --- Hand Detection ---
        detection_group = QGroupBox("Hand Detection")
        detection_layout = QFormLayout()

        self._detection_confidence, self._det_conf_label = (
            self._make_slider_row(
                30,
                100,
                int(
                    self._settings.get("min_detection_confidence", 0.7) * 100
                ),
                suffix="%",
            )
        )
        detection_layout.addRow(
            "Detection Confidence:",
            self._make_slider_widget(
                self._detection_confidence, self._det_conf_label
            ),
        )

        self._tracking_confidence, self._track_conf_label = (
            self._make_slider_row(
                30,
                100,
                int(
                    self._settings.get("min_tracking_confidence", 0.5) * 100
                ),
                suffix="%",
            )
        )
        detection_layout.addRow(
            "Tracking Confidence:",
            self._make_slider_widget(
                self._tracking_confidence, self._track_conf_label
            ),
        )

        self._frame_padding, self._frame_padding_label = (
            self._make_slider_row(
                15,
                50,
                int(
                    self._settings.get("frame_padding_ratio", 0.35) * 100
                ),
                divisor=100,
                suffix="",
            )
        )
        detection_layout.addRow(
            "Frame padding (edge detection):",
            self._make_slider_widget(
                self._frame_padding, self._frame_padding_label
            ),
        )

        detection_group.setLayout(detection_layout)
        layout.addWidget(detection_group)

        # --- Gestures ---
        gesture_group = QGroupBox("Gestures")
        gesture_layout = QFormLayout()

        self._nav_cooldown, self._nav_cd_label = self._make_slider_row(
            5,
            30,
            int(self._settings.get("nav_cooldown", 1.0) * 10),
            divisor=10,
            suffix="s",
        )
        gesture_layout.addRow(
            "Navigation Cooldown:",
            self._make_slider_widget(self._nav_cooldown, self._nav_cd_label),
        )

        self._nav_confirm_frames = QSpinBox()
        self._nav_confirm_frames.setRange(2, 30)
        self._nav_confirm_frames.setValue(
            int(self._settings.get("nav_confirm_frames", 6))
        )
        gesture_layout.addRow(
            "Navigation confirm (consecutive frames):",
            self._nav_confirm_frames,
        )

        gesture_group.setLayout(gesture_layout)
        layout.addWidget(gesture_group)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # Slider helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_slider_row(
        min_val: int,
        max_val: int,
        initial: int,
        divisor: int = 1,
        suffix: str = "",
    ) -> tuple[QSlider, QLabel]:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(initial)

        if divisor > 1:
            text = f"{initial / divisor:.{len(str(divisor)) - 1}f}{suffix}"
        else:
            text = f"{initial}{suffix}"
        label = QLabel(text)
        label.setMinimumWidth(40)

        def _on_change(v: int) -> None:
            if divisor > 1:
                label.setText(
                    f"{v / divisor:.{len(str(divisor)) - 1}f}{suffix}"
                )
            else:
                label.setText(f"{v}{suffix}")

        slider.valueChanged.connect(_on_change)
        return slider, label

    @staticmethod
    def _make_slider_widget(slider: QSlider, label: QLabel) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(slider)
        lay.addWidget(label)
        return w

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self) -> None:
        self._settings = {
            "camera_index": self._camera_index.value(),
            "min_detection_confidence": (
                self._detection_confidence.value() / 100
            ),
            "min_tracking_confidence": (
                self._tracking_confidence.value() / 100
            ),
            "nav_cooldown": self._nav_cooldown.value() / 10,
            "nav_confirm_frames": self._nav_confirm_frames.value(),
            "frame_padding_ratio": self._frame_padding.value() / 100,
        }
        self.settings_changed.emit(self._settings)
        self.accept()

    def get_settings(self) -> dict:
        return self._settings
