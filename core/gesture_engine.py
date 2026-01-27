"""Gesture engine -- validates, debounces, and converts raw gestures into actions."""

from __future__ import annotations

import time
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
    - Implements timed hold for fist-to-erase.
    """

    def __init__(
        self,
        nav_cooldown: float = 1.0,
        fist_hold_time: float = 0.5,
    ):
        self.nav_cooldown = nav_cooldown
        self.fist_hold_time = fist_hold_time

        self._last_nav_time: float = 0.0
        self._fist_start_time: float | None = None
        self._fist_triggered: bool = False

    def update(self, gesture_result: GestureResult) -> Action | None:
        """Process a gesture result and return an action if warranted."""
        now = time.time()
        gesture = gesture_result.gesture

        # --- Navigation ---
        if gesture == GestureType.PINKY_NEXT:
            self._reset_fist()
            if now - self._last_nav_time > self.nav_cooldown:
                self._last_nav_time = now
                return Action(
                    ActionType.NEXT_SLIDE,
                    confidence=gesture_result.confidence,
                )
            return None

        if gesture == GestureType.THUMB_PREV:
            self._reset_fist()
            if now - self._last_nav_time > self.nav_cooldown:
                self._last_nav_time = now
                return Action(
                    ActionType.PREV_SLIDE,
                    confidence=gesture_result.confidence,
                )
            return None

        # --- Pointer ---
        if gesture == GestureType.POINTER:
            self._reset_fist()
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
            if gesture_result.pointer_pos:
                return Action(
                    ActionType.DRAW_POINT,
                    position=gesture_result.pointer_pos,
                    confidence=gesture_result.confidence,
                )
            return None

        # --- Fist hold -> erase last stroke ---
        if gesture == GestureType.FIST:
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
        return None

    def _reset_fist(self) -> None:
        self._fist_start_time = None
        self._fist_triggered = False
