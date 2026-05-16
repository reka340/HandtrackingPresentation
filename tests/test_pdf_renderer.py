"""Unit tests for the annotated-PDF exporter in ``core.pdf_renderer``."""

from __future__ import annotations

import pymupdf
import pytest

from core.annotation_manager import Stroke
from core.pdf_renderer import (
    _hex_to_rgb01,
    _stroke_render_params,
    export_annotated_pdf,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_blank_pdf(path, page_count: int = 2) -> None:
    """Write a tiny multi-page PDF to ``path`` (A4 portrait, blank pages)."""
    doc = pymupdf.open()
    try:
        for _ in range(page_count):
            doc.new_page()
        doc.save(str(path))
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# _hex_to_rgb01
# ---------------------------------------------------------------------------


class TestHexToRgb01:
    def test_pure_red(self):
        assert _hex_to_rgb01("#FF0000") == pytest.approx((1.0, 0.0, 0.0))

    def test_pure_blue(self):
        assert _hex_to_rgb01("#0000FF") == pytest.approx((0.0, 0.0, 1.0))

    def test_handles_missing_hash(self):
        assert _hex_to_rgb01("00FF00") == pytest.approx((0.0, 1.0, 0.0))

    def test_malformed_falls_back_to_black(self):
        assert _hex_to_rgb01("not-a-color") == (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# _stroke_render_params
# ---------------------------------------------------------------------------


class TestStrokeRenderParams:
    def test_pen_uses_literal_width_and_full_opacity(self):
        s = Stroke(width=4, tool="pen")
        width, opacity = _stroke_render_params(s)
        assert width == pytest.approx(4.0)
        assert opacity == pytest.approx(1.0)

    def test_highlighter_inflates_width_and_dims_opacity(self):
        s = Stroke(width=3, tool="highlighter")
        width, opacity = _stroke_render_params(s)
        # max(width * 10, 18) -> 30
        assert width == pytest.approx(30.0)
        assert opacity == pytest.approx(20 / 255)

    def test_highlighter_enforces_minimum_width(self):
        s = Stroke(width=1, tool="highlighter")
        width, _ = _stroke_render_params(s)
        # max(10, 18) -> 18
        assert width == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# export_annotated_pdf
# ---------------------------------------------------------------------------


class TestExportAnnotatedPdf:
    def test_preserves_page_count(self, tmp_path):
        src = tmp_path / "in.pdf"
        dst = tmp_path / "out.pdf"
        _make_blank_pdf(src, page_count=3)

        export_annotated_pdf(str(src), str(dst), {})

        with pymupdf.open(str(dst)) as out:
            assert out.page_count == 3

    def test_pages_without_strokes_are_left_unchanged(self, tmp_path):
        """Untouched pages should contain no drawing operations after export."""
        src = tmp_path / "in.pdf"
        dst = tmp_path / "out.pdf"
        _make_blank_pdf(src, page_count=2)

        export_annotated_pdf(str(src), str(dst), {})

        with pymupdf.open(str(dst)) as out:
            for page in out:
                assert page.get_drawings() == []

    def test_strokes_are_rendered_as_vector_drawings(self, tmp_path):
        src = tmp_path / "in.pdf"
        dst = tmp_path / "out.pdf"
        _make_blank_pdf(src, page_count=2)

        strokes = {
            0: [
                Stroke(
                    points=[(0.1, 0.1), (0.5, 0.5), (0.9, 0.9)],
                    color="#FF0000",
                    width=4,
                    tool="pen",
                ),
                Stroke(
                    points=[(0.2, 0.2), (0.8, 0.2)],
                    color="#00FF00",
                    width=2,
                    tool="highlighter",
                ),
            ],
        }
        export_annotated_pdf(str(src), str(dst), strokes)

        with pymupdf.open(str(dst)) as out:
            # Page 0 got two strokes; page 1 had none.
            page0_drawings = out[0].get_drawings()
            page1_drawings = out[1].get_drawings()

            assert len(page0_drawings) == 2
            assert page1_drawings == []

            # Check that the red pen stroke kept its colour and full opacity.
            pen = next(
                d
                for d in page0_drawings
                if d.get("color") == pytest.approx((1.0, 0.0, 0.0))
            )
            assert pen.get("stroke_opacity", 1.0) == pytest.approx(1.0)

            # And the highlighter ended up translucent.
            highlighter = next(
                d
                for d in page0_drawings
                if d.get("color") == pytest.approx((0.0, 1.0, 0.0))
            )
            assert highlighter.get("stroke_opacity", 1.0) == pytest.approx(
                20 / 255
            )

    def test_strokes_with_fewer_than_two_points_are_skipped(self, tmp_path):
        src = tmp_path / "in.pdf"
        dst = tmp_path / "out.pdf"
        _make_blank_pdf(src, page_count=1)

        strokes = {0: [Stroke(points=[(0.5, 0.5)], color="#000000")]}
        export_annotated_pdf(str(src), str(dst), strokes)

        with pymupdf.open(str(dst)) as out:
            assert out[0].get_drawings() == []

    def test_unknown_slide_indices_are_ignored(self, tmp_path):
        """Strokes for pages beyond the deck shouldn't crash the export."""
        src = tmp_path / "in.pdf"
        dst = tmp_path / "out.pdf"
        _make_blank_pdf(src, page_count=1)

        strokes = {
            0: [Stroke(points=[(0.0, 0.0), (1.0, 1.0)])],
            42: [Stroke(points=[(0.0, 0.0), (1.0, 1.0)])],
        }
        export_annotated_pdf(str(src), str(dst), strokes)

        with pymupdf.open(str(dst)) as out:
            assert out.page_count == 1
            assert len(out[0].get_drawings()) == 1

    def test_missing_source_pdf_raises(self, tmp_path):
        with pytest.raises(Exception):
            export_annotated_pdf(
                str(tmp_path / "nope.pdf"),
                str(tmp_path / "out.pdf"),
                {},
            )
