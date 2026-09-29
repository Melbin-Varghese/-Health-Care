"""
routes/home.py
Public pages (landing page with doctor / patient role selection).
Add future static pages here: /about, /contact, /privacy-policy ...
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from extensions import templates

router = APIRouter(tags=["home"])


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "main.html", {})
