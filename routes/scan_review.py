"""
routes/scan_review.py
Scan Review page: lists the available scan tools (Pneumonia, Eye, Bone ...).
Each tool has its own page/route (e.g. routes/pneumonia.py -> /doctor/xray).
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

from dependencies import require_doctor
from extensions import templates

router = APIRouter(prefix="/doctor", tags=["scan-review"])


@router.get("/scans", response_class=HTMLResponse)
def scan_review(request: Request, doctor=Depends(require_doctor)):
    return templates.TemplateResponse(request, "scan_review.html", {"doctor": doctor})