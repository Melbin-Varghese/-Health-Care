"""
routes/symptom_checker.py
Patient-side symptom checker page. Does NOT contain the rules itself -- it
calls the standalone service in services/symptom_service.py over HTTP
(like routes/pneumonia.py does for the X-ray model), then saves the history
and adds doctor suggestions from this server's own database.

Point it at the service with:
    SYMPTOM_SERVICE_URL=http://192.168.1.5:8001
Default is http://127.0.0.1:8001 (same laptop).
"""

import json

import httpx
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse

import config
import crud
from dependencies import require_patient
from extensions import templates

router = APIRouter(prefix="/patient", tags=["symptom-checker"])

SERVICE_DOWN = (
    f"Cannot reach the Symptom Checker service at {config.SYMPTOM_SERVICE_URL}. "
    "Make sure services/symptom_service.py is running."
)


async def _get_catalogue() -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{config.SYMPTOM_SERVICE_URL}/symptoms")
    r.raise_for_status()
    return r.json()


async def _render(request, patient, result=None, error=None, selected=None, form=None):
    catalogue = {"groups": {}, "emergency_number": "112"}
    try:
        catalogue = await _get_catalogue()
    except httpx.HTTPError:
        error = error or SERVICE_DOWN

    return templates.TemplateResponse(
        request, "symptom_checker.html",
        {
            "patient": patient,
            "groups": catalogue["groups"],
            "emergency_number": catalogue["emergency_number"],
            "result": result,
            "error": error,
            "selected": selected or [],
            "form": form or {"severity": "moderate", "duration_days": 1},
            "history": crud.list_symptom_checks(patient["id"]),
            "doctors": crud.list_doctors_by_department(result["suggested_dept"]) if result else [],
        },
    )


@router.get("/symptom-checker", response_class=HTMLResponse)
async def symptom_form(request: Request, patient=Depends(require_patient)):
    return await _render(request, patient)


@router.post("/symptom-checker", response_class=HTMLResponse)
async def symptom_submit(
    request: Request,
    patient=Depends(require_patient),
    severity: str = Form("moderate"),
    duration_days: str = Form("1"),
):
    form_data = await request.form()
    symptoms = form_data.getlist("symptoms")
    form = {"severity": severity, "duration_days": duration_days}

    if not symptoms:
        return await _render(request, patient, error="Select at least one symptom.", form=form)
    if not duration_days.isdigit() or int(duration_days) > 365:
        return await _render(request, patient, selected=symptoms, form=form,
                             error="Enter how many days (0-365) you've had these symptoms.")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{config.SYMPTOM_SERVICE_URL}/check",
                json={"symptoms": symptoms, "severity": severity,
                      "duration_days": int(duration_days), "age": patient["age"]},
            )
        r.raise_for_status()
        result = r.json()
    except httpx.ConnectError:
        return await _render(request, patient, selected=symptoms, form=form, error=SERVICE_DOWN)
    except Exception as e:
        return await _render(request, patient, selected=symptoms, form=form,
                             error=f"Could not check those symptoms: {e}")

    crud.create_symptom_check(
        patient["id"], json.dumps(result["symptoms"]), result["severity"], result["duration_days"],
        result["urgency"], result["matches"][0]["name"] if result["matches"] else None,
        json.dumps(result["matches"]),
    )
    return await _render(request, patient, result=result, selected=symptoms, form=form)