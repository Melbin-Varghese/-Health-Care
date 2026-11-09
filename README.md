# Sukham: Full Stack Health Platform

A FastAPI + Jinja + SQLite platform where **doctors** and **patients** share one system:
appointment booking, an automatic Patient Monitor (hand-gesture and facial-expression alerts), prescriptions with medication reminders, adherence tracking, risk scoring, an
AI pneumonia X-ray check, and a symptom checker.

> Screening and decision-support tools only. Nothing here is a medical diagnosis.

## Features
See [docs/FEATURES.md](docs/FEATURES.md) for every page, URL and the files behind it.

| Role | What they can do |
|------|------------------|
| Doctor | Register/login, receive and acknowledge automatic patient alerts, confirm or decline appointment requests, prescribe medication with reminder times, view patient adherence and low-adherence alerts, calculate diabetes / hypertension / heart-disease risk, upload chest X-rays for AI review |
| Patient | Register/login, get monitored by camera: a hand gesture or sustained distress alerts the care team automatically (Patient Monitor), book appointments with a doctor, see prescriptions, confirm each dose, view own adherence, run the symptom checker, edit profile |
| System | Background scheduler creates dose logs, sends reminders (console for now), raises one low-adherence alert per patient per day |

## Project layout
```
app.py                  entry point: wires middleware, routers, scheduler
config.py               all settings (env-overridable)
database.py             SQLite connection + table creation
crud.py                 every SQL query
dependencies.py         "who is logged in" helpers
security.py             password hashing
validators.py           form validation
extensions.py           shared Jinja templates object + filters
risk.py                 rule-based risk calculator (pure Python)
medication_service.py   reminders + adherence logic
appointment_service.py  appointment booking rules
alert_service.py        Patient Monitor alert rules
scheduler.py            background jobs
routes/                 one APIRouter per feature
services/
  pneumonia_service.py  separate AI microservice
  models/               the pneumonia .keras model file
  monitor_service/      Patient Monitor AI service (gestures + expression)
tools/delete_user.py    safely delete a doctor/patient and their data
templates/              page templates
  partials/             shared sidebars
static/css/             stylesheets
docs/FEATURES.md        feature map
```

## Setup (Windows, Python 3.11)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Edit `.env` and set a real `SECRET_KEY`.

## Run (separate terminals, project root)
| Process | Command | Port |
|---------|---------|------|
| Main app | `uvicorn app:app --reload --port 9000` | 9000 |
| Pneumonia AI | `uvicorn services.pneumonia_service:app --port 8000` | 8000 |
| Symptom service | see `SYMPTOM_SERVICE_URL` in `config.py` | 8001 |
| Patient Monitor AI | `cd services/monitor_service` then `uvicorn main:app --port 8002` | 8002 |

Open http://127.0.0.1:9000. The pneumonia page needs its AI service running and the Patient Monitor needs the monitor service and a camera; everything else works without them.

**Monitor service setup:** the three model files (`emotion_model.h5`, `haarcascade_frontalface_default.xml`, `hand_landmarker.task`) are already in `services/monitor_service/models/`. Install `services/monitor_service/requirements.txt` into the virtual environment that worked for your old patient_monitor project, and keep it separate from the venv that has the full `tensorflow` package (this one uses `tensorflow-cpu`). Keep OpenCV below version 5: OpenCV 5 removed `CascadeClassifier`, which the face detector needs.

## Notes
- Only one program can use a camera at a time. If the monitor page says another program is using it, close OBS, Zoom, Teams or other tabs that use the camera (or pick another camera in the page).
- Run the main app with **one worker**. Each worker starts its own scheduler, so several workers would send duplicate reminders.
- `sukham.db` is created on first start and is git-ignored. It holds patient data and password hashes.
- The model file is about 50 MB. GitHub warns above 50 MB; use Git LFS if it grows.
- To record exact versions after everything runs: `pip freeze > requirements.lock.txt`.
