"""
services/pneumonia_service.py
Standalone pneumonia X-ray prediction microservice.

This is deliberately a SEPARATE FastAPI app from the main server --
run it on its own (even on a different laptop on the same WiFi), and
the main server's /doctor/xray page will call it over HTTP.

Run on THIS laptop with:
    uvicorn pneumonia_service:app --host 0.0.0.0 --port 9000

--host 0.0.0.0 is required so other devices on the WiFi can reach it
(127.0.0.1 only accepts connections from the same machine).

Find this laptop's local IP (to give to the main server):
    Windows : ipconfig            -> look for "IPv4 Address"
    Mac/Linux: ifconfig | hostname -I

Then on the MAIN server laptop, set:
    PNEUMONIA_SERVICE_URL=http://<this-laptop-ip>:9000
before starting main.py (see routers/pneumonia.py).
"""

import io

import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

MODEL_PATH = "pneumonia_efficientNet_finetuned.keras"
IMG_SIZE = (224, 224)
CLASS_NAMES = {0: "NORMAL", 1: "PNEUMONIA"}

app = FastAPI(title="Pneumonia Detection Microservice")

# Wide-open CORS: this service may be called from a browser on a
# different machine (the main server's frontend), so it needs to
# accept cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model = None


@app.on_event("startup")
def load_model():
    global model
    import tensorflow as tf
    model = tf.keras.models.load_model(MODEL_PATH)
    dummy = np.zeros((1, IMG_SIZE[0], IMG_SIZE[1], 3), dtype=np.float32)
    model.predict(dummy, verbose=0)
    print("Pneumonia model loaded and warmed up.")


def preprocess_image(file_bytes: bytes) -> np.ndarray:
    try:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="File is not a valid image.")
    img = img.resize(IMG_SIZE)
    arr = np.array(img, dtype=np.float32)
    return np.expand_dims(arr, axis=0)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    file_bytes = await file.read()
    x = preprocess_image(file_bytes)

    prob_pneumonia = float(model.predict(x, verbose=0)[0][0])
    predicted_class = 1 if prob_pneumonia >= 0.5 else 0

    return {
        "filename": file.filename,
        "prediction": CLASS_NAMES[predicted_class],
        "confidence": round(
            (prob_pneumonia if predicted_class == 1 else 1 - prob_pneumonia) * 100, 2
        ),
    }