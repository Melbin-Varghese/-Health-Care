"""
dependencies.py
"Who is logged in?" helpers -- the FastAPI equivalent of Flask-Login.

Use in a route:
    def dashboard(request: Request, doctor=Depends(require_doctor)): ...
If nobody is logged in, LoginRequired is raised and app.py turns it into
a redirect to the right login page (like login_manager.login_view).
"""

from fastapi import Request

import crud


class LoginRequired(Exception):
    def __init__(self, login_url: str):
        self.login_url = login_url


def current_doctor(request: Request):
    doctor_id = request.session.get("doctor_id")
    return crud.get_doctor_by_id(doctor_id) if doctor_id else None


def current_patient(request: Request):
    patient_id = request.session.get("patient_id")
    return crud.get_patient_by_id(patient_id) if patient_id else None


def require_doctor(request: Request):
    doctor = current_doctor(request)
    if not doctor:
        raise LoginRequired("/doctor/login")
    return doctor


def require_patient(request: Request):
    patient = current_patient(request)
    if not patient:
        raise LoginRequired("/patient/login")
    return patient
