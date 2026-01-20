"""PDF loading and rendering with page caching."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap


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
