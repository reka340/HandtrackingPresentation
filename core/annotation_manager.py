"""Stroke-based annotation manager with undo/redo, multi-color, and pen smoothing."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Stroke:
    """A single drawing stroke consisting of a series of points."""

    points: list[tuple[float, float]] = field(default_factory=list)
    color: str = "#0000FF"
    width: int = 3
    tool: str = "pen"  # "pen" or "highlighter"

    def add_point(self, x: float, y: float) -> None:
        self.points.append((x, y))

    def smooth(self, window_size: int = 3) -> None:
        """Apply a moving-average filter to reduce hand jitter."""
        if len(self.points) < window_size:
            return
        smoothed: list[tuple[float, float]] = []
        half = window_size // 2
        for i in range(len(self.points)):
            start = max(0, i - half)
            end = min(len(self.points), i + half + 1)
            avg_x = sum(p[0] for p in self.points[start:end]) / (end - start)
            avg_y = sum(p[1] for p in self.points[start:end]) / (end - start)
            smoothed.append((avg_x, avg_y))
        self.points = smoothed

    def to_dict(self) -> dict:
        return {
            "points": self.points,
            "color": self.color,
            "width": self.width,
            "tool": self.tool,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Stroke:
        return cls(
            points=[tuple(p) for p in data["points"]],
            color=data["color"],
            width=data["width"],
            tool=data.get("tool", "pen"),
        )


class AnnotationManager:
    """Manages per-slide annotations with undo/redo support."""

    def __init__(self) -> None:
        self._strokes: dict[int, list[Stroke]] = defaultdict(list)
        self._redo_stack: dict[int, list[Stroke]] = defaultdict(list)
        self._current_stroke: Stroke | None = None
        self._current_slide: int = 0
        self._pen_color: str = "#0000FF"
        self._pen_width: int = 3
        self._tool: str = "pen"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def pen_color(self) -> str:
        return self._pen_color

    @pen_color.setter
    def pen_color(self, color: str) -> None:
        self._pen_color = color

    @property
    def pen_width(self) -> int:
        return self._pen_width

    @pen_width.setter
    def pen_width(self, width: int) -> None:
        self._pen_width = max(1, min(width, 20))

    @property
    def tool(self) -> str:
        return self._tool

    @tool.setter
    def tool(self, tool: str) -> None:
        if tool in ("pen", "highlighter"):
            self._tool = tool

    # ------------------------------------------------------------------
    # Slide management
    # ------------------------------------------------------------------

    def set_slide(self, slide_index: int) -> None:
        """Switch to a different slide, finishing any active stroke."""
        self.finish_stroke()
        self._current_slide = slide_index

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def add_point(self, x: float, y: float) -> None:
        """Add a point to the current stroke (starts a new stroke if needed)."""
        if self._current_stroke is None:
            self._current_stroke = Stroke(
                color=self._pen_color,
                width=self._pen_width,
                tool=self._tool,
            )
        self._current_stroke.add_point(x, y)

    def finish_stroke(self) -> None:
        """Finalize the current stroke, smooth it, and commit to history."""
        if self._current_stroke and len(self._current_stroke.points) >= 2:
            self._current_stroke.smooth()
            self._strokes[self._current_slide].append(self._current_stroke)
            # Clear redo stack on new stroke
            self._redo_stack[self._current_slide].clear()
        self._current_stroke = None

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def undo(self) -> None:
        """Undo the last completed stroke on the current slide."""
        self.finish_stroke()
        slide_strokes = self._strokes[self._current_slide]
        if slide_strokes:
            stroke = slide_strokes.pop()
            self._redo_stack[self._current_slide].append(stroke)

    def redo(self) -> None:
        """Redo the last undone stroke on the current slide."""
        self.finish_stroke()
        redo = self._redo_stack[self._current_slide]
        if redo:
            stroke = redo.pop()
            self._strokes[self._current_slide].append(stroke)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_strokes(self, slide_index: int) -> list[Stroke]:
        """Return all completed strokes for a given slide."""
        return list(self._strokes.get(slide_index, []))

    def get_current_stroke(self) -> Stroke | None:
        """Return the in-progress stroke (if any)."""
        return self._current_stroke

    def clear_slide(self, slide_index: int) -> None:
        """Remove all annotations from a slide."""
        self._strokes[slide_index].clear()
        self._redo_stack[slide_index].clear()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Export all annotations to a JSON file."""
        data: dict[str, list[dict]] = {}
        for slide_idx, strokes in self._strokes.items():
            if strokes:
                data[str(slide_idx)] = [s.to_dict() for s in strokes]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Import annotations from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._strokes.clear()
        self._redo_stack.clear()
        for slide_idx_str, strokes_data in data.items():
            slide_idx = int(slide_idx_str)
            for sd in strokes_data:
                self._strokes[slide_idx].append(Stroke.from_dict(sd))
