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
    if status not in ("taken", "skipped", "missed"):
        raise HTTPException(status_code=400, detail="Invalid status")

    dose = crud.get_dose(log_id)
    # A patient can only verify their own doses.
    if not dose or dose["patient_id"] != patient["id"]:
        raise HTTPException(status_code=404, detail="Dose not found")

    at = svc.now()
    # Only today's doses can be marked (not tomorrow's).
    if svc.parse(dose["scheduled_for"]).date() != at.date():
        raise HTTPException(status_code=400, detail="Only today's doses can be marked")

    try:
        saved = crud.update_dose_status(log_id, status, svc.fmt(at))
    except Exception as exc:  # noqa: BLE001
        # If the dose_logs table has a CHECK that rejects 'missed', record it as
        # 'skipped' -- adherence treats both the same way.
        if status != "missed":
            raise
        print(f"[DOSE] could not store 'missed' ({exc}); storing 'skipped' instead", flush=True)
        saved = crud.update_dose_status(log_id, "skipped", svc.fmt(at))

    if saved:
        if status in ("missed", "skipped"):
            svc.send_missed_dose_alert(patient["id"], dose["scheduled_for"])
        # Recalculate adherence and raise the doctor alert if it dropped below the threshold.
        svc.check_adherence_and_alert(patient["id"], at)

    return RedirectResponse(url="/patient/dashboard#prescriptions", status_code=303)


@router.get("/prescriptions/adherence", response_class=HTMLResponse)
def adherence_alerts(request: Request, days: int = 7, patient=Depends(require_patient)):
    days = days if days in (7, 14, 30) else 7
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