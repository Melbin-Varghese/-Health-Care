"""
services/pneumonia_service.py
Standalone pneumonia X-ray prediction microservice.

This is deliberately a SEPARATE FastAPI app from the main server. The main
server (routes/pneumonia.py) forwards the uploaded image to POST /predict
over HTTP, so no browser ever talks to this service directly (no CORS needed).

Run from the project root:
    uvicorn services.pneumonia_service:app --port 8000

Same machine as the main app: keep the default host (127.0.0.1).
Different laptop on the same WiFi: add  --host 0.0.0.0  and set, on the main
server,  PNEUMONIA_SERVICE_URL=http://<this-laptop-ip>:8000
(find the IP with `ipconfig` on Windows or `hostname -I` on Linux).
This service has no login, so only expose it on a network you trust.

Model location: services/models/pneumonia_efficientNet_finetuned.keras
(override with the PNEUMONIA_MODEL_PATH environment variable).
"""

import io
import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

MODEL_PATH = Path(os.getenv(
    "PNEUMONIA_MODEL_PATH",
    Path(__file__).resolve().parent / "models" / "pneumonia_efficientNet_finetuned.keras",
))
IMG_SIZE = (224, 224)
CLASS_NAMES = {0: "NORMAL", 1: "PNEUMONIA"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

_state = {"model": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Pneumonia model not found at {MODEL_PATH}")
    import tensorflow as tf  # imported here so the file can be imported without TensorFlow
    _state["model"] = tf.keras.models.load_model(MODEL_PATH)
    # Warm-up run so the first real request isn't slow.
    _state["model"].predict(np.zeros((1, *IMG_SIZE, 3), dtype=np.float32), verbose=0)
    print("Pneumonia model loaded and warmed up.", flush=True)
    yield
    _state["model"] = None


app = FastAPI(title="Pneumonia Detection Microservice", lifespan=lifespan)


def preprocess_image(file_bytes: bytes) -> np.ndarray:
    """Raw 0-255 RGB pixels, resized. The model has its own Rescaling/Normalization layers."""
    try:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="File is not a valid image.")
    arr = np.array(img.resize(IMG_SIZE), dtype=np.float32)
    return np.expand_dims(arr, axis=0)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _state["model"] is not None}


# Plain `def` (not async): FastAPI runs it in a worker thread, so the slow
# model.predict() call doesn't freeze the event loop.
@app.post("/predict")
def predict(file: UploadFile = File(...)):
    model = _state["model"]
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded yet.")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    file_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is larger than 10 MB.")

    x = preprocess_image(file_bytes)
    prob_pneumonia = float(model.predict(x, verbose=0)[0][0])
    predicted_class = 1 if prob_pneumonia >= 0.5 else 0

    # Same response shape as before, so routes/pneumonia.py needs no change.
    return {
        "filename": file.filename,
        "prediction": CLASS_NAMES[predicted_class],
        "confidence": round(
            (prob_pneumonia if predicted_class == 1 else 1 - prob_pneumonia) * 100, 2
        ),
    }
