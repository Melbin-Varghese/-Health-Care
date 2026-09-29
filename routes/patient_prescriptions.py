"""
routes/patient_prescriptions.py
Patient side of the medication feature:
  POST /patient/doses/{id}/respond     "consume verification" (Taken / Skipped)
  GET  /patient/prescriptions/adherence  Adherence alerts page
(The prescription list itself lives inside the patient dashboard.)
"""

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

import crud
import medication_service as svc
from dependencies import require_patient
from extensions import templates

router = APIRouter(prefix="/patient", tags=["patient-prescriptions"])


@router.post("/doses/{log_id}/respond")
def respond_to_dose(log_id: int, status: str = Form(...), patient=Depends(require_patient)):
    if status not in ("taken", "skipped"):
        raise HTTPException(status_code=400, detail="Invalid status")

    dose = crud.get_dose(log_id)
    # A patient can only verify their own doses.
    if not dose or dose["patient_id"] != patient["id"]:
        raise HTTPException(status_code=404, detail="Dose not found")

    at = svc.now()
    # ...and only once the dose is actually due (not tomorrow's).
    if svc.parse(dose["scheduled_for"]) <= at:
        if crud.update_dose_status(log_id, status, svc.fmt(at)):
            svc.check_adherence_and_alert(patient["id"], at)

    return RedirectResponse(url="/patient/dashboard#prescriptions", status_code=303)


@router.get("/prescriptions/adherence", response_class=HTMLResponse)
def adherence_alerts(request: Request, days: int = 14, patient=Depends(require_patient)):
    days = days if days in (7, 14, 30) else 14
    at = svc.now()
    return templates.TemplateResponse(
        request,
        "patient_adherence.html",
        {
            "patient": patient,
            "days": days,
            "stats": svc.adherence_for_patient(patient["id"], days, at),
            "by_medication": svc.adherence_by_medication(patient["id"], days, at),
            "recent": svc.decorate_doses(crud.list_recent_doses(patient["id"], svc.fmt(at), 15), at),
            "alerts": crud.list_alerts_for_patient(patient["id"]),
            "threshold": svc.LOW_ADHERENCE_THRESHOLD,
        },
    )