"""
gesture_detector.py
--------------------
Recognizes 3 simple, low-effort hand gestures for patients with limited
motor ability (e.g. a hand that can still be raised or curled slightly,
even if speech/full movement isn't possible):

    Open palm (5 fingers extended)  -> "I'M OK"
    One finger raised               -> "NEED HELP"
    Closed fist (0 fingers)         -> "EMERGENCY"

Built on MediaPipe's Hand Landmarker task (21 hand landmarks). A gesture
must be held steadily for a configurable number of consecutive frames
before it is "confirmed", to avoid false alarms from a hand briefly
passing through frame.

On first run this downloads the small (~7MB) hand_landmarker.task model
file from Google's public model store into ./models/. This requires
internet access once; after that it is cached locally.
"""

import os
import urllib.request
from collections import deque

import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python import BaseOptions

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "hand_landmarker.task")

# Landmark indices (MediaPipe hand model)
FINGER_TIPS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
FINGER_PIPS = {"index": 6, "middle": 10, "ring": 14, "pinky": 18}
THUMB_TIP, THUMB_IP, THUMB_MCP = 4, 3, 2
WRIST = 0

GESTURE_OK = "I'M OK"
GESTURE_HELP = "NEED HELP"
GESTURE_EMERGENCY = "EMERGENCY"
GESTURE_NONE = "NO GESTURE"


def _ensure_model():
    os.makedirs(MODEL_DIR, exist_ok=True)
    if not os.path.exists(MODEL_PATH):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def _count_extended_fingers(landmarks, handedness_label: str) -> int:
    """
    landmarks: list of 21 (x, y, z) normalized points.
    Returns how many of the 5 fingers are extended, using simple
    geometric rules (tip further from palm than the lower joint).
    """
    count = 0

    # 4 fingers: tip above (smaller y, image coords) the pip joint = extended.
    for name in ("index", "middle", "ring", "pinky"):
        tip_y = landmarks[FINGER_TIPS[name]][1]
        pip_y = landmarks[FINGER_PIPS[name]][1]
        if tip_y < pip_y - 0.02:
            count += 1

    # Thumb: compare x position relative to its own MCP joint, direction
    # depends on which hand (mirrored) is showing.
    thumb_tip_x = landmarks[THUMB_TIP][0]
    thumb_mcp_x = landmarks[THUMB_MCP][0]
    if handedness_label == "Right":
        if thumb_tip_x < thumb_mcp_x - 0.02:
            count += 1
    else:  # "Left" (or unknown, default to same rule)
        if thumb_tip_x > thumb_mcp_x + 0.02:
            count += 1

    return count


def _finger_count_to_gesture(n_fingers: int) -> str:
    if n_fingers == 0:
        return GESTURE_EMERGENCY
    if n_fingers == 1:
        return GESTURE_HELP
    if n_fingers >= 4:
        return GESTURE_OK
    return GESTURE_NONE  # 2-3 fingers = ambiguous, ignored on purpose


class GestureDetector:
    def __init__(self, hold_frames: int = 8, max_hands: int = 1):
        """
        hold_frames: how many consecutive frames a gesture must be seen
                     before it counts as "confirmed" (debounce).
        """
        model_path = _ensure_model()
        options = mp_vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            num_hands=max_hands,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        self.landmarker = mp_vision.HandLandmarker.create_from_options(options)
        self.hold_frames = hold_frames
        self._recent = deque(maxlen=hold_frames)
        self.confirmed_gesture = GESTURE_NONE

    def process(self, frame_rgb: np.ndarray):
        """
        frame_rgb: HxWx3 uint8 RGB frame.
        Returns dict: {raw_gesture, confirmed_gesture, landmarks, handedness}
        landmarks is None if no hand was found this frame.
        """
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self.landmarker.detect(mp_image)

        raw_gesture = GESTURE_NONE
        landmarks_xy = None
        handedness_label = None

        if result.hand_landmarks:
            hand = result.hand_landmarks[0]
            landmarks_xy = [(lm.x, lm.y, lm.z) for lm in hand]
            handedness_label = "Right"
            if result.handedness and result.handedness[0]:
                handedness_label = result.handedness[0][0].category_name
            n_fingers = _count_extended_fingers(landmarks_xy, handedness_label)
            raw_gesture = _finger_count_to_gesture(n_fingers)

        self._recent.append(raw_gesture)

        # Confirm only if the buffer is full and every recent reading agrees.
        if len(self._recent) == self.hold_frames and len(set(self._recent)) == 1:
            self.confirmed_gesture = self._recent[0]
        elif raw_gesture == GESTURE_NONE and self._recent.count(GESTURE_NONE) > self.hold_frames // 2:
            self.confirmed_gesture = GESTURE_NONE

        return {
            "raw_gesture": raw_gesture,
            "confirmed_gesture": self.confirmed_gesture,
            "landmarks": landmarks_xy,
            "handedness": handedness_label,
        }

    def close(self):
        self.landmarker.close()
