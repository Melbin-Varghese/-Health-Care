"""
config.py
All settings in one place. Anything that changes between your laptop and
a real server (secret key, DB location, AI service address) lives here
and can be overridden with an environment variable.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

APP_TITLE = "Sukham — Full Stack Health Platform"

DB_PATH = BASE_DIR / "sukham.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

# Address of the standalone pneumonia AI service (model runs on port 8000).
# The main app itself runs on port 9000:  uvicorn app:app --reload --port 9000
PNEUMONIA_SERVICE_URL = os.getenv("PNEUMONIA_SERVICE_URL", "http://127.0.0.1:8000")
SYMPTOM_SERVICE_URL= os.getenv("SYMPTOM_SERVICE_URL", "http://127.0.0.1:8001")