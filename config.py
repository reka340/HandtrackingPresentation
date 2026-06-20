"""Application-wide configuration and default settings."""

import os

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_ROOT_DIR, "resources", "hand_landmarker.task")

DEFAULT_SETTINGS = {
    "camera_index": 0,
    "min_detection_confidence": 0.7,
    "min_tracking_confidence": 0.5,
    "nav_cooldown": 1.0,
    "nav_confirm_frames": 12,
    "fist_hold_time": 1.0,
    "frame_padding_ratio": 0.35,
}

APP_NAME = "Presentation Helper"
APP_VERSION = "2.0.0"
FRAME_RATE_MS = 33
