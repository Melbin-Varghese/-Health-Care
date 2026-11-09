"""
routes/appointments.py
Appointment booking for patients and approval for doctors.
All rules live in appointment_service.py; this file only moves data between
the browser and that service.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

import appointment_service as appts
import crud
from dependencies import require_doctor, require_patient
from extensions import templates

router = APIRouter()


# ----------------------------- helpers -----------------------------
def _flash(request: Request, kind: str, text: str) -> None:
    request.session["flash"] = {"kind": kind, "text": text}


def _pop_flash(request: Request):
    return request.session.pop("flash", None)


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ----------------------------- patient -----------------------------
def _patient_page(request: Request, patient, doctor_id=None, day="", error=None,
                  reason="", slot="", status_code=200):
    at = appts.now()
    doctors = [dict(d) for d in crud.list_doctors_for_booking()]
    selected = next((d for d in doctors if d["id"] == doctor_id), None)

    slots, slots_error, day_obj = None, None, appts.parse_day(day)
    if selected and day:
        slots_error = appts.day_error(day_obj, at)
        if not slots_error:
            slots = appts.available_slots(selected["id"], day_obj, at)

    first, last = appts.bookable_range(at)
    lists = appts.split_for_patient(crud.list_appointments_for_patient(patient["id"]), at)
    return templates.TemplateResponse(request, "patient_appointments.html", {
        "patient": patient, "doctors": doctors, "selected_doctor": selected,
        "day": day, "day_label": day_obj.strftime("%A, %d %b %Y") if day_obj else "",
        "slots": slots, "slots_error": slots_error, "chosen_slot": slot, "reason": reason,
        "min_day": first.isoformat(), "max_day": last.isoformat(),
        "upcoming": lists["upcoming"], "history": lists["history"],
        "error": error, "flash": _pop_flash(request),
        "slot_minutes": appts.SLOT_MINUTES,
    }, status_code=status_code)


@router.get("/patient/appointments")
def patient_appointments(request: Request, doctor_id: str = "", day: str = "",
                         patient=Depends(require_patient)):
    return _patient_page(request, patient, doctor_id=_to_int(doctor_id), day=day.strip())


@router.post("/patient/appointments/book")
def patient_book(request: Request, doctor_id: str = Form(""), day: str = Form(""),
                 slot: str = Form(""), reason: str = Form(""),
                 patient=Depends(require_patient)):
    did = _to_int(doctor_id)
    appt_id, error = appts.book(patient["id"], did, day, slot, reason)
    if error:
        return _patient_page(request, patient, doctor_id=did, day=day.strip(), error=error,
                             reason=reason, slot=slot, status_code=400)
    _flash(request, "success", "Appointment requested. You'll see it as confirmed once the doctor accepts.")
    return RedirectResponse("/patient/appointments", status_code=303)


@router.post("/patient/appointments/{appt_id}/cancel")
def patient_cancel(request: Request, appt_id: int, patient=Depends(require_patient)):
    ok, message = appts.patient_cancel(patient["id"], appt_id)
    _flash(request, "success" if ok else "error", message)
    return RedirectResponse("/patient/appointments", status_code=303)


# ----------------------------- doctor -----------------------------
@router.get("/doctor/appointments")
def doctor_appointments(request: Request, doctor=Depends(require_doctor)):
    lists = appts.split_for_doctor(crud.list_appointments_for_doctor(doctor["id"]))
    return templates.TemplateResponse(request, "doctor_appointments.html", {
        "doctor": doctor, "flash": _pop_flash(request), **lists,
    })


@router.post("/doctor/appointments/{appt_id}/{action}")
def doctor_respond(request: Request, appt_id: int, action: str, note: str = Form(""),
                   doctor=Depends(require_doctor)):
    ok, message = appts.doctor_respond(doctor["id"], appt_id, action, note)
    _flash(request, "success" if ok else "error", message)
    return RedirectResponse("/doctor/appointments", status_code=303)
