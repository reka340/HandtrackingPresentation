"""Hand tracking and raw gesture detection using the MediaPipe Tasks API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.components.containers import landmark as landmark_module


class GestureType(Enum):
    """Raw gesture types detected from hand landmarks."""

    NONE = "none"
    POINTER = "pointer"
    DRAW = "draw"
    THUMB_PREV = "thumb_prev"  # Thumb only -> previous slide
    PINKY_NEXT = "pinky_next"  # Pinky only -> next slide
    FIST = "fist"


@dataclass
class GestureResult:
    """Result of processing a single camera frame for hand gestures."""

    gesture: GestureType = GestureType.NONE
    pointer_pos: tuple[float, float] | None = None
    confidence: float = 0.0
    hand_landmarks: list | None = None
    finger_states: list[int] = field(default_factory=list)


# Default model path relative to the project root
_DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources",
    "hand_landmarker.task",
)


class HandTracker:
    """Wraps MediaPipe HandLandmarker (Tasks API) for real-time gesture detection.

    Detects static gestures: thumb-only (prev slide), pinky-only (next slide),
    pointer, draw, and fist.
    """

    FINGER_TIPS = [4, 8, 12, 16, 20]  # Thumb, index, middle, ring, pinky

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL_PATH,
        max_hands: int = 1,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.5,
        padding_ratio: float = 0.35,
    ):
        # Read model as bytes to avoid path-encoding issues on Windows
        with open(model_path, "rb") as f:
            model_data = f.read()
        base_options = mp_python.BaseOptions(
            model_asset_buffer=model_data,
        )
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._frame_ts: int = 0  # monotonically increasing timestamp (ms)
        self._padding_ratio = padding_ratio

    def process_frame(self, frame: np.ndarray) -> GestureResult:
        """Process a BGR camera frame and return the detected gesture.

        Applies frame padding to improve hand detection at screen edges,
        then remaps coordinates back to the original frame space.
        """
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Pad frame so hands at edges appear more centered to MediaPipe
        padded_rgb = self._pad_frame(rgb)
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB, data=padded_rgb
        )

        self._frame_ts += 33  # advance ~33ms per frame
        result = self._landmarker.detect_for_video(mp_image, self._frame_ts)

        if not result.hand_landmarks:
            return GestureResult()

        landmarks = result.hand_landmarks[0]  # first hand
        # Remap landmarks from padded frame coords to original frame coords
        landmarks = self._remap_landmarks(landmarks)

        confidence = 0.0
        if result.handedness and result.handedness[0]:
            confidence = result.handedness[0][0].score

        fingers = self._get_finger_states(landmarks)

        # Detect static gesture from finger pose
        gesture = self._detect_static_gesture(fingers)

        # Pointer / draw position (index fingertip)
        pointer_pos = None
        if gesture in (GestureType.POINTER, GestureType.DRAW):
            pointer_pos = (landmarks[8].x, landmarks[8].y)

        return GestureResult(
            gesture=gesture,
            pointer_pos=pointer_pos,
            confidence=confidence,
            hand_landmarks=landmarks,
            finger_states=fingers,
        )

    def _pad_frame(self, frame: np.ndarray) -> np.ndarray:
        """Add padding around the frame so hands at edges appear more centered.

        Uses more horizontal padding (left/right) to improve detection when
        the hand is at the sides of the frame.
        """
        h, w = frame.shape[:2]
        r = self._padding_ratio
        pad_x = int(w * r * 1.4)  # Extra horizontal padding for left/right edges
        pad_y = int(h * r)
        return cv2.copyMakeBorder(
            frame, pad_y, pad_y, pad_x, pad_x,
            cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )

    def _remap_landmarks(self, landmarks) -> list:
        """Remap landmark coordinates from padded frame to original frame.

        MediaPipe returns normalized [0,1] for the padded image. We map
        the content region back to [0,1] for the original frame.
        """
        r = self._padding_ratio
        rx = r * 1.4  # Horizontal padding factor
        ry = r
        scale_x = 1 + 2 * rx
        scale_y = 1 + 2 * ry

        def remap_x(v: float) -> float:
            return max(0.0, min(1.0, v * scale_x - rx))

        def remap_y(v: float) -> float:
            return max(0.0, min(1.0, v * scale_y - ry))

        result = []
        for lm in landmarks:
            result.append(
                landmark_module.NormalizedLandmark(
                    x=remap_x(lm.x),
                    y=remap_y(lm.y),
                    z=getattr(lm, "z", 0.0),
                    visibility=getattr(lm, "visibility", None),
                    presence=getattr(lm, "presence", None),
                )
            )
        return result

    # Finger state detection

    def _get_finger_states(self, landmarks) -> list[int]:
        """Return a list of 5 ints (0/1) indicating which fingers are extended.

        Order: [thumb, index, middle, ring, pinky].
        """
        tips = self.FINGER_TIPS
        fingers: list[int] = []

        # Thumb: compare x-coordinates (works for mirrored right-hand view)
        if landmarks[tips[0]].x < landmarks[tips[0] - 1].x:
            fingers.append(1)
        else:
            fingers.append(0)

        # Other four fingers: tip above PIP joint (lower y = higher on screen)
        for i in range(1, 5):
            if landmarks[tips[i]].y < landmarks[tips[i] - 2].y:
                fingers.append(1)
            else:
                fingers.append(0)

        return fingers

    # Static gesture mapping

    def _detect_static_gesture(self, fingers: list[int]) -> GestureType:
        """Map a finger-state vector to a static gesture type."""
        # Navigation: thumb only = prev, pinky only = next
        if fingers == [1, 0, 0, 0, 0]:
            return GestureType.THUMB_PREV
        if fingers == [0, 0, 0, 0, 1]:
            return GestureType.PINKY_NEXT
        # Pointer: index only
        if fingers == [0, 1, 0, 0, 0]:
            return GestureType.POINTER
        # Draw: index + middle
        if fingers == [0, 1, 1, 0, 0]:
            return GestureType.DRAW
        if fingers == [0, 0, 0, 0, 0]:
            return GestureType.FIST
        return GestureType.NONE

    # Drawing utilities

    def draw_landmarks_on_frame(
        self, frame: np.ndarray, landmarks
    ) -> np.ndarray:
        """Draw hand landmarks and connections on a BGR frame (in-place).

        Uses the new MediaPipe Tasks drawing utilities.
        """
        if landmarks is None:
            return frame

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        vision.drawing_utils.draw_landmarks(
            rgb_frame,
            landmarks,
            vision.HandLandmarksConnections.HAND_CONNECTIONS,
        )
        return cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)

    def release(self) -> None:
        """Release MediaPipe resources."""
        self._landmarker.close()
