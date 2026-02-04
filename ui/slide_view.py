"""Slide display widget with annotation overlay and pointer."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.annotation_manager import Stroke


class SlideView(QWidget):
    """Main presentation area that renders the current slide, annotations,
    and pointer dot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._slide_image: QImage | None = None
        self._annotations: list[Stroke] = []
        self._current_stroke: Stroke | None = None
        self._pointer_pos: tuple[float, float] | None = None
        self._zoom_scale: float = 1.0

        self.setMinimumSize(640, 480)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_slide(self, image: QImage) -> None:
        self._slide_image = image
        self._pointer_pos = None
        self.update()

    def set_annotations(
        self,
        strokes: list[Stroke],
        current_stroke: Stroke | None = None,
    ) -> None:
        self._annotations = strokes
        self._current_stroke = current_stroke
        self.update()

    def set_pointer(self, pos: tuple[float, float] | None) -> None:
        self._pointer_pos = pos
        self.update()

    def set_zoom(self, scale: float) -> None:
        self._zoom_scale = max(1.0, min(scale, 3.0))
        self.update()

    @property
    def zoom_scale(self) -> float:
        return self._zoom_scale

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _get_slide_rect(self) -> QRect:
        """Compute the rectangle where the slide is drawn, centered and
        scaled to fit the widget while respecting the current zoom level."""
        if not self._slide_image:
            return QRect()

        widget_w = self.width()
        widget_h = self.height()
        img_w = self._slide_image.width()
        img_h = self._slide_image.height()

        base_scale = min(widget_w / img_w, widget_h / img_h)
        effective_scale = base_scale * self._zoom_scale

        scaled_w = int(img_w * effective_scale)
        scaled_h = int(img_h * effective_scale)
        x = (widget_w - scaled_w) // 2
        y = (widget_h - scaled_h) // 2

        return QRect(x, y, scaled_w, scaled_h)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Background
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        if not self._slide_image:
            painter.setPen(QColor("#888888"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Open a PDF to start presenting  (Ctrl+O)",
            )
            painter.end()
            return

        slide_rect = self._get_slide_rect()

        # Slide image
        painter.drawImage(slide_rect, self._slide_image)

        # Completed strokes
        for stroke in self._annotations:
            self._draw_stroke(painter, stroke, slide_rect)

        # Active (in-progress) stroke
        if self._current_stroke:
            self._draw_stroke(painter, self._current_stroke, slide_rect)

        # Pointer
        if self._pointer_pos:
            self._draw_pointer(painter, slide_rect)

        painter.end()

    def _draw_stroke(
        self, painter: QPainter, stroke: Stroke, slide_rect: QRect
    ) -> None:
        if len(stroke.points) < 2:
            return

        color = QColor(stroke.color)
        width = stroke.width
        if stroke.tool == "highlighter":
            color.setAlpha(80)
            width = stroke.width * 4

        pen = QPen(
            color,
            width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)

        for i in range(1, len(stroke.points)):
            x1 = slide_rect.x() + int(
                stroke.points[i - 1][0] * slide_rect.width()
            )
            y1 = slide_rect.y() + int(
                stroke.points[i - 1][1] * slide_rect.height()
            )
            x2 = slide_rect.x() + int(
                stroke.points[i][0] * slide_rect.width()
            )
            y2 = slide_rect.y() + int(
                stroke.points[i][1] * slide_rect.height()
            )
            painter.drawLine(x1, y1, x2, y2)

    def _draw_pointer(self, painter: QPainter, slide_rect: QRect) -> None:
        assert self._pointer_pos is not None
        px = slide_rect.x() + int(self._pointer_pos[0] * slide_rect.width())
        py = slide_rect.y() + int(self._pointer_pos[1] * slide_rect.height())

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 50, 50, 180))
        painter.drawEllipse(QPoint(px, py), 8, 8)
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawEllipse(QPoint(px, py), 3, 3)
