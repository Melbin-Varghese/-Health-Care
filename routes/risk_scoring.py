"""
routes/risk.py
Doctor-side Risk Scoring page: pick a patient, enter clinical values,
get Diabetes / Hypertension / Heart / Overall risk with reasons.
"""

from typing import Optional

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse

import crud
import risk
from dependencies import require_doctor
from extensions import templates

router = APIRouter(prefix="/doctor", tags=["risk"])

YES_NO = ("yes", "no")


def _history(patient_id):
    if not patient_id:
        return []
    rows = []
    for r in crud.list_health_records(patient_id):
        d = dict(r)
        d["level"] = risk.level(d["overall_score"])
        rows.append(d)
    return rows


def _render(request, doctor, *, patient_id=None, form=None, errors=None, result=None, patient=None):
    return templates.TemplateResponse(
        request,
        "risk_scoring.html",
        {
            "doctor": doctor,
            "patients": crud.list_patients(),
            "selected_id": patient_id,
            "form": form or {},
            "errors": errors or [],
            "result": result,
            "patient": patient,
            "history": _history(patient_id),
        },
    )


@router.get("/risk", response_class=HTMLResponse)
def risk_form(request: Request, patient_id: Optional[int] = None, doctor=Depends(require_doctor)):
    return _render(request, doctor, patient_id=patient_id)


@router.post("/risk", response_class=HTMLResponse)
def risk_submit(
    request: Request,
    doctor=Depends(require_doctor),
    patient_id: int = Form(...),
    height_cm: float = Form(...),
    weight_kg: float = Form(...),
    systolic: int = Form(...),
    diastolic: int = Form(...),
    fasting_sugar: int = Form(...),
    cholesterol: int = Form(...),
    smoker: str = Form(...),
    drinker: str = Form(...),
    exercises: str = Form(...),
    family_history: str = Form(...),
):
    form = dict(
        patient_id=patient_id, height_cm=height_cm, weight_kg=weight_kg,
        systolic=systolic, diastolic=diastolic, fasting_sugar=fasting_sugar,
        cholesterol=cholesterol, smoker=smoker, drinker=drinker,
        exercises=exercises, family_history=family_history,
    )

    patient = crud.get_patient_by_id(patient_id)
    errors = []
    if not patient:
        errors.append("Select a valid patient.")
    if not 50 <= height_cm <= 250:
        errors.append("Height must be between 50 and 250 cm.")
    if not 10 <= weight_kg <= 300:
        errors.append("Weight must be between 10 and 300 kg.")
    if not 70 <= systolic <= 250 or not 40 <= diastolic <= 150:
        errors.append("Enter a realistic blood pressure (systolic 70-250, diastolic 40-150).")
    elif diastolic >= systolic:
        errors.append("Systolic BP must be higher than diastolic BP.")
    if not 40 <= fasting_sugar <= 500:
        errors.append("Fasting sugar must be between 40 and 500 mg/dL.")
    if not 80 <= cholesterol <= 500:
        errors.append("Cholesterol must be between 80 and 500 mg/dL.")
    if any(v not in YES_NO for v in (smoker, drinker, exercises, family_history)):
        errors.append("Answer all lifestyle questions.")

    if errors:
        return _render(request, doctor, patient_id=patient_id, form=form, errors=errors, patient=patient)

    result = risk.calculate_risk(
        age=patient["age"], gender=patient["gender"],
        height_cm=height_cm, weight_kg=weight_kg,
        systolic=systolic, diastolic=diastolic,
        sugar=fasting_sugar, cholesterol=cholesterol,
        smoker=smoker == "yes", drinker=drinker == "yes",
        exercises=exercises == "yes", family_history=family_history == "yes",
    )

    crud.create_health_record(
        patient_id, doctor["id"], height_cm, weight_kg, result["bmi"],
        systolic, diastolic, fasting_sugar, cholesterol,
        smoker == "yes", drinker == "yes", exercises == "yes", family_history == "yes",
        result["diabetes"]["score"], result["hypertension"]["score"],
        result["heart"]["score"], result["overall"]["score"],
    )

    return _render(request, doctor, patient_id=patient_id, form=form, result=result, patient=patient)