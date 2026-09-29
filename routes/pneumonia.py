"""
routes/pneumonia.py
Doctor-side X-ray page. Does NOT load the AI model itself -- it forwards
the uploaded image to the standalone service in services/pneumonia_service.py
(which can run on another laptop on the same WiFi).

Point it at that service with:
    PNEUMONIA_SERVICE_URL=http://192.168.1.5:9000
Default is http://127.0.0.1:9000 (same laptop).
"""

import httpx
from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import HTMLResponse

import config
from dependencies import require_doctor
from extensions import templates

router = APIRouter(prefix="/doctor", tags=["pneumonia"])


def _render(request, doctor, result=None, error=None):
    return templates.TemplateResponse(
        request, "pneumonia.html", {"doctor": doctor, "result": result, "error": error}
    )


@router.get("/xray", response_class=HTMLResponse)
def xray_form(request: Request, doctor=Depends(require_doctor)):
    return _render(request, doctor)


@router.post("/xray", response_class=HTMLResponse)
async def xray_predict(request: Request, doctor=Depends(require_doctor), file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        return _render(request, doctor, error="Please upload a valid image file.")

    file_bytes = await file.read()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{config.PNEUMONIA_SERVICE_URL}/predict",
                files={"file": (file.filename, file_bytes, file.content_type)},
            )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        return _render(
            request, doctor,
            error=f"Cannot reach the X-ray AI service at {config.PNEUMONIA_SERVICE_URL}. "
                  "Make sure services/pneumonia_service.py is running.",
        )
    except Exception as e:
        return _render(request, doctor, error=f"Could not analyze that image: {e}")

    return _render(request, doctor, result=result)
