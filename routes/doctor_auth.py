"""
routes/doctor_auth.py
Doctor registration, login and logout.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse

import crud
from extensions import templates
from security import hash_password, verify_password
from validators import EMAIL_RE, PHONE_RE

router = APIRouter(prefix="/doctor", tags=["doctor-auth"])

DEPARTMENTS = [
    "General Medicine", "Cardiology", "Dermatology", "Pediatrics",
    "Orthopedics", "Neurology", "ENT", "Gynecology", "Psychiatry", "Other",
]


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        request, "doctor_register.html", {"departments": DEPARTMENTS, "form": {}, "errors": []}
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    department: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    name, email, phone, department = name.strip(), email.strip().lower(), phone.strip(), department.strip()

    errors = []
    if not name:
        errors.append("Name is required.")
    if not EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
    if not PHONE_RE.match(phone):
        errors.append("Enter a valid phone number.")
    if not department:
        errors.append("Select a department.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")

    if not errors:
        if crud.get_doctor_by_email(email):
            errors.append("An account with this email already exists.")
        else:
            crud.create_doctor(name, email, phone, department, hash_password(password))
            request.session["flash"] = ("success", "Registration successful. Please log in.")
            return RedirectResponse(url="/doctor/login", status_code=303)

    return templates.TemplateResponse(
        request,
        "doctor_register.html",
        {
            "departments": DEPARTMENTS,
            "form": {"name": name, "email": email, "phone": phone, "department": department},
            "errors": errors,
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(request, "doctor_login.html", {"email": "", "errors": [], "flash": flash})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    """`email` field accepts either an email address or a phone number."""
    doctor = crud.get_doctor_by_login(email.strip())

    if doctor and verify_password(password, doctor["password_hash"]):
        request.session["doctor_id"] = doctor["id"]
        return RedirectResponse(url="/doctor/dashboard", status_code=303)

    return templates.TemplateResponse(
        request, "doctor_login.html",
        {"email": email, "errors": ["Invalid email/phone or password."], "flash": None},
    )


@router.get("/logout")
def logout(request: Request):
    request.session.pop("doctor_id", None)
    return RedirectResponse(url="/", status_code=303)
