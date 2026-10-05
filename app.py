"""
app.py
Application factory / entry point. Wires together config, middleware,
static files, startup tasks and every router (FastAPI's "blueprints").

Run with:
    uvicorn app:app --reload --port 8000

To add a new feature later:
    1. Create routes/your_feature.py with its own APIRouter
    2. Import it below and add app.include_router(your_feature.router)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import config
from database import init_db
from dependencies import LoginRequired
from scheduler import start_scheduler, stop_scheduler

from routes.home import router as home_router
from routes.doctor_auth import router as doctor_auth_router
from routes.doctor_dashboard import router as doctor_dashboard_router
from routes.doctor_prescriptions import router as doctor_prescriptions_router
from routes.patient_auth import router as patient_auth_router
from routes.patient_dashboard import router as patient_dashboard_router
from routes.patient_prescriptions import router as patient_prescriptions_router
from routes.pneumonia import router as pneumonia_router
from routes.risk_scoring import router as risk_router
from routes.scan_review import router as scan_review_router
from routes.symptom_checker import router as symptom_checker_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # Flask equivalent: db.create_all()
    start_scheduler()  # medication reminders + adherence alerts
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(title=config.APP_TITLE, lifespan=lifespan)

    app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

    app.include_router(home_router)
    app.include_router(doctor_auth_router)
    app.include_router(doctor_dashboard_router)
    app.include_router(doctor_prescriptions_router)
    app.include_router(patient_auth_router)
    app.include_router(patient_dashboard_router)
    app.include_router(patient_prescriptions_router)
    app.include_router(pneumonia_router)
    app.include_router(risk_router)
    app.include_router(scan_review_router)
    app.include_router(symptom_checker_router)

    # Not logged in -> redirect to the matching login page (like login_view in Flask-Login)
    @app.exception_handler(LoginRequired)
    async def login_required_handler(request: Request, exc: LoginRequired):
        return RedirectResponse(url=exc.login_url, status_code=303)

    return app


app = create_app()