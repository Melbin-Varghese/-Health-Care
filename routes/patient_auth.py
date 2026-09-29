"""
routes/patient_auth.py
Patient registration, login and logout.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse

import crud
from extensions import templates
from security import hash_password, verify_password
from validators import EMAIL_RE, PHONE_RE, parse_age

router = APIRouter(prefix="/patient", tags=["patient-auth"])

GENDERS = ["Male", "Female"]


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        request, "patient_register.html", {"genders": GENDERS, "form": {}, "errors": []}
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    age: str = Form(...),
    gender: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    name, email, phone, gender = name.strip(), email.strip().lower(), phone.strip(), gender.strip()
    age_raw = age.strip()

    errors = []
    if not name:
        errors.append("Name is required.")
    if not EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
    if not PHONE_RE.match(phone):
        errors.append("Enter a valid phone number.")

    age_val, age_error = parse_age(age_raw)
    if age_error:
        errors.append(age_error)

    if gender not in GENDERS:
        errors.append("Select a gender.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")

    if not errors:
        if crud.get_patient_by_email(email):
            errors.append("An account with this email already exists.")
        else:
            crud.create_patient(name, email, phone, age_val, gender, hash_password(password))
            request.session["flash"] = ("success", "Registration successful. Please log in.")
            return RedirectResponse(url="/patient/login", status_code=303)

    return templates.TemplateResponse(
        request,
        "patient_register.html",
        {
            "genders": GENDERS,
            "form": {"name": name, "email": email, "phone": phone, "age": age_raw, "gender": gender},
            "errors": errors,
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(request, "patient_login.html", {"email": "", "errors": [], "flash": flash})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    """`email` field accepts either an email address or a phone number."""
    patient = crud.get_patient_by_login(email.strip())

    if patient and verify_password(password, patient["password_hash"]):
        request.session["patient_id"] = patient["id"]
        return RedirectResponse(url="/patient/dashboard", status_code=303)

    return templates.TemplateResponse(
        request, "patient_login.html",
        {"email": email, "errors": ["Invalid email/phone or password."], "flash": None},
    )


@router.get("/logout")
def logout(request: Request):
    request.session.pop("patient_id", None)
    return RedirectResponse(url="/", status_code=303)
