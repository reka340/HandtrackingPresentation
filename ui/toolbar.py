"""Presentation toolbar with drawing tools, undo/redo, timer, and settings."""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolBar,
    QWidget,
)


class PresentationToolbar(QToolBar):
    """Top toolbar with file, drawing-tool, undo/redo, and timer controls."""

    pen_color_changed = Signal(str)
    pen_width_changed = Signal(int)
    tool_changed = Signal(str)
    undo_requested = Signal()
    redo_requested = Signal()
    clear_requested = Signal()
    open_pdf_requested = Signal()
    save_annotated_pdf_requested = Signal()
    settings_requested = Signal()
    timer_toggle_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Tools", parent)
        self.setMovable(False)
        self.setIconSize(QSize(24, 24))
        self._pen_color = "#0000FF"
        self._setup_actions()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_actions(self) -> None:
        # --- Open PDF ---
        self._open_action = QAction("Open PDF", self)
        self._open_action.setShortcut("Ctrl+O")
        self._open_action.triggered.connect(self.open_pdf_requested.emit)
        self.addAction(self._open_action)

        # --- Save annotated PDF ---
        self._save_pdf_action = QAction("Save Annotated PDF", self)
        self._save_pdf_action.setShortcut("Ctrl+S")
        self._save_pdf_action.setToolTip(
            "Save a copy of the PDF with all drawn annotations baked in"
            " (Ctrl+S)"
        )
        self._save_pdf_action.triggered.connect(
            self.save_annotated_pdf_requested.emit
        )
        self.addAction(self._save_pdf_action)

        self.addSeparator()

        # --- Tool selector ---
        tool_widget = QWidget()
        tool_layout = QHBoxLayout(tool_widget)
        tool_layout.setContentsMargins(4, 0, 4, 0)

        tool_label = QLabel("Tool:")
        self._tool_combo = QComboBox()
        self._tool_combo.addItems(["Pen", "Highlighter"])
        self._tool_combo.currentTextChanged.connect(
            lambda t: self.tool_changed.emit(t.lower())
        )
        tool_layout.addWidget(tool_label)
        tool_layout.addWidget(self._tool_combo)
        self.addWidget(tool_widget)

        # --- Color picker ---
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(28, 28)
        self._update_color_swatch()
        self._color_btn.clicked.connect(self._pick_color)
        self._color_btn.setToolTip("Pen Color")
        self.addWidget(self._color_btn)

        # --- Pen width ---
        width_widget = QWidget()
        width_layout = QHBoxLayout(width_widget)
        width_layout.setContentsMargins(4, 0, 4, 0)
        width_label = QLabel("Width:")
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 20)
        self._width_spin.setValue(3)
        self._width_spin.valueChanged.connect(self.pen_width_changed.emit)
        width_layout.addWidget(width_label)
        width_layout.addWidget(self._width_spin)
        self.addWidget(width_widget)

        self.addSeparator()

        # --- Undo / Redo / Clear ---
        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut("Ctrl+Z")
        self._undo_action.triggered.connect(self.undo_requested.emit)
        self.addAction(self._undo_action)

        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut("Ctrl+Y")
        self._redo_action.triggered.connect(self.redo_requested.emit)
        self.addAction(self._redo_action)

        self._clear_action = QAction("Clear Slide", self)
        self._clear_action.triggered.connect(self.clear_requested.emit)
        self.addAction(self._clear_action)

        self.addSeparator()

        # --- Timer toggle ---
        self._timer_action = QAction("Start Timer", self)
        self._timer_action.triggered.connect(self.timer_toggle_requested.emit)
        self.addAction(self._timer_action)

        # --- Spacer ---
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.addWidget(spacer)

        # --- Settings ---
        self._settings_action = QAction("Settings", self)
        self._settings_action.triggered.connect(self.settings_requested.emit)
        self.addAction(self._settings_action)

    # ------------------------------------------------------------------
    # Color handling
    # ------------------------------------------------------------------

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self._pen_color), self, "Select Pen Color"
        )
        if color.isValid():
            self._pen_color = color.name()
            self._update_color_swatch()
            self.pen_color_changed.emit(self._pen_color)

    def _update_color_swatch(self) -> None:
        pixmap = QPixmap(24, 24)
        pixmap.fill(QColor(self._pen_color))
        self._color_btn.setIcon(QIcon(pixmap))

    # ------------------------------------------------------------------
    # Timer label
    # ------------------------------------------------------------------

    def set_timer_text(self, text: str) -> None:
        self._timer_action.setText(text)
