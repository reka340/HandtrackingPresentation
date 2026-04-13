"""Main application window -- wires together all core and UI components."""

from __future__ import annotations

import os
import time

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_SETTINGS, FRAME_RATE_MS
from core.annotation_manager import AnnotationManager
from core.gesture_engine import ActionType, GestureEngine
from core.hand_tracker import HandTracker
from core.pdf_renderer import PdfRenderer
from ui.camera_preview import CameraPreview
from ui.gesture_indicator import GestureIndicator
from ui.settings_dialog import SettingsDialog
from ui.slide_view import SlideView
from ui.toolbar import PresentationToolbar


class MainWindow(QMainWindow):
    """Top-level window that hosts the slide view, camera preview,
    gesture indicator, toolbar, thumbnail sidebar, and status bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Presentation Helper")
        self.setMinimumSize(1024, 768)

        # Settings
        self._settings: dict = DEFAULT_SETTINGS.copy()

        # Core components
        self._hand_tracker = self._create_hand_tracker()
        self._gesture_engine = self._create_gesture_engine()
        self._pdf_renderer = PdfRenderer()
        self._annotation_manager = AnnotationManager()

        # Presentation state
        self._current_slide: int = 0
        self._is_drawing: bool = False

        # Smoothness: stroke grace period, pointer smoothing
        self._draw_lost_frames: int = 0
        self._pointer_lost_frames: int = 0
        self._last_pointer_pos: tuple[float, float] | None = None
        self._pointer_smooth_alpha: float = 0.4  # EMA: lower = smoother

        # Timer state
        self._timer_running: bool = False
        self._timer_start: float = 0.0
        self._timer_elapsed: float = 0.0

        # Camera
        self._camera: cv2.VideoCapture | None = None

        # Build the UI
        self._setup_ui()
        self._setup_keyboard_shortcuts()
        self._setup_camera()
        self._setup_timers()

        self._update_status()

    # ==================================================================
    # Factory helpers
    # ==================================================================

    def _create_hand_tracker(self) -> HandTracker:
        return HandTracker(
            min_detection_confidence=self._settings["min_detection_confidence"],
            min_tracking_confidence=self._settings["min_tracking_confidence"],
            padding_ratio=self._settings.get("frame_padding_ratio", 0.35),
        )

    def _create_gesture_engine(self) -> GestureEngine:
        return GestureEngine(
            nav_cooldown=self._settings["nav_cooldown"],
            fist_hold_time=self._settings.get("fist_hold_time", 1.5),
            nav_confirm_frames=int(
                self._settings.get("nav_confirm_frames", 6)
            ),
        )

    # ==================================================================
    # UI construction
    # ==================================================================

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left: slide thumbnails ---
        self._thumbnail_list = QListWidget()
        self._thumbnail_list.setFixedWidth(160)
        self._thumbnail_list.setIconSize(QSize(140, 105))
        self._thumbnail_list.setSpacing(4)
        self._thumbnail_list.currentRowChanged.connect(
            self._on_thumbnail_clicked
        )
        self._thumbnail_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._thumbnail_list.setObjectName("thumbnailList")

        # --- Center: slide view ---
        self._slide_view = SlideView()

        # --- Right: camera + gesture indicator ---
        right_panel = QWidget()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        self._camera_preview = CameraPreview()
        self._gesture_indicator = GestureIndicator()

        # Finger state display (small debug helper)
        self._finger_label = QLabel("")
        self._finger_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._finger_label.setFont(QFont("Consolas", 9))
        self._finger_label.setObjectName("fingerLabel")

        right_layout.addWidget(self._camera_preview)
        right_layout.addWidget(self._gesture_indicator)
        right_layout.addWidget(self._finger_label)
        right_layout.addStretch()
        right_panel.setFixedWidth(256)

        # Assemble main layout
        main_layout.addWidget(self._thumbnail_list)
        main_layout.addWidget(self._slide_view, 1)
        main_layout.addWidget(right_panel)

        # --- Toolbar ---
        self._toolbar = PresentationToolbar()
        self.addToolBar(self._toolbar)
        self._toolbar.open_pdf_requested.connect(self._open_pdf)
        self._toolbar.pen_color_changed.connect(self._on_pen_color_changed)
        self._toolbar.pen_width_changed.connect(self._on_pen_width_changed)
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.undo_requested.connect(self._undo)
        self._toolbar.redo_requested.connect(self._redo)
        self._toolbar.clear_requested.connect(self._clear_annotations)
        self._toolbar.settings_requested.connect(self._open_settings)
        self._toolbar.timer_toggle_requested.connect(self._toggle_timer)

        # --- Status bar ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._slide_label = QLabel("No PDF loaded")
        self._slide_label.setFont(QFont("Segoe UI", 10))
        self._status_bar.addWidget(self._slide_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setFixedHeight(14)
        self._progress_bar.setTextVisible(False)
        self._status_bar.addWidget(self._progress_bar)

        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._status_bar.addWidget(spacer)

        self._timer_label = QLabel("00:00:00")
        self._timer_label.setFont(QFont("Segoe UI Semibold", 12))
        self._timer_label.setObjectName("timerLabel")
        self._status_bar.addPermanentWidget(self._timer_label)

    def _setup_keyboard_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._next_slide)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._prev_slide)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._next_slide)
        QShortcut(
            QKeySequence(Qt.Key.Key_F11), self, self._toggle_fullscreen
        )
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._exit_fullscreen)

    # ==================================================================
    # Camera
    # ==================================================================

    def _setup_camera(self) -> None:
        idx = self._settings.get("camera_index", 0)
        self._camera = cv2.VideoCapture(idx)
        if not self._camera.isOpened():
            self._camera = None

    # ==================================================================
    # Timers (frame loop + presentation clock)
    # ==================================================================

    def _setup_timers(self) -> None:
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._process_frame)
        self._frame_timer.start(FRAME_RATE_MS)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_presentation_timer)
        self._clock_timer.start(500)

    # ==================================================================
    # Frame processing loop
    # ==================================================================

    def _process_frame(self) -> None:
        if self._camera is None or not self._camera.isOpened():
            return

        ret, frame = self._camera.read()
        if not ret:
            return

        frame = cv2.flip(frame, 1)

        # Hand tracking
        gesture_result = self._hand_tracker.process_frame(frame)

        # Update gesture indicator
        self._gesture_indicator.set_gesture(
            gesture_result.gesture.value, gesture_result.confidence
        )

        # Finger state debug label
        if gesture_result.finger_states:
            self._finger_label.setText(
                "Fingers: " + str(gesture_result.finger_states)
            )
        else:
            self._finger_label.setText("")

        # Camera preview with hand skeleton
        preview_frame = frame.copy()
        if gesture_result.hand_landmarks:
            preview_frame = self._hand_tracker.draw_landmarks_on_frame(
                preview_frame, gesture_result.hand_landmarks
            )
        preview_rgb = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
        self._camera_preview.update_frame(preview_rgb)

        # Gesture -> Action
        action = self._gesture_engine.update(gesture_result)
        if action:
            self._draw_lost_frames = 0
            self._pointer_lost_frames = 0
            self._handle_action(action)
        else:
            # No action - use grace period before finishing stroke
            if self._is_drawing:
                self._draw_lost_frames += 1
                if self._draw_lost_frames >= 8:  # ~267ms at 30fps
                    self._annotation_manager.finish_stroke()
                    self._is_drawing = False
                    self._draw_lost_frames = 0
                    self._update_annotations()
            else:
                self._draw_lost_frames = 0

            # Pointer: persist for a few frames, then clear
            self._pointer_lost_frames += 1
            if self._pointer_lost_frames >= 4:
                self._slide_view.set_pointer(None)
                self._last_pointer_pos = None

    # ==================================================================
    # Action handling
    # ==================================================================

    def _handle_action(self, action) -> None:
        # Finish drawing if transitioning away from draw
        if action.action_type != ActionType.DRAW_POINT and self._is_drawing:
            self._annotation_manager.finish_stroke()
            self._is_drawing = False
            self._update_annotations()

        if action.action_type == ActionType.NEXT_SLIDE:
            self._next_slide()

        elif action.action_type == ActionType.PREV_SLIDE:
            self._prev_slide()

        elif action.action_type == ActionType.POINTER_MOVE:
            pos = action.position
            if pos:
                # EMA smoothing for pointer
                if self._last_pointer_pos is not None:
                    ax, ay = self._last_pointer_pos
                    pos = (
                        self._pointer_smooth_alpha * ax + (1 - self._pointer_smooth_alpha) * pos[0],
                        self._pointer_smooth_alpha * ay + (1 - self._pointer_smooth_alpha) * pos[1],
                    )
                self._last_pointer_pos = pos
            self._slide_view.set_pointer(pos)

        elif action.action_type == ActionType.DRAW_POINT:
            self._is_drawing = True
            self._slide_view.set_pointer(None)
            if action.position:
                # EMA smoothing for drawing points
                pos = action.position
                if self._last_pointer_pos is not None:
                    ax, ay = self._last_pointer_pos
                    pos = (
                        self._pointer_smooth_alpha * ax + (1 - self._pointer_smooth_alpha) * pos[0],
                        self._pointer_smooth_alpha * ay + (1 - self._pointer_smooth_alpha) * pos[1],
                    )
                self._last_pointer_pos = pos
                self._annotation_manager.add_point(pos[0], pos[1])
                self._update_annotations()

        elif action.action_type == ActionType.ERASE_LAST:
            self._undo()

    # ==================================================================
    # Slide navigation
    # ==================================================================

    def _go_to_slide(self, index: int) -> None:
        if not self._pdf_renderer.is_loaded:
            return

        self._annotation_manager.finish_stroke()
        self._is_drawing = False

        self._current_slide = max(
            0, min(index, self._pdf_renderer.page_count - 1)
        )
        self._annotation_manager.set_slide(self._current_slide)
        self._slide_view.set_zoom(1.0)

        image = self._pdf_renderer.get_page_image(self._current_slide)
        if image:
            self._slide_view.set_slide(image)

        self._update_annotations()
        self._update_status()

        self._thumbnail_list.blockSignals(True)
        self._thumbnail_list.setCurrentRow(self._current_slide)
        self._thumbnail_list.blockSignals(False)

    def _next_slide(self) -> None:
        if self._pdf_renderer.is_loaded:
            new = min(
                self._current_slide + 1,
                self._pdf_renderer.page_count - 1,
            )
            self._go_to_slide(new)

    def _prev_slide(self) -> None:
        if self._pdf_renderer.is_loaded:
            new = max(self._current_slide - 1, 0)
            self._go_to_slide(new)

    # ==================================================================
    # Annotations
    # ==================================================================

    def _update_annotations(self) -> None:
        strokes = self._annotation_manager.get_strokes(self._current_slide)
        current = self._annotation_manager.get_current_stroke()
        self._slide_view.set_annotations(strokes, current)

    def _undo(self) -> None:
        self._annotation_manager.undo()
        self._update_annotations()

    def _redo(self) -> None:
        self._annotation_manager.redo()
        self._update_annotations()

    def _clear_annotations(self) -> None:
        self._annotation_manager.clear_slide(self._current_slide)
        self._update_annotations()

    def _on_pen_color_changed(self, color: str) -> None:
        self._annotation_manager.pen_color = color

    def _on_pen_width_changed(self, width: int) -> None:
        self._annotation_manager.pen_width = width

    def _on_tool_changed(self, tool: str) -> None:
        self._annotation_manager.tool = tool

    # ==================================================================
    # Status bar
    # ==================================================================

    def _update_status(self) -> None:
        if self._pdf_renderer.is_loaded:
            total = self._pdf_renderer.page_count
            self._slide_label.setText(
                f"  Slide {self._current_slide + 1} / {total}"
            )
            self._progress_bar.setMaximum(max(total - 1, 1))
            self._progress_bar.setValue(self._current_slide)
        else:
            self._slide_label.setText("  No PDF loaded")
            self._progress_bar.setValue(0)

    # ==================================================================
    # PDF loading
    # ==================================================================

    def _open_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Presentation",
            "",
            "PDF Files (*.pdf);;All Files (*)",
        )
        if not path:
            return

        if self._pdf_renderer.load(path):
            self._current_slide = 0
            self._annotation_manager = AnnotationManager()
            self._load_thumbnails()
            self._go_to_slide(0)
            basename = os.path.basename(path)
            self.setWindowTitle(f"Presentation Helper \u2014 {basename}")
        else:
            QMessageBox.warning(self, "Error", "Failed to load PDF file.")

    def _load_thumbnails(self) -> None:
        self._thumbnail_list.clear()
        thumb_size = QSize(140, 105)
        for i in range(self._pdf_renderer.page_count):
            thumb = self._pdf_renderer.get_page_thumbnail(i, thumb_size)
            if thumb:
                item = QListWidgetItem(QIcon(thumb), f"  {i + 1}")
                self._thumbnail_list.addItem(item)

    def _on_thumbnail_clicked(self, row: int) -> None:
        if row >= 0:
            self._go_to_slide(row)

    # ==================================================================
    # Presentation timer
    # ==================================================================

    def _toggle_timer(self) -> None:
        if self._timer_running:
            self._timer_elapsed += time.time() - self._timer_start
            self._timer_running = False
            self._toolbar.set_timer_text("Resume Timer")
        else:
            self._timer_start = time.time()
            self._timer_running = True
            self._toolbar.set_timer_text("Pause Timer")

    def _update_presentation_timer(self) -> None:
        if self._timer_running:
            elapsed = self._timer_elapsed + (time.time() - self._timer_start)
        else:
            elapsed = self._timer_elapsed
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        self._timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    # ==================================================================
    # Settings
    # ==================================================================

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        dialog.settings_changed.connect(self._apply_settings)
        dialog.exec()

    def _apply_settings(self, new_settings: dict) -> None:
        old_camera = self._settings.get("camera_index", 0)
        self._settings.update(new_settings)

        # Recreate hand tracker with new confidence values
        self._hand_tracker.release()
        self._hand_tracker = self._create_hand_tracker()

        # Recreate gesture engine with new cooldowns
        self._gesture_engine = self._create_gesture_engine()

        # Re-open camera if index changed
        new_camera = self._settings.get("camera_index", 0)
        if new_camera != old_camera:
            if self._camera:
                self._camera.release()
            self._camera = cv2.VideoCapture(new_camera)
            if not self._camera.isOpened():
                self._camera = None

    # ==================================================================
    # Fullscreen
    # ==================================================================

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def _exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showMaximized()

    # ==================================================================
    # Cleanup
    # ==================================================================

    def closeEvent(self, event) -> None:  # noqa: N802
        self._frame_timer.stop()
        self._clock_timer.stop()
        if self._camera:
            self._camera.release()
        self._hand_tracker.release()
        self._pdf_renderer.close()
        event.accept()
