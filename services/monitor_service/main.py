"""
services/monitor_service/main.py
Non-verbal patient monitor: the AI half of the "Help Signal" feature.

It only LOOKS at frames and reports what it sees (hand gesture, facial
expression, whether distress has been sustained). It does NOT decide who gets
alerted and it does NOT store anything: the main Sukham app turns these
signals into alerts in the database. Frames are decoded in memory and thrown
away; nothing is written to disk.

Run from THIS folder (the imports below are flat):
    cd services/monitor_service
    uvicorn main:app --port 8002

Needs  models/emotion_model.h5  and  models/haarcascade_frontalface_default.xml
(copy them from your old patient_monitor backend/models folder). The hand model
downloads itself on first run.

Endpoints
    POST /session/start?hold_frames=6&emotion_every_n=2  -> {"session_id": "..."}
    POST /session/{id}/analyze   body = raw JPEG bytes    -> signals (JSON)
    POST /session/{id}/stop
    GET  /health
This service has no login: keep it on 127.0.0.1 (the default) and let only the
main app talk to it.
"""

import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from emotion_detector import EmotionModel, EmotionSession
from gesture_detector import GestureDetector

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.getenv("EMOTION_MODEL_PATH", os.path.join(BASE_DIR, "models", "emotion_model.h5"))
SESSION_TIMEOUT_SECONDS = 120   # idle sessions are cleaned up
MAX_FRAME_BYTES = 2 * 1024 * 1024

_state = {"emotion_model": None}
_sessions: Dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Emotion model not found at {MODEL_PATH}")
    _state["emotion_model"] = EmotionModel(MODEL_PATH)
    print("Monitor service ready.", flush=True)
    yield
    for sess in list(_sessions.values()):
        sess["gesture_detector"].close()
    _sessions.clear()


app = FastAPI(title="Patient Monitor Service", lifespan=lifespan)


def _cleanup_stale_sessions():
    now = time.time()
    for sid in [s for s, v in _sessions.items() if now - v["last_seen"] > SESSION_TIMEOUT_SECONDS]:
        sess = _sessions.pop(sid)
        with sess["lock"]:
            sess["gesture_detector"].close()


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _state["emotion_model"] is not None,
            "active_sessions": len(_sessions)}


@app.post("/session/start")
def start_session(hold_frames: int = 6, emotion_every_n: int = 2):
    _cleanup_stale_sessions()
    hold_frames = max(2, min(hold_frames, 30))
    emotion_every_n = max(1, min(emotion_every_n, 10))
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "emotion_session": EmotionSession(_state["emotion_model"]),
        "gesture_detector": GestureDetector(hold_frames=hold_frames),
        "emotion_every_n": emotion_every_n,
        "frame_count": 0,
        "last_seen": time.time(),
        "lock": threading.Lock(),   # MediaPipe + the rolling history are not thread-safe
    }
    return {"session_id": session_id}


@app.post("/session/{session_id}/stop")
def stop_session(session_id: str):
    sess = _sessions.pop(session_id, None)
    if sess is not None:
        with sess["lock"]:
            sess["gesture_detector"].close()
    return {"status": "stopped"}


def _analyze_frame(sess: dict, frame_bytes: bytes):
    img_bgr = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img_bgr is None:
        return None
    sess["frame_count"] += 1
    gesture = sess["gesture_detector"].process(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    emotion = None
    if sess["frame_count"] % sess["emotion_every_n"] == 0:
        emotion = sess["emotion_session"].analyze(img_bgr)
    return {
        "gesture": gesture["confirmed_gesture"],
        "raw_gesture": gesture["raw_gesture"],
        "landmarks": gesture["landmarks"],
        "emotion": emotion,
        "distress": sess["emotion_session"].sustained_distress(),
        "ts": time.time(),
    }


@app.post("/session/{session_id}/analyze")
async def analyze(session_id: str, request: Request):
    sess = _sessions.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Unknown or expired session_id.")
    frame_bytes = await request.body()
    if len(frame_bytes) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="Frame too large.")

    # If the previous frame is still being processed, drop this one instead of queueing it.
    if not sess["lock"].acquire(blocking=False):
        return {"skipped": True}
    try:
        sess["last_seen"] = time.time()
        result = await run_in_threadpool(_analyze_frame, sess, frame_bytes)
    finally:
        sess["lock"].release()
    if result is None:
        raise HTTPException(status_code=400, detail="Could not decode frame as an image.")
    return result
