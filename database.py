"""
database.py
SQLite connection and table setup only. No FastAPI, no routes, no queries
for a specific feature (those live in crud.py).
"""

import sqlite3

import config


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist (Flask equivalent: db.create_all())."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            department TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            height_cm REAL NOT NULL,
            weight_kg REAL NOT NULL,
            bmi REAL NOT NULL,
            systolic INTEGER NOT NULL,
            diastolic INTEGER NOT NULL,
            fasting_sugar INTEGER NOT NULL,
            cholesterol INTEGER NOT NULL,
            smoker INTEGER NOT NULL,
            drinker INTEGER NOT NULL,
            exercises INTEGER NOT NULL,
            family_history INTEGER NOT NULL,
            diabetes_score INTEGER NOT NULL,
            hypertension_score INTEGER NOT NULL,
            heart_score INTEGER NOT NULL,
            overall_score INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)
    # ---------------- medication reminder & adherence ----------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            drug_name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            frequency TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL,
            scheduled_time TEXT NOT NULL,          -- "HH:MM"
            FOREIGN KEY (medication_id) REFERENCES medications(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dose_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER NOT NULL,
            medication_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            scheduled_for TEXT NOT NULL,           -- "YYYY-MM-DD HH:MM:SS" (server local time)
            status TEXT NOT NULL DEFAULT 'pending', -- pending | taken | skipped | delayed
            responded_at TEXT,
            reminder_sent INTEGER NOT NULL DEFAULT 0,
            UNIQUE (schedule_id, scheduled_for),
            FOREIGN KEY (schedule_id) REFERENCES medication_schedules(id),
            FOREIGN KEY (medication_id) REFERENCES medications(id),
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dose_patient_time ON dose_logs (patient_id, scheduled_for)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS adherence_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            adherence_pct REAL NOT NULL,
            window_days INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
    """)
    conn.commit()
    conn.close()