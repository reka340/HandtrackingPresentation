"""Unit tests for ``core.gesture_engine.GestureEngine``.

Time is mocked through a ``clock`` fixture that replaces the ``time`` module
referenced by ``gesture_engine`` with a controllable fake. This lets us
exercise the cooldown and fist-hold timing rules deterministically.
"""

from __future__ import annotations

import pytest

import core.gesture_engine as ge_mod
from core.gesture_engine import ActionType, GestureEngine
from core.hand_tracker import GestureResult, GestureType


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def make_result(
    gesture: GestureType,
    *,
    pointer_pos: tuple[float, float] | None = None,
    confidence: float = 0.95,
) -> GestureResult:
    """Build a ``GestureResult`` with only the fields the engine uses."""
    return GestureResult(
        gesture=gesture,
        pointer_pos=pointer_pos,
        confidence=confidence,
    )


@pytest.fixture
def clock(monkeypatch):
    """Replace ``gesture_engine.time`` with a fake whose ``time()`` we drive."""
    state = {"now": 1000.0}

    class _FakeTime:
        @staticmethod
        def time() -> float:
            return state["now"]

    monkeypatch.setattr(ge_mod, "time", _FakeTime)

    class _Clock:
        @staticmethod
        def advance(dt: float) -> None:
            state["now"] += dt

        @staticmethod
        def now() -> float:
            return state["now"]

    return _Clock


@pytest.fixture
def engine(clock) -> GestureEngine:
    """Engine with the production defaults (cooldown=1.0s, hold=0.5s, n=6)."""
    return GestureEngine(
        nav_cooldown=1.0,
        fist_hold_time=0.5,
        nav_confirm_frames=6,
    )


def feed(engine: GestureEngine, gesture: GestureType, n: int):
    """Feed ``n`` frames of ``gesture``; return the action emitted at frame ``n``."""
    last = None
    for _ in range(n):
        last = engine.update(make_result(gesture))
    return last


# ---------------------------------------------------------------------------
# Navigation: PINKY_NEXT / THUMB_PREV with consecutive-frame confirmation
# ---------------------------------------------------------------------------


class TestNavigationConfirmation:
    def test_first_five_pinky_frames_do_not_trigger(self, engine):
        for _ in range(5):
            assert engine.update(make_result(GestureType.PINKY_NEXT)) is None

    def test_sixth_consecutive_pinky_triggers_next_slide(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is not None
        assert action.action_type == ActionType.NEXT_SLIDE

    def test_sixth_consecutive_thumb_triggers_prev_slide(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.THUMB_PREV))
        action = engine.update(make_result(GestureType.THUMB_PREV))
        assert action is not None
        assert action.action_type == ActionType.PREV_SLIDE

    def test_streak_resets_when_other_nav_gesture_intervenes(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        engine.update(make_result(GestureType.THUMB_PREV))
        for _ in range(5):
            assert engine.update(make_result(GestureType.PINKY_NEXT)) is None
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is not None
        assert action.action_type == ActionType.NEXT_SLIDE

    def test_streak_resets_on_none_gesture(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        engine.update(make_result(GestureType.NONE))
        for _ in range(5):
            assert engine.update(make_result(GestureType.PINKY_NEXT)) is None
        assert engine.update(make_result(GestureType.PINKY_NEXT)) is not None

    def test_streak_resets_on_pointer_gesture(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        engine.update(make_result(GestureType.POINTER, pointer_pos=(0.5, 0.5)))
        for _ in range(5):
            assert engine.update(make_result(GestureType.PINKY_NEXT)) is None
        assert engine.update(make_result(GestureType.PINKY_NEXT)) is not None

    def test_confidence_propagates_to_action(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT, confidence=0.42))
        action = engine.update(
            make_result(GestureType.PINKY_NEXT, confidence=0.42)
        )
        assert action.confidence == pytest.approx(0.42)

    def test_action_has_no_position(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action.position is None


# ---------------------------------------------------------------------------
# Navigation: cooldown rule (``now - last_nav_time <= cooldown`` blocks)
# ---------------------------------------------------------------------------


class TestNavigationCooldown:
    def test_cooldown_blocks_immediate_retrigger(self, clock, engine):
        feed(engine, GestureType.PINKY_NEXT, 6)
        clock.advance(0.1)
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is None

    def test_cooldown_at_exact_boundary_still_blocks(self, clock, engine):
        feed(engine, GestureType.PINKY_NEXT, 6)
        clock.advance(1.0)
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is None

    def test_cooldown_just_after_boundary_allows_retrigger(self, clock, engine):
        feed(engine, GestureType.PINKY_NEXT, 6)
        clock.advance(1.0001)
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is not None
        assert action.action_type == ActionType.NEXT_SLIDE

    def test_cooldown_is_shared_between_directions(self, clock, engine):
        """A NEXT navigation should also block an immediate PREV navigation."""
        feed(engine, GestureType.PINKY_NEXT, 6)
        clock.advance(0.5)
        for _ in range(5):
            engine.update(make_result(GestureType.THUMB_PREV))
        action = engine.update(make_result(GestureType.THUMB_PREV))
        assert action is None


# ---------------------------------------------------------------------------
# Custom navigation parameters
# ---------------------------------------------------------------------------


class TestNavigationCustomParameters:
    def test_custom_confirm_frames_two(self, clock):
        engine = GestureEngine(nav_confirm_frames=2)
        assert engine.update(make_result(GestureType.PINKY_NEXT)) is None
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is not None
        assert action.action_type == ActionType.NEXT_SLIDE

    def test_confirm_frames_clamped_to_minimum_one(self, clock):
        engine = GestureEngine(nav_confirm_frames=0)
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is not None
        assert action.action_type == ActionType.NEXT_SLIDE

    def test_negative_confirm_frames_clamped(self, clock):
        engine = GestureEngine(nav_confirm_frames=-5)
        action = engine.update(make_result(GestureType.PINKY_NEXT))
        assert action is not None


# ---------------------------------------------------------------------------
# Pointer
# ---------------------------------------------------------------------------


class TestPointer:
    def test_pointer_with_position_emits_pointer_move(self, engine):
        action = engine.update(
            make_result(GestureType.POINTER, pointer_pos=(0.3, 0.7))
        )
        assert action is not None
        assert action.action_type == ActionType.POINTER_MOVE
        assert action.position == (0.3, 0.7)

    def test_pointer_without_position_emits_nothing(self, engine):
        action = engine.update(
            make_result(GestureType.POINTER, pointer_pos=None)
        )
        assert action is None

    def test_pointer_emits_every_frame_no_cooldown(self, engine):
        for i in range(20):
            action = engine.update(
                make_result(GestureType.POINTER, pointer_pos=(0.1 * i, 0.5))
            )
            assert action is not None
            assert action.action_type == ActionType.POINTER_MOVE

    def test_pointer_resets_fist_timer(self, clock, engine):
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.4)
        engine.update(
            make_result(GestureType.POINTER, pointer_pos=(0.5, 0.5))
        )
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.4)
        action = engine.update(make_result(GestureType.FIST))
        assert action is None


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------


class TestDraw:
    def test_draw_with_position_emits_draw_point(self, engine):
        action = engine.update(
            make_result(GestureType.DRAW, pointer_pos=(0.2, 0.8))
        )
        assert action is not None
        assert action.action_type == ActionType.DRAW_POINT
        assert action.position == (0.2, 0.8)

    def test_draw_without_position_emits_nothing(self, engine):
        action = engine.update(
            make_result(GestureType.DRAW, pointer_pos=None)
        )
        assert action is None

    def test_draw_emits_every_frame_no_cooldown(self, engine):
        for i in range(10):
            action = engine.update(
                make_result(GestureType.DRAW, pointer_pos=(0.1 * i, 0.5))
            )
            assert action is not None
            assert action.action_type == ActionType.DRAW_POINT

    def test_draw_resets_nav_streak(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        engine.update(make_result(GestureType.DRAW, pointer_pos=(0.5, 0.5)))
        for _ in range(5):
            assert engine.update(make_result(GestureType.PINKY_NEXT)) is None
        assert engine.update(make_result(GestureType.PINKY_NEXT)) is not None


# ---------------------------------------------------------------------------
# Fist hold -> erase
# ---------------------------------------------------------------------------


class TestFistHold:
    def test_first_fist_frame_does_not_trigger(self, engine):
        action = engine.update(make_result(GestureType.FIST))
        assert action is None

    def test_short_hold_does_not_trigger(self, clock, engine):
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.4)
        action = engine.update(make_result(GestureType.FIST))
        assert action is None

    def test_hold_at_exact_threshold_triggers(self, clock, engine):
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.5)
        action = engine.update(make_result(GestureType.FIST))
        assert action is not None
        assert action.action_type == ActionType.ERASE_LAST

    def test_long_hold_does_not_retrigger(self, clock, engine):
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.5)
        engine.update(make_result(GestureType.FIST))
        clock.advance(2.0)
        for _ in range(5):
            assert engine.update(make_result(GestureType.FIST)) is None

    def test_release_resets_hold_timer(self, clock, engine):
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.4)
        engine.update(make_result(GestureType.NONE))
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.4)
        action = engine.update(make_result(GestureType.FIST))
        assert action is None

    def test_release_then_full_hold_triggers_again(self, clock, engine):
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.5)
        engine.update(make_result(GestureType.FIST))
        engine.update(make_result(GestureType.NONE))
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.5)
        action = engine.update(make_result(GestureType.FIST))
        assert action is not None
        assert action.action_type == ActionType.ERASE_LAST

    def test_custom_fist_hold_time(self, clock):
        engine = GestureEngine(fist_hold_time=2.0)
        engine.update(make_result(GestureType.FIST))
        clock.advance(1.0)
        assert engine.update(make_result(GestureType.FIST)) is None
        clock.advance(1.0)
        action = engine.update(make_result(GestureType.FIST))
        assert action is not None
        assert action.action_type == ActionType.ERASE_LAST


# ---------------------------------------------------------------------------
# NONE gesture and miscellaneous
# ---------------------------------------------------------------------------


class TestNoneGesture:
    def test_none_returns_none(self, engine):
        assert engine.update(make_result(GestureType.NONE)) is None

    def test_none_resets_nav_streak(self, engine):
        for _ in range(5):
            engine.update(make_result(GestureType.PINKY_NEXT))
        engine.update(make_result(GestureType.NONE))
        for _ in range(5):
            assert engine.update(make_result(GestureType.PINKY_NEXT)) is None
        assert engine.update(make_result(GestureType.PINKY_NEXT)) is not None

    def test_none_resets_fist_timer(self, clock, engine):
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.4)
        engine.update(make_result(GestureType.NONE))
        engine.update(make_result(GestureType.FIST))
        clock.advance(0.4)
        assert engine.update(make_result(GestureType.FIST)) is None
