"""
routes/patient_dashboard.py
Pages a logged-in patient sees: dashboard and profile.
"""

from datetime import timedelta

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse

import crud
import medication_service as svc
from dependencies import require_patient
from extensions import templates
from routes.patient_auth import GENDERS
from validators import PHONE_RE, parse_age

router = APIRouter(prefix="/patient", tags=["patient-dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, patient=Depends(require_patient)):
    at = svc.now()
    day_start = at.replace(hour=0, minute=0, second=0)
    day_end = day_start + timedelta(days=1)
    todays_doses = svc.decorate_doses(
        crud.list_doses_between(patient["id"], svc.fmt(day_start), svc.fmt(day_end)), at
    )
    return templates.TemplateResponse(
        request, "patient_dashboard.html",
        {
            "patient": patient,
            "medications": crud.list_medications_for_patient(patient["id"]),
            "todays_doses": todays_doses,
            "adherence": svc.adherence_for_patient(patient["id"], 7, at),
        },
    )


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, patient=Depends(require_patient)):
    return templates.TemplateResponse(
        request, "patient_profile.html",
        {"patient": patient, "profile_errors": None, "profile_success": None},
    )


@router.post("/profile/update", response_class=HTMLResponse)
def profile_update(
    request: Request,
    patient=Depends(require_patient),
    name: str = Form(...),
    phone: str = Form(...),
    age: str = Form(...),
    gender: str = Form(...),
):
    name, phone, gender = name.strip(), phone.strip(), gender.strip()

    errors = []
    if not name:
        errors.append("Name is required.")
    if not PHONE_RE.match(phone):
        errors.append("Enter a valid phone number.")

    age_val, age_error = parse_age(age.strip())
    if age_error:
        errors.append(age_error)

    if gender not in GENDERS:
        errors.append("Select a gender.")

    if errors:
        return templates.TemplateResponse(
            request, "patient_profile.html",
            {"patient": patient, "profile_errors": errors, "profile_success": None},
        )

    crud.update_patient(patient["id"], name, phone, age_val, gender)
    return RedirectResponse(url="/patient/profile", status_code=303)