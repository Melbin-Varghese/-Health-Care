
import os
from collections import deque
import numpy as np
import cv2

BASE_DIR = os.path.dirname(__file__)

BUNDLED_CASCADE_PATH = os.path.join(BASE_DIR, "models", "haarcascade_frontalface_default.xml")

EMOTION_LABELS = ["Angry", "Disgust", "Fear", "Happy", "Sad", "Surprise", "Neutral"]
DISTRESS_EMOTIONS = {"Angry", "Disgust", "Fear", "Sad"}


def _load_face_cascade() -> cv2.CascadeClassifier:
    candidates = [BUNDLED_CASCADE_PATH]
    try:
        candidates.append(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    except Exception:
        pass  # cv2.data may not exist on some builds; that's fine, we have the bundled copy

    for path in candidates:
        if os.path.exists(path):
            cascade = cv2.CascadeClassifier(path)
            if not cascade.empty():
                return cascade

    raise RuntimeError(
        "Could not load the face-detection cascade file. Expected it at "
        f"{BUNDLED_CASCADE_PATH}. Make sure "
        "backend/models/haarcascade_frontalface_default.xml exists (it should "
        "have been included in the project) and is not corrupted/truncated."
    )


class EmotionModel:
    """Loaded once at backend startup; shared, read-only, thread-safe for
    inference (Keras predict calls are safe to call from multiple threads
    as long as they're not concurrent on the exact same call — FastAPI's
    default threadpool for sync endpoints serializes this fine)."""

    def __init__(self, model_path: str):
        from tensorflow import keras

        self.model = keras.models.load_model(model_path)
        self.face_cascade = _load_face_cascade()

    def _preprocess(self, face_gray: np.ndarray) -> np.ndarray:
        face = cv2.resize(face_gray, (48, 48), interpolation=cv2.INTER_AREA)
        face = face.astype("float32") / 255.0
        return np.expand_dims(face, axis=(0, -1))  # (1,48,48,1)

    def detect_faces(self, frame_bgr: np.ndarray):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )
        return faces, gray

    def predict_face(self, frame_bgr: np.ndarray):
        """Returns one dict for the largest detected face, or None."""
        faces, gray = self.detect_faces(frame_bgr)
        if len(faces) == 0:
            return None

        x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
        face_roi = gray[y : y + h, x : x + w]
        inp = self._preprocess(face_roi)

        probs = self.model.predict(inp, verbose=0)[0]
        idx = int(np.argmax(probs))
        return {
            "label": EMOTION_LABELS[idx],
            "confidence": float(probs[idx]),
            "probs": {EMOTION_LABELS[i]: float(probs[i]) for i in range(len(probs))},
            "box": (int(x), int(y), int(w), int(h)),
        }


class EmotionSession:
    """One per monitoring session. Wraps a shared EmotionModel and keeps
    its own short rolling history for the sustained-distress check."""

    def __init__(self, model: EmotionModel, history_len: int = 30):
        self.model = model
        self.history = deque(maxlen=history_len)

    def analyze(self, frame_bgr: np.ndarray):
        result = self.model.predict_face(frame_bgr)
        if result is not None:
            self.history.append((result["label"], result["confidence"]))
        return result

    def sustained_distress(self, min_fraction: float = 0.6, min_confidence: float = 0.45) -> bool:
        if len(self.history) < self.history.maxlen:
            return False
        hits = sum(
            1
            for label, conf in self.history
            if label in DISTRESS_EMOTIONS and conf >= min_confidence
        )
        return (hits / len(self.history)) >= min_fraction
