"""
config.py
All settings in one place. Anything that changes between your laptop and
a real server (secret key, DB location, AI service address) lives here
and can be overridden with an environment variable.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Optional: load variables from a local .env file (copy .env.example to .env).
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

APP_TITLE = "Sukham — Full Stack Health Platform"

DB_PATH = BASE_DIR / "sukham.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

_DEV_SECRET = "dev-secret-key-change-me"
SECRET_KEY = os.getenv("SECRET_KEY", _DEV_SECRET)
if SECRET_KEY == _DEV_SECRET:
    print("[CONFIG] WARNING: using the default SECRET_KEY. Set SECRET_KEY before deploying.", flush=True)

# ---- Ports used when running everything on one machine ----
#   main app           9000   uvicorn app:app --reload --port 9000
#   pneumonia service  8000   uvicorn services.pneumonia_service:app --port 8000
#   symptom service    8001
PNEUMONIA_SERVICE_URL = os.getenv("PNEUMONIA_SERVICE_URL", "http://127.0.0.1:8000")
SYMPTOM_SERVICE_URL = os.getenv("SYMPTOM_SERVICE_URL", "http://127.0.0.1:8001")
#   monitor service    8002   cd services/monitor_service && uvicorn main:app --port 8002
MONITOR_SERVICE_URL = os.getenv("MONITOR_SERVICE_URL", "http://127.0.0.1:8002")