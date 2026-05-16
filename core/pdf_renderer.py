"""PDF loading and rendering with page caching."""

from __future__ import annotations

from typing import Mapping, Sequence

import pymupdf
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap

from core.annotation_manager import Stroke


class PdfRenderer:
    """Loads a PDF file and renders pages as QImage objects with caching."""

    def __init__(self, render_zoom: float = 2.0):
        self._doc: pymupdf.Document | None = None
        self._file_path: str | None = None
        self._render_zoom = render_zoom
        self._page_cache: dict[int, QImage] = {}
        self._thumbnail_cache: dict[tuple[int, int, int], QPixmap] = {}

    def load(self, file_path: str) -> bool:
        """Open a PDF file. Returns True on success."""
        try:
            doc = pymupdf.open(file_path)
            if self._doc is not None:
                self._doc.close()
            self._doc = doc
            self._file_path = file_path
            self._page_cache.clear()
            self._thumbnail_cache.clear()
            return True
        except Exception:
            return False

    @property
    def page_count(self) -> int:
        return len(self._doc) if self._doc else 0

    @property
    def file_path(self) -> str | None:
        return self._file_path

    @property
    def is_loaded(self) -> bool:
        return self._doc is not None and len(self._doc) > 0

    def get_page_image(self, page_index: int) -> QImage | None:
        """Return a high-resolution QImage for the given page (cached)."""
        if not self._doc or not (0 <= page_index < len(self._doc)):
            return None

        if page_index in self._page_cache:
            return self._page_cache[page_index]

        page = self._doc[page_index]
        matrix = pymupdf.Matrix(self._render_zoom, self._render_zoom)
        pix = page.get_pixmap(matrix=matrix)

        qimg = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888,
        )
        # Deep copy so PyMuPDF pixmap data can be freed
        qimg = qimg.copy()

        self._page_cache[page_index] = qimg
        return qimg

    def get_page_thumbnail(
        self, page_index: int, size: QSize
    ) -> QPixmap | None:
        """Return a scaled-down thumbnail pixmap for a page."""
        cache_key = (page_index, size.width(), size.height())
        if cache_key in self._thumbnail_cache:
            return self._thumbnail_cache[cache_key]

        img = self.get_page_image(page_index)
        if img is None:
            return None

        pixmap = QPixmap.fromImage(img)
        thumb = pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumbnail_cache[cache_key] = thumb
        return thumb

    def close(self) -> None:
        """Close the PDF document and free resources."""
        if self._doc:
            self._doc.close()
            self._doc = None
        self._page_cache.clear()
        self._thumbnail_cache.clear()


# ---------------------------------------------------------------------------
# Annotated-PDF export
# ---------------------------------------------------------------------------


def _hex_to_rgb01(color: str) -> tuple[float, float, float]:
    """Convert a ``#RRGGBB`` string to a 0..1 RGB tuple for PyMuPDF."""
    c = color.lstrip("#")
    if len(c) != 6:
        # Fall back to black for malformed colors rather than crashing the export.
        return (0.0, 0.0, 0.0)
    r = int(c[0:2], 16) / 255.0
    g = int(c[2:4], 16) / 255.0
    b = int(c[4:6], 16) / 255.0
    return (r, g, b)


def _stroke_render_params(
    stroke: Stroke,
) -> tuple[float, float]:
    """Return (width_in_points, stroke_opacity) for a given stroke.

    Mirrors the on-screen rendering rules in ``SlideView``: highlighters are
    drawn much thicker and almost transparent; pens are opaque at their
    configured width.
    """
    if stroke.tool == "highlighter":
        return float(max(stroke.width * 10, 18)), 20.0 / 255.0
    return float(stroke.width), 1.0


def _draw_stroke_on_page(page: "pymupdf.Page", stroke: Stroke) -> None:
    """Overlay a single ``Stroke`` onto ``page`` as a vector polyline."""
    if len(stroke.points) < 2:
        return

    page_w = page.rect.width
    page_h = page.rect.height
    pts = [
        pymupdf.Point(nx * page_w, ny * page_h) for nx, ny in stroke.points
    ]

    width_pt, opacity = _stroke_render_params(stroke)
    color = _hex_to_rgb01(stroke.color)

    shape = page.new_shape()
    shape.draw_polyline(pts)
    shape.finish(
        color=color,
        width=width_pt,
        closePath=False,
        lineCap=1,   # round
        lineJoin=1,  # round
        stroke_opacity=opacity,
        fill=None,
    )
    shape.commit()


def export_annotated_pdf(
    src_path: str,
    dest_path: str,
    strokes_per_slide: Mapping[int, Sequence[Stroke]],
) -> None:
    """Write a new PDF at ``dest_path`` containing the pages of ``src_path``
    with the supplied strokes burned in on top of each page.

    Strokes are vector overlays (not raster), so the original page content
    keeps its full quality. Pages with no strokes are copied unchanged.

    Raises ``OSError`` (or PyMuPDF's exceptions) on I/O failure.
    """
    src = pymupdf.open(src_path)
    try:
        out = pymupdf.open()
        try:
            out.insert_pdf(src)
            for page_index in range(out.page_count):
                strokes = strokes_per_slide.get(page_index) or ()
                if not strokes:
                    continue
                page = out[page_index]
                for stroke in strokes:
                    _draw_stroke_on_page(page, stroke)
            out.save(dest_path, garbage=4, deflate=True)
        finally:
            out.close()
    finally:
        src.close()
