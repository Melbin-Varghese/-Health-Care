"""
routes/doctor_dashboard.py
Pages a logged-in doctor sees.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

import crud
from dependencies import require_doctor
from extensions import templates

router = APIRouter(prefix="/doctor", tags=["doctor-dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, doctor=Depends(require_doctor)):
    return templates.TemplateResponse(
        request, "doctor_dashboard.html",
        {"doctor": doctor, "prescriptions": crud.list_medications_for_doctor(doctor["id"])},
    )