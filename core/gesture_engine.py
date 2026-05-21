"""Gesture engine -- validates, debounces, and converts raw gestures into actions."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from core.hand_tracker import GestureResult, GestureType


class ActionType(Enum):
    """High-level actions produced by the gesture engine."""

    NONE = "none"
    NEXT_SLIDE = "next_slide"
    PREV_SLIDE = "prev_slide"
    POINTER_MOVE = "pointer_move"
    DRAW_POINT = "draw_point"
    ERASE_LAST = "erase_last"


@dataclass
class Action:
    """A validated action ready to be executed by the UI."""

    action_type: ActionType
    position: tuple[float, float] | None = None
    confidence: float = 0.0


class GestureEngine:
    """Converts raw gesture results into debounced, validated actions.

    Responsibilities:
    - Applies per-action-type cooldown timers.
    - Requires consecutive-frame confirmation before slide navigation.
    - Implements timed hold for fist-to-erase.
    """

    def __init__(
        self,
        nav_cooldown: float = 1.0,
        fist_hold_time: float = 0.5,
        nav_confirm_frames: int = 6,
        time_source: Callable[[], float] | None = None,
    ):
        self.nav_cooldown = nav_cooldown
        self.fist_hold_time = fist_hold_time
        self.nav_confirm_frames = max(1, nav_confirm_frames)
        # Optional clock injection for offline evaluation. Production code
        # leaves this as None and the live wall clock is used; offline
        # evaluators feed in a video-timestamp callable so the cooldown
        # and fist-hold rules apply in "video time" rather than wall time.
        self._time_source = time_source

        self._last_nav_time: float = 0.0
        self._fist_start_time: float | None = None
        self._fist_triggered: bool = False
        self._nav_streak_gesture: GestureType | None = None
        self._nav_streak_count: int = 0

    def _now(self) -> float:
        if self._time_source is not None:
            return self._time_source()
        return time.time()

    def _reset_nav_streak(self) -> None:
        self._nav_streak_gesture = None
        self._nav_streak_count = 0

    def _nav_gesture_confirmed(self, nav_gesture: GestureType) -> bool:
        """Update same-gesture frame count; return True once threshold is met."""
        if self._nav_streak_gesture != nav_gesture:
            self._nav_streak_gesture = nav_gesture
            self._nav_streak_count = 1
        else:
            self._nav_streak_count = min(
                self._nav_streak_count + 1,
                self.nav_confirm_frames,
            )
        return self._nav_streak_count >= self.nav_confirm_frames

    def update(self, gesture_result: GestureResult) -> Action | None:
        """Process a gesture result and return an action if warranted."""
        now = self._now()
        gesture = gesture_result.gesture

        # --- Navigation ---
        if gesture == GestureType.PINKY_NEXT:
            self._reset_fist()
            if not self._nav_gesture_confirmed(GestureType.PINKY_NEXT):
                return None
            if now - self._last_nav_time <= self.nav_cooldown:
                return None
            self._last_nav_time = now
            self._reset_nav_streak()
            return Action(
                ActionType.NEXT_SLIDE,
                confidence=gesture_result.confidence,
            )

        if gesture == GestureType.THUMB_PREV:
            self._reset_fist()
            if not self._nav_gesture_confirmed(GestureType.THUMB_PREV):
                return None
            if now - self._last_nav_time <= self.nav_cooldown:
                return None
            self._last_nav_time = now
            self._reset_nav_streak()
            return Action(
                ActionType.PREV_SLIDE,
                confidence=gesture_result.confidence,
            )

        # --- Pointer ---
        if gesture == GestureType.POINTER:
            self._reset_fist()
            self._reset_nav_streak()
            if gesture_result.pointer_pos:
                return Action(
                    ActionType.POINTER_MOVE,
                    position=gesture_result.pointer_pos,
                    confidence=gesture_result.confidence,
                )
            return None

        # --- Draw ---
        if gesture == GestureType.DRAW:
            self._reset_fist()
            self._reset_nav_streak()
            if gesture_result.pointer_pos:
                return Action(
                    ActionType.DRAW_POINT,
                    position=gesture_result.pointer_pos,
                    confidence=gesture_result.confidence,
                )
            return None

        # --- Fist hold -> erase last stroke ---
        if gesture == GestureType.FIST:
            self._reset_nav_streak()
            if self._fist_start_time is None:
                self._fist_start_time = now
                self._fist_triggered = False
            elif (
                not self._fist_triggered
                and (now - self._fist_start_time) >= self.fist_hold_time
            ):
                self._fist_triggered = True
                return Action(
                    ActionType.ERASE_LAST,
                    confidence=gesture_result.confidence,
                )
            return None

        # --- No recognized gesture ---
        self._reset_fist()
        self._reset_nav_streak()
        return None

    def _reset_fist(self) -> None:
        self._fist_start_time = None
        self._fist_triggered = False
