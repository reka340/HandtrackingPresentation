"""Unit tests for ``core.annotation_manager``: ``Stroke`` and ``AnnotationManager``."""

from __future__ import annotations

import json

import pytest

from core.annotation_manager import AnnotationManager, Stroke


# ---------------------------------------------------------------------------
# Stroke
# ---------------------------------------------------------------------------


class TestStrokeInit:
    def test_default_values(self):
        s = Stroke()
        assert s.points == []
        assert s.color == "#0000FF"
        assert s.width == 3
        assert s.tool == "pen"

    def test_explicit_values(self):
        s = Stroke(
            points=[(0.1, 0.2)],
            color="#FF00AA",
            width=7,
            tool="highlighter",
        )
        assert s.points == [(0.1, 0.2)]
        assert s.color == "#FF00AA"
        assert s.width == 7
        assert s.tool == "highlighter"

    def test_default_factory_lists_are_distinct(self):
        s1 = Stroke()
        s2 = Stroke()
        s1.points.append((0.0, 0.0))
        assert s2.points == []


class TestStrokeAddPoint:
    def test_appends_in_order(self):
        s = Stroke()
        s.add_point(0.1, 0.2)
        s.add_point(0.3, 0.4)
        s.add_point(0.5, 0.6)
        assert s.points == [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)]


class TestStrokeSmooth:
    def test_smooth_is_noop_below_window(self):
        s = Stroke(points=[(0.0, 0.0), (1.0, 1.0)])
        s.smooth(window_size=3)
        assert s.points == [(0.0, 0.0), (1.0, 1.0)]

    def test_smooth_is_noop_with_zero_points(self):
        s = Stroke()
        s.smooth(window_size=3)
        assert s.points == []

    def test_smooth_averages_window_of_three(self):
        s = Stroke(points=[(0.0, 0.0), (10.0, 0.0), (0.0, 0.0), (10.0, 0.0)])
        s.smooth(window_size=3)
        assert s.points[0] == pytest.approx((5.0, 0.0))
        assert s.points[1] == pytest.approx((10 / 3, 0.0))
        assert s.points[2] == pytest.approx((20 / 3, 0.0))
        assert s.points[3] == pytest.approx((5.0, 0.0))

    def test_smooth_preserves_length(self):
        s = Stroke(points=[(float(i), 0.0) for i in range(10)])
        s.smooth(window_size=3)
        assert len(s.points) == 10

    def test_smooth_constant_signal_is_unchanged(self):
        s = Stroke(points=[(0.5, 0.5)] * 7)
        s.smooth(window_size=3)
        for p in s.points:
            assert p == pytest.approx((0.5, 0.5))


class TestStrokeSerialization:
    def test_to_dict_round_trip(self):
        s = Stroke(
            points=[(0.1, 0.2), (0.3, 0.4)],
            color="#FF00AA",
            width=5,
            tool="highlighter",
        )
        s2 = Stroke.from_dict(s.to_dict())
        assert s2.points == s.points
        assert s2.color == s.color
        assert s2.width == s.width
        assert s2.tool == s.tool

    def test_from_dict_defaults_tool_to_pen(self):
        """Legacy JSON files written before the highlighter tool existed."""
        data = {
            "points": [(0.1, 0.2)],
            "color": "#FF0000",
            "width": 4,
        }
        s = Stroke.from_dict(data)
        assert s.tool == "pen"

    def test_from_dict_converts_lists_to_tuples(self):
        """``json.load`` produces lists; ``from_dict`` should normalise to tuples."""
        data = {
            "points": [[0.1, 0.2], [0.3, 0.4]],
            "color": "#000000",
            "width": 2,
        }
        s = Stroke.from_dict(data)
        assert s.points == [(0.1, 0.2), (0.3, 0.4)]
        assert all(isinstance(p, tuple) for p in s.points)


# ---------------------------------------------------------------------------
# AnnotationManager: initial state, properties, slide management
# ---------------------------------------------------------------------------


class TestAnnotationManagerInit:
    def test_initial_state(self):
        am = AnnotationManager()
        assert am.pen_color == "#0000FF"
        assert am.pen_width == 3
        assert am.tool == "pen"
        assert am.get_strokes(0) == []
        assert am.get_strokes(99) == []
        assert am.get_current_stroke() is None


class TestAnnotationManagerProperties:
    def test_pen_color_setter(self):
        am = AnnotationManager()
        am.pen_color = "#ABCDEF"
        assert am.pen_color == "#ABCDEF"

    def test_pen_width_clamped_low(self):
        am = AnnotationManager()
        am.pen_width = 0
        assert am.pen_width == 1
        am.pen_width = -10
        assert am.pen_width == 1

    def test_pen_width_clamped_high(self):
        am = AnnotationManager()
        am.pen_width = 100
        assert am.pen_width == 20

    def test_pen_width_normal_range(self):
        am = AnnotationManager()
        am.pen_width = 7
        assert am.pen_width == 7

    def test_tool_setter_accepts_pen_and_highlighter(self):
        am = AnnotationManager()
        am.tool = "highlighter"
        assert am.tool == "highlighter"
        am.tool = "pen"
        assert am.tool == "pen"

    def test_tool_setter_silently_rejects_invalid(self):
        am = AnnotationManager()
        am.tool = "highlighter"
        am.tool = "spray"
        am.tool = ""
        am.tool = "PEN"
        assert am.tool == "highlighter"


class TestSlideManagement:
    def test_set_slide_finishes_active_stroke_on_previous_slide(self):
        am = AnnotationManager()
        am.add_point(0.1, 0.2)
        am.add_point(0.3, 0.4)
        am.set_slide(1)
        assert am.get_current_stroke() is None
        assert len(am.get_strokes(0)) == 1
        assert am.get_strokes(1) == []

    def test_strokes_isolated_per_slide(self):
        am = AnnotationManager()
        am.add_point(0.0, 0.0)
        am.add_point(0.1, 0.1)
        am.finish_stroke()
        am.set_slide(1)
        am.add_point(0.5, 0.5)
        am.add_point(0.6, 0.6)
        am.finish_stroke()
        assert len(am.get_strokes(0)) == 1
        assert len(am.get_strokes(1)) == 1
        assert am.get_strokes(0)[0].points == [(0.0, 0.0), (0.1, 0.1)]
        assert am.get_strokes(1)[0].points == [(0.5, 0.5), (0.6, 0.6)]

    def test_revisit_slide_preserves_strokes(self):
        am = AnnotationManager()
        am.add_point(0.0, 0.0)
        am.add_point(0.1, 0.1)
        am.finish_stroke()
        am.set_slide(1)
        am.set_slide(0)
        assert len(am.get_strokes(0)) == 1


# ---------------------------------------------------------------------------
# Drawing: add_point / finish_stroke
# ---------------------------------------------------------------------------


def _commit(am: AnnotationManager, *points: tuple[float, float]) -> None:
    """Helper: feed ``points`` into a single stroke and commit it."""
    for x, y in points:
        am.add_point(x, y)
    am.finish_stroke()


class TestDrawing:
    def test_add_point_creates_stroke_with_current_settings(self):
        am = AnnotationManager()
        am.pen_color = "#FF0000"
        am.pen_width = 5
        am.tool = "highlighter"
        am.add_point(0.1, 0.2)
        s = am.get_current_stroke()
        assert s is not None
        assert s.points == [(0.1, 0.2)]
        assert s.color == "#FF0000"
        assert s.width == 5
        assert s.tool == "highlighter"

    def test_subsequent_add_points_extend_same_stroke(self):
        am = AnnotationManager()
        am.add_point(0.1, 0.2)
        am.add_point(0.3, 0.4)
        s = am.get_current_stroke()
        assert s.points == [(0.1, 0.2), (0.3, 0.4)]

    def test_finish_stroke_commits_to_current_slide(self):
        am = AnnotationManager()
        am.add_point(0.1, 0.2)
        am.add_point(0.3, 0.4)
        am.finish_stroke()
        assert am.get_current_stroke() is None
        strokes = am.get_strokes(0)
        assert len(strokes) == 1
        assert strokes[0].points == [(0.1, 0.2), (0.3, 0.4)]

    def test_finish_stroke_drops_strokes_with_fewer_than_two_points(self):
        am = AnnotationManager()
        am.add_point(0.1, 0.2)
        am.finish_stroke()
        assert am.get_current_stroke() is None
        assert am.get_strokes(0) == []

    def test_finish_stroke_with_no_active_is_noop(self):
        am = AnnotationManager()
        am.finish_stroke()
        assert am.get_current_stroke() is None
        assert am.get_strokes(0) == []

    def test_back_to_back_strokes_are_separate(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        _commit(am, (0.5, 0.5), (0.6, 0.6))
        strokes = am.get_strokes(0)
        assert len(strokes) == 2
        assert strokes[0].points == [(0.0, 0.0), (0.1, 0.1)]
        assert strokes[1].points == [(0.5, 0.5), (0.6, 0.6)]

    def test_subsequent_strokes_capture_updated_settings(self):
        am = AnnotationManager()
        am.tool = "pen"
        am.pen_color = "#0000FF"
        am.pen_width = 3
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        am.tool = "highlighter"
        am.pen_color = "#FFFF00"
        am.pen_width = 8
        _commit(am, (0.2, 0.2), (0.3, 0.3))
        strokes = am.get_strokes(0)
        assert strokes[0].tool == "pen"
        assert strokes[0].color == "#0000FF"
        assert strokes[0].width == 3
        assert strokes[1].tool == "highlighter"
        assert strokes[1].color == "#FFFF00"
        assert strokes[1].width == 8

    def test_smoothing_applied_on_finish(self):
        am = AnnotationManager()
        for x in [0.0, 1.0, 0.0, 1.0, 0.0]:
            am.add_point(x, 0.0)
        am.finish_stroke()
        s = am.get_strokes(0)[0]
        assert len(s.points) == 5
        assert s.points[0] != (0.0, 0.0) or s.points[1] != (1.0, 0.0)

    def test_get_strokes_returns_a_copy(self):
        """Mutating the returned list must not affect internal state."""
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        view = am.get_strokes(0)
        view.clear()
        assert len(am.get_strokes(0)) == 1


# ---------------------------------------------------------------------------
# Undo / Redo
# ---------------------------------------------------------------------------


class TestUndoRedo:
    def test_undo_on_empty_is_noop(self):
        am = AnnotationManager()
        am.undo()
        assert am.get_strokes(0) == []

    def test_redo_on_empty_redo_stack_is_noop(self):
        am = AnnotationManager()
        am.redo()
        assert am.get_strokes(0) == []

    def test_undo_removes_last_stroke(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        _commit(am, (0.5, 0.5), (0.6, 0.6))
        am.undo()
        strokes = am.get_strokes(0)
        assert len(strokes) == 1
        assert strokes[0].points == [(0.0, 0.0), (0.1, 0.1)]

    def test_redo_restores_undone_stroke(self):
        am = AnnotationManager()
        _commit(am, (0.5, 0.5), (0.6, 0.6))
        am.undo()
        am.redo()
        strokes = am.get_strokes(0)
        assert len(strokes) == 1
        assert strokes[0].points == [(0.5, 0.5), (0.6, 0.6)]

    def test_undo_finalises_active_stroke_first(self):
        """An in-progress stroke is committed and immediately undone."""
        am = AnnotationManager()
        am.add_point(0.0, 0.0)
        am.add_point(0.1, 0.1)
        am.undo()
        assert am.get_strokes(0) == []
        assert am.get_current_stroke() is None

    def test_undo_then_redo_preserves_order(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        _commit(am, (0.2, 0.2), (0.3, 0.3))
        _commit(am, (0.4, 0.4), (0.5, 0.5))
        am.undo()
        am.undo()
        am.redo()
        am.redo()
        strokes = am.get_strokes(0)
        assert [s.points[0] for s in strokes] == [
            (0.0, 0.0),
            (0.2, 0.2),
            (0.4, 0.4),
        ]

    def test_new_stroke_clears_redo_stack(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        am.undo()
        _commit(am, (0.5, 0.5), (0.6, 0.6))
        am.redo()
        strokes = am.get_strokes(0)
        assert len(strokes) == 1
        assert strokes[0].points == [(0.5, 0.5), (0.6, 0.6)]

    def test_undo_redo_per_slide(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        am.set_slide(1)
        _commit(am, (0.5, 0.5), (0.6, 0.6))
        am.undo()
        assert am.get_strokes(1) == []
        assert len(am.get_strokes(0)) == 1
        am.set_slide(0)
        am.undo()
        assert am.get_strokes(0) == []

    def test_undo_more_times_than_strokes_is_safe(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        for _ in range(5):
            am.undo()
        assert am.get_strokes(0) == []


# ---------------------------------------------------------------------------
# clear_slide
# ---------------------------------------------------------------------------


class TestClearSlide:
    def test_clear_slide_removes_all_strokes(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        _commit(am, (0.2, 0.2), (0.3, 0.3))
        am.clear_slide(0)
        assert am.get_strokes(0) == []

    def test_clear_slide_does_not_affect_other_slides(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        am.set_slide(1)
        _commit(am, (0.5, 0.5), (0.6, 0.6))
        am.clear_slide(0)
        assert am.get_strokes(0) == []
        assert len(am.get_strokes(1)) == 1

    def test_clear_slide_clears_redo_stack(self):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        am.undo()
        am.clear_slide(0)
        am.redo()
        assert am.get_strokes(0) == []

    def test_clear_unknown_slide_is_safe(self):
        am = AnnotationManager()
        am.clear_slide(42)
        assert am.get_strokes(42) == []


# ---------------------------------------------------------------------------
# Persistence (save / load)
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_save_and_load_round_trip_preserves_all_fields(self, tmp_path):
        am = AnnotationManager()
        am.pen_color = "#FF0000"
        am.pen_width = 7
        am.tool = "highlighter"
        _commit(am, (0.1, 0.2), (0.3, 0.4))
        am.set_slide(2)
        am.tool = "pen"
        am.pen_color = "#00FF00"
        am.pen_width = 4
        _commit(am, (0.5, 0.6), (0.7, 0.8))

        path = tmp_path / "annotations.json"
        am.save(str(path))

        am2 = AnnotationManager()
        am2.load(str(path))

        s0 = am2.get_strokes(0)
        s2 = am2.get_strokes(2)
        assert len(s0) == 1
        assert s0[0].color == "#FF0000"
        assert s0[0].width == 7
        assert s0[0].tool == "highlighter"
        assert s0[0].points == [(0.1, 0.2), (0.3, 0.4)]
        assert len(s2) == 1
        assert s2[0].color == "#00FF00"
        assert s2[0].width == 4
        assert s2[0].tool == "pen"
        assert s2[0].points == [(0.5, 0.6), (0.7, 0.8)]

    def test_load_replaces_existing_strokes(self, tmp_path):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        path = tmp_path / "a.json"
        am.save(str(path))

        am2 = AnnotationManager()
        _commit(am2, (0.5, 0.5), (0.6, 0.6))
        _commit(am2, (0.7, 0.7), (0.8, 0.8))
        assert len(am2.get_strokes(0)) == 2

        am2.load(str(path))
        loaded = am2.get_strokes(0)
        assert len(loaded) == 1
        assert loaded[0].points[0] == pytest.approx((0.0, 0.0))

    def test_save_empty_manager_writes_empty_object(self, tmp_path):
        am = AnnotationManager()
        path = tmp_path / "empty.json"
        am.save(str(path))
        with open(path, encoding="utf-8") as f:
            assert json.load(f) == {}

    def test_save_omits_slides_with_no_strokes(self, tmp_path):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        am.set_slide(5)
        am.set_slide(0)
        path = tmp_path / "a.json"
        am.save(str(path))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert set(data.keys()) == {"0"}

    def test_load_legacy_file_without_tool_field(self, tmp_path):
        """A JSON file produced before the highlighter tool was added."""
        path = tmp_path / "legacy.json"
        legacy = {
            "0": [
                {
                    "points": [[0.0, 0.0], [1.0, 1.0]],
                    "color": "#0000FF",
                    "width": 3,
                }
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(legacy, f)

        am = AnnotationManager()
        am.load(str(path))
        s = am.get_strokes(0)[0]
        assert s.tool == "pen"
        assert s.points == [(0.0, 0.0), (1.0, 1.0)]

    def test_load_clears_undo_redo_history(self, tmp_path):
        am = AnnotationManager()
        _commit(am, (0.0, 0.0), (0.1, 0.1))
        am.undo()
        path = tmp_path / "a.json"
        am.save(str(path))

        am2 = AnnotationManager()
        _commit(am2, (0.5, 0.5), (0.6, 0.6))
        am2.undo()
        am2.load(str(path))
        am2.redo()
        assert am2.get_strokes(0) == []
