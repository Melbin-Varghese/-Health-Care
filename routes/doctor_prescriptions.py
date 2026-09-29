"""
routes/doctor_prescriptions.py
Doctor -> Prescriptions:
  /doctor/prescriptions             Add-medication page (+ what this doctor prescribed recently)
  /doctor/prescriptions/add         form POST
  /doctor/prescriptions/adherence   Adherence alerts page
"""

import re
from datetime import date
from urllib.parse import quote
from typing import List, Optional

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

import crud
import medication_service as svc
from dependencies import require_doctor
from extensions import templates

router = APIRouter(prefix="/doctor/prescriptions", tags=["doctor-prescriptions"])

FREQUENCIES = ["Once daily", "Twice daily", "Three times daily", "Four times daily", "Every night", "As directed"]
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_DOSES_PER_DAY = 6
DEFAULT_TIMES = ["08:00", "20:00"]


def _render(request, doctor, *, form=None, errors=None, added=None):
    form = form or {}
    return templates.TemplateResponse(
        request,
        "doctor_prescriptions.html",
        {
            "doctor": doctor,
            "patients": crud.list_patients(),
            "frequencies": FREQUENCIES,
            "form": form,
            "dose_times": form.get("dose_times") or DEFAULT_TIMES,
            "today": date.today().isoformat(),
            "errors": errors or [],
            "added": added,
            "prescriptions": crud.list_medications_for_doctor(doctor["id"], limit=8),
            "active_tab": "add",
        },
    )


@router.get("", response_class=HTMLResponse)
def add_medication_page(
    request: Request,
    patient_id: Optional[int] = None,
    added: Optional[str] = None,
    doctor=Depends(require_doctor),
):
    form = {"patient_id": patient_id} if patient_id else {}
    return _render(request, doctor, form=form, added=added)


@router.post("/add", response_class=HTMLResponse)
def add_medication(
    request: Request,
    doctor=Depends(require_doctor),
    patient_id: Optional[int] = Form(None),
    drug_name: str = Form(""),
    dosage: str = Form(""),
    frequency: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    dose_times: List[str] = Form([]),
):
    drug_name, dosage, frequency = drug_name.strip(), dosage.strip(), frequency.strip()
    end_date = end_date.strip()
    times = sorted({t.strip() for t in dose_times if t.strip()})
    form = dict(patient_id=patient_id, drug_name=drug_name, dosage=dosage, frequency=frequency,
                start_date=start_date, end_date=end_date, dose_times=times or DEFAULT_TIMES)

    errors = []
    if not patient_id or not crud.get_patient_by_id(patient_id):
        errors.append("Select a valid patient.")
    if not drug_name or len(drug_name) > 150:
        errors.append("Enter the drug name (max 150 characters).")
    if not dosage or len(dosage) > 50:
        errors.append("Enter the dosage, e.g. 500mg (max 50 characters).")
    if not frequency or len(frequency) > 50:
        errors.append("Enter the frequency, e.g. Twice daily (max 50 characters).")

    start = end = None
    try:
        start = date.fromisoformat(start_date)
    except ValueError:
        errors.append("Enter a valid start date.")
    if end_date:
        try:
            end = date.fromisoformat(end_date)
        except ValueError:
            errors.append("Enter a valid end date or leave it empty.")
    if start and end and end < start:
        errors.append("End date cannot be before the start date.")
    if end and end < date.today():
        errors.append("End date has already passed.")

    if not times or any(not TIME_RE.match(t) for t in times):
        errors.append("Enter every dose time as HH:MM.")
    elif len(times) > MAX_DOSES_PER_DAY:
        errors.append(f"At most {MAX_DOSES_PER_DAY} doses per day.")

    if errors:
        return _render(request, doctor, form=form, errors=errors)

    med_id = crud.create_medication(
        patient_id, doctor["id"], drug_name, dosage, frequency,
        start.isoformat(), end.isoformat() if end else None,
        times, svc.fmt(svc.now()),
    )
    svc.generate_doses(med_id)
    return RedirectResponse(url=f"/doctor/prescriptions?added={quote(drug_name)}", status_code=303)


@router.get("/adherence", response_class=HTMLResponse)
def adherence_alerts(request: Request, days: int = 7, doctor=Depends(require_doctor)):
    days = days if days in (7, 14, 30) else 7
    at = svc.now()

    rows = []
    for p in crud.list_patients_of_doctor(doctor["id"]):
        stats = svc.adherence_for_patient(p["id"], days, at)
        rows.append({"patient": p, "stats": stats})
    # lowest adherence first; patients with no data yet go last
    rows.sort(key=lambda r: (r["stats"]["pct"] is None, r["stats"]["pct"] or 0))

    # missed / skipped doses reported by (or auto-detected for) this doctor's patients
    missed_doses = []
    for r in rows:
        recent = svc.decorate_doses(crud.list_recent_doses(r["patient"]["id"], svc.fmt(at), 30), at)
        for d in recent:
            if d["state"] in ("missed", "skipped"):
                missed_doses.append({**d, "patient_name": r["patient"]["name"]})
    missed_doses.sort(key=lambda d: d["scheduled_for"], reverse=True)
    missed_doses = missed_doses[:20]

    return templates.TemplateResponse(
        request,
        "doctor_adherence.html",
        {
            "doctor": doctor,
            "rows": rows,
            "days": days,
            "threshold": svc.LOW_ADHERENCE_THRESHOLD,
            "alerts": crud.list_alerts_for_doctor(doctor["id"]),
            "low_count": sum(1 for r in rows if r["stats"]["low"]),
            "missed_doses": missed_doses,
            "active_tab": "adherence",
        },
    )