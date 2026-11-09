"""
crud.py
Every database query in one file. Routers never write SQL -- they call
these functions (same role as crud.py in the Flask project).
"""

import json
from contextlib import closing
from datetime import datetime, timedelta

from database import get_db


# ----------------------------- doctors -----------------------------
def get_doctor_by_id(doctor_id: int):
    with closing(get_db()) as conn:
        return conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone()


def get_doctor_by_email(email: str):
    with closing(get_db()) as conn:
        return conn.execute("SELECT id FROM doctors WHERE email = ?", (email,)).fetchone()


def get_doctor_by_login(identifier: str):
    """Login accepts either an email or a phone number."""
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT * FROM doctors WHERE email = ? OR phone = ?",
            (identifier.lower(), identifier),
        ).fetchone()


def create_doctor(name, email, phone, department, password_hash) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO doctors (name, email, phone, department, password_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (name, email, phone, department, password_hash),
        )
        conn.commit()


# ----------------------------- patients ----------------------------
def get_patient_by_id(patient_id: int):
    with closing(get_db()) as conn:
        return conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()


def get_patient_by_email(email: str):
    with closing(get_db()) as conn:
        return conn.execute("SELECT id FROM patients WHERE email = ?", (email,)).fetchone()


def get_patient_by_login(identifier: str):
    """Login accepts either an email or a phone number."""
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT * FROM patients WHERE email = ? OR phone = ?",
            (identifier.lower(), identifier),
        ).fetchone()


def create_patient(name, email, phone, age, gender, password_hash) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO patients (name, email, phone, age, gender, password_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, email, phone, age, gender, password_hash),
        )
        conn.commit()


def update_patient(patient_id: int, name, phone, age, gender) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            "UPDATE patients SET name = ?, phone = ?, age = ?, gender = ? WHERE id = ?",
            (name, phone, age, gender, patient_id),
        )
        conn.commit()


# ------------------------- health records (risk) -------------------------
def list_patients():
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT id, name, age, gender FROM patients ORDER BY name COLLATE NOCASE"
        ).fetchall()


def create_health_record(patient_id, doctor_id, height_cm, weight_kg, bmi,
                         systolic, diastolic, fasting_sugar, cholesterol,
                         smoker, drinker, exercises, family_history,
                         diabetes_score, hypertension_score, heart_score, overall_score) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO health_records
               (patient_id, doctor_id, height_cm, weight_kg, bmi, systolic, diastolic,
                fasting_sugar, cholesterol, smoker, drinker, exercises, family_history,
                diabetes_score, hypertension_score, heart_score, overall_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, doctor_id, height_cm, weight_kg, bmi, systolic, diastolic,
             fasting_sugar, cholesterol, int(smoker), int(drinker), int(exercises),
             int(family_history), diabetes_score, hypertension_score, heart_score,
             overall_score),
        )
        conn.commit()


def list_health_records(patient_id: int, limit: int = 5):
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT * FROM health_records WHERE patient_id = ? ORDER BY id DESC LIMIT ?",
            (patient_id, limit),
        ).fetchall()


# ------------------------- medications & doses -------------------------
# Timestamps are stored as local "YYYY-MM-DD HH:MM:SS" text so they sort
# and compare correctly as plain strings in SQLite.

def create_medication(patient_id, doctor_id, drug_name, dosage, frequency,
                      start_date, end_date, times, created_at) -> int:
    """Insert a medication and its daily reminder times. Returns the new id."""
    with closing(get_db()) as conn:
        cur = conn.execute(
            """INSERT INTO medications
               (patient_id, doctor_id, drug_name, dosage, frequency,
                start_date, end_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, doctor_id, drug_name, dosage, frequency,
             start_date, end_date, created_at),
        )
        med_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO medication_schedules (medication_id, scheduled_time) VALUES (?, ?)",
            [(med_id, t) for t in times],
        )
        conn.commit()
        return med_id


def get_medication(med_id: int):
    with closing(get_db()) as conn:
        return conn.execute("SELECT * FROM medications WHERE id = ?", (med_id,)).fetchone()


def list_schedules(med_id: int):
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT * FROM medication_schedules WHERE medication_id = ? ORDER BY scheduled_time",
            (med_id,),
        ).fetchall()


_MED_SELECT = """
    SELECT m.*, p.name AS patient_name, p.age AS patient_age, d.name AS doctor_name,
           (SELECT group_concat(scheduled_time, ', ')
              FROM (SELECT scheduled_time FROM medication_schedules
                     WHERE medication_id = m.id ORDER BY scheduled_time)) AS times
      FROM medications m
      JOIN patients p ON p.id = m.patient_id
      JOIN doctors  d ON d.id = m.doctor_id
"""


def list_medications_for_doctor(doctor_id: int, limit: int = 200):
    with closing(get_db()) as conn:
        return conn.execute(
            _MED_SELECT + " WHERE m.doctor_id = ? ORDER BY m.id DESC LIMIT ?",
            (doctor_id, limit),
        ).fetchall()


def list_medications_for_patient(patient_id: int):
    with closing(get_db()) as conn:
        return conn.execute(
            _MED_SELECT + " WHERE m.patient_id = ? ORDER BY m.is_active DESC, m.id DESC",
            (patient_id,),
        ).fetchall()


def list_active_medications():
    with closing(get_db()) as conn:
        return conn.execute("SELECT * FROM medications WHERE is_active = 1").fetchall()


def deactivate_expired_medications(today: str) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            "UPDATE medications SET is_active = 0 WHERE is_active = 1 AND end_date IS NOT NULL AND end_date < ?",
            (today,),
        )
        conn.commit()


def add_dose_log_if_missing(schedule_id, medication_id, patient_id, scheduled_for) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO dose_logs (schedule_id, medication_id, patient_id, scheduled_for)
               VALUES (?, ?, ?, ?)""",
            (schedule_id, medication_id, patient_id, scheduled_for),
        )
        conn.commit()


_DOSE_SELECT = """
    SELECT dl.*, m.drug_name, m.dosage, m.frequency
      FROM dose_logs dl
      JOIN medications m ON m.id = dl.medication_id
"""


def get_dose(log_id: int):
    with closing(get_db()) as conn:
        return conn.execute(_DOSE_SELECT + " WHERE dl.id = ?", (log_id,)).fetchone()


def list_doses_between(patient_id: int, start: str, end: str):
    """Doses with start <= scheduled_for < end (used for 'today' and adherence windows)."""
    with closing(get_db()) as conn:
        return conn.execute(
            _DOSE_SELECT + """ WHERE dl.patient_id = ? AND dl.scheduled_for >= ? AND dl.scheduled_for < ?
                               ORDER BY dl.scheduled_for""",
            (patient_id, start, end),
        ).fetchall()


def list_recent_doses(patient_id: int, now: str, limit: int = 20):
    """Most recent doses that have already come due, newest first."""
    with closing(get_db()) as conn:
        return conn.execute(
            _DOSE_SELECT + """ WHERE dl.patient_id = ? AND dl.scheduled_for <= ?
                               ORDER BY dl.scheduled_for DESC LIMIT ?""",
            (patient_id, now, limit),
        ).fetchall()


def update_dose_status(log_id: int, status: str, responded_at: str) -> bool:
    """Only a still-pending dose can be answered. Returns True if it was updated."""
    with closing(get_db()) as conn:
        cur = conn.execute(
            "UPDATE dose_logs SET status = ?, responded_at = ? WHERE id = ? AND status = 'pending'",
            (status, responded_at, log_id),
        )
        conn.commit()
        return cur.rowcount == 1


def list_unreminded_due_doses(now: str):
    with closing(get_db()) as conn:
        return conn.execute(
            """SELECT dl.id, dl.scheduled_for, m.drug_name, m.dosage,
                      p.id AS patient_id, p.name AS patient_name
                 FROM dose_logs dl
                 JOIN medications m ON m.id = dl.medication_id
                 JOIN patients p ON p.id = dl.patient_id
                WHERE dl.reminder_sent = 0 AND dl.status = 'pending' AND dl.scheduled_for <= ?""",
            (now,),
        ).fetchall()


def mark_reminder_sent(log_id: int) -> None:
    with closing(get_db()) as conn:
        conn.execute("UPDATE dose_logs SET reminder_sent = 1 WHERE id = ?", (log_id,))
        conn.commit()


def list_patients_of_doctor(doctor_id: int):
    """Patients this doctor has prescribed something to."""
    with closing(get_db()) as conn:
        return conn.execute(
            """SELECT DISTINCT p.id, p.name, p.age, p.gender
                 FROM medications m JOIN patients p ON p.id = m.patient_id
                WHERE m.doctor_id = ? ORDER BY p.name COLLATE NOCASE""",
            (doctor_id,),
        ).fetchall()


def list_patient_ids_with_active_medications():
    with closing(get_db()) as conn:
        return [r["patient_id"] for r in conn.execute(
            "SELECT DISTINCT patient_id FROM medications WHERE is_active = 1"
        ).fetchall()]


# ----------------------------- adherence alerts -----------------------------
def alert_exists_on(patient_id: int, day: str) -> bool:
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT 1 FROM adherence_alerts WHERE patient_id = ? AND substr(created_at, 1, 10) = ?",
            (patient_id, day),
        ).fetchone() is not None


def create_adherence_alert(patient_id: int, adherence_pct: float, window_days: int, created_at: str) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO adherence_alerts (patient_id, adherence_pct, window_days, created_at) VALUES (?, ?, ?, ?)",
            (patient_id, adherence_pct, window_days, created_at),
        )
        conn.commit()


def list_alerts_for_doctor(doctor_id: int, limit: int = 30):
    with closing(get_db()) as conn:
        return conn.execute(
            """SELECT a.*, p.name AS patient_name
                 FROM adherence_alerts a JOIN patients p ON p.id = a.patient_id
                WHERE a.patient_id IN (SELECT patient_id FROM medications WHERE doctor_id = ?)
                ORDER BY a.id DESC LIMIT ?""",
            (doctor_id, limit),
        ).fetchall()


def list_alerts_for_patient(patient_id: int, limit: int = 30):
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT * FROM adherence_alerts WHERE patient_id = ? ORDER BY id DESC LIMIT ?",
            (patient_id, limit),
        ).fetchall()


# --------------------------- symptom checker ---------------------------
def create_symptom_check(patient_id, symptoms_json, severity, duration_days,
                         urgency, top_condition, result_json) -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """INSERT INTO symptom_checks
               (patient_id, symptoms, severity, duration_days, urgency, top_condition, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, symptoms_json, severity, duration_days, urgency, top_condition, result_json),
        )
        conn.commit()


def list_symptom_checks(patient_id: int, limit: int = 10):
    """Newest first. 'symptoms' holds a JSON list of readable symptom names."""
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM symptom_checks WHERE patient_id = ? ORDER BY id DESC LIMIT ?",
            (patient_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["symptom_labels"] = json.loads(d["symptoms"])
        out.append(d)
    return out


def list_doctors_by_department(department: str, limit: int = 3):
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT id, name, department FROM doctors WHERE department = ? ORDER BY name LIMIT ?",
            (department, limit),
        ).fetchall()


# ----------------------------- appointments -----------------------------
# start_time is local "YYYY-MM-DD HH:MM:SS" text, same convention as dose_logs.
LIVE = "('pending', 'confirmed')"


def list_doctors_for_booking():
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT id, name, department FROM doctors "
            "ORDER BY department COLLATE NOCASE, name COLLATE NOCASE"
        ).fetchall()


def create_appointment(patient_id, doctor_id, start_time, reason, created_at) -> int:
    """Insert a pending appointment. Raises sqlite3.IntegrityError if the slot is taken."""
    with closing(get_db()) as conn:
        cur = conn.execute(
            """INSERT INTO appointments
               (patient_id, doctor_id, start_time, reason, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (patient_id, doctor_id, start_time, reason, created_at, created_at),
        )
        conn.commit()
        return cur.lastrowid


def get_appointment(appt_id: int):
    with closing(get_db()) as conn:
        return conn.execute("SELECT * FROM appointments WHERE id = ?", (appt_id,)).fetchone()


_APPT_SELECT = """
    SELECT a.*, p.name AS patient_name, p.age AS patient_age, p.gender AS patient_gender,
           d.name AS doctor_name, d.department AS doctor_department
      FROM appointments a
      JOIN patients p ON p.id = a.patient_id
      JOIN doctors  d ON d.id = a.doctor_id
"""


def list_appointments_for_patient(patient_id: int, limit: int = 200):
    with closing(get_db()) as conn:
        return conn.execute(
            _APPT_SELECT + " WHERE a.patient_id = ? ORDER BY a.start_time DESC LIMIT ?",
            (patient_id, limit),
        ).fetchall()


def list_appointments_for_doctor(doctor_id: int, limit: int = 300):
    with closing(get_db()) as conn:
        return conn.execute(
            _APPT_SELECT + " WHERE a.doctor_id = ? ORDER BY a.start_time DESC LIMIT ?",
            (doctor_id, limit),
        ).fetchall()


def list_taken_slots(doctor_id: int, start: str, end: str):
    """start_time of live appointments for this doctor with start <= t < end."""
    with closing(get_db()) as conn:
        return [r["start_time"] for r in conn.execute(
            f"SELECT start_time FROM appointments WHERE doctor_id = ? AND status IN {LIVE} "
            "AND start_time >= ? AND start_time < ?",
            (doctor_id, start, end),
        ).fetchall()]


def get_next_appointment_for_patient(patient_id: int, now: str):
    with closing(get_db()) as conn:
        return conn.execute(
            _APPT_SELECT + f" WHERE a.patient_id = ? AND a.status IN {LIVE} AND a.start_time > ? "
            "ORDER BY a.start_time LIMIT 1",
            (patient_id, now),
        ).fetchone()


def count_confirmed_between(doctor_id: int, start: str, end: str) -> int:
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE doctor_id = ? AND status = 'confirmed' "
            "AND start_time >= ? AND start_time < ?",
            (doctor_id, start, end),
        ).fetchone()[0]


def count_pending_after(doctor_id: int, now: str) -> int:
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE doctor_id = ? AND status = 'pending' AND start_time > ?",
            (doctor_id, now),
        ).fetchone()[0]


def update_appointment_status(appt_id: int, new_status: str, allowed_from, updated_at: str,
                              patient_id=None, doctor_id=None, doctor_note=None) -> bool:
    """Change status only if it is currently one of `allowed_from` AND belongs to the caller."""
    allowed_from = tuple(allowed_from)
    sql = ("UPDATE appointments SET status = ?, updated_at = ?, doctor_note = COALESCE(?, doctor_note) "
           "WHERE id = ? AND status IN (" + ",".join("?" * len(allowed_from)) + ")")
    params = [new_status, updated_at, doctor_note, appt_id, *allowed_from]
    if patient_id is not None:
        sql += " AND patient_id = ?"
        params.append(patient_id)
    if doctor_id is not None:
        sql += " AND doctor_id = ?"
        params.append(doctor_id)
    with closing(get_db()) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount == 1


# ----------------------------- help signals / care alerts -----------------------------
# A doctor sees an alert when the patient is in their care (they prescribed something, or
# have a pending/confirmed appointment with them) -- OR when the patient has no doctor at
# all yet, so a call for help is never delivered to nobody.
# An urgent alert nobody answers within ESCALATE_AFTER_SECONDS becomes visible to EVERY doctor.
ESCALATE_AFTER_SECONDS = 90

_ALERT_SCOPE = """(
    a.patient_id IN (SELECT patient_id FROM medications WHERE doctor_id = :doc
                     UNION SELECT patient_id FROM appointments
                            WHERE doctor_id = :doc AND status IN ('pending', 'confirmed'))
    OR a.patient_id NOT IN (SELECT patient_id FROM medications
                            UNION SELECT patient_id FROM appointments
                                   WHERE status IN ('pending', 'confirmed'))
    OR (a.status = 'open' AND a.level IN ('help', 'emergency') AND a.created_at <= :esc)
    OR a.acknowledged_by = :doc
)"""


def _scope(doctor_id: int, **extra) -> dict:
    cutoff = (datetime.now().replace(microsecond=0) - timedelta(seconds=ESCALATE_AFTER_SECONDS))
    return {"doc": doctor_id, "esc": cutoff.strftime("%Y-%m-%d %H:%M:%S"), **extra}


_ALERT_SELECT = """
    SELECT a.*, p.name AS patient_name, p.age AS patient_age, p.gender AS patient_gender,
           d.name AS acknowledged_by_name
      FROM care_alerts a
      JOIN patients p ON p.id = a.patient_id
      LEFT JOIN doctors d ON d.id = a.acknowledged_by
"""


def create_care_alert(patient_id, level, source, detail, now) -> int:
    with closing(get_db()) as conn:
        cur = conn.execute(
            """INSERT INTO care_alerts (patient_id, level, source, detail, status, created_at, last_signal_at)
               VALUES (?, ?, ?, ?, 'open', ?, ?)""",
            (patient_id, level, source, detail, now, now),
        )
        conn.commit()
        return cur.lastrowid


def get_latest_care_alert(patient_id: int):
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT * FROM care_alerts WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (patient_id,)
        ).fetchone()


def touch_care_alert(alert_id: int, now: str) -> None:
    with closing(get_db()) as conn:
        conn.execute("UPDATE care_alerts SET last_signal_at = ? WHERE id = ?", (now, alert_id))
        conn.commit()


def get_care_alert_for_doctor(alert_id: int, doctor_id: int):
    with closing(get_db()) as conn:
        return conn.execute(
            _ALERT_SELECT + " WHERE a.id = :id AND " + _ALERT_SCOPE, _scope(doctor_id, id=alert_id)
        ).fetchone()


def list_care_alerts_for_doctor(doctor_id: int, limit: int = 100):
    with closing(get_db()) as conn:
        return conn.execute(
            _ALERT_SELECT + " WHERE " + _ALERT_SCOPE + " ORDER BY a.id DESC LIMIT :limit",
            _scope(doctor_id, limit=limit),
        ).fetchall()


def count_open_care_alerts_for_doctor(doctor_id: int):
    """(open alerts, open alerts that are help/emergency)."""
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(a.level IN ('help', 'emergency')), 0) FROM care_alerts a "
            "WHERE a.status = 'open' AND " + _ALERT_SCOPE, _scope(doctor_id),
        ).fetchone()
        return row[0], int(row[1])


def acknowledge_care_alert(alert_id: int, doctor_id: int, note, now: str) -> bool:
    """Only an OPEN alert in this doctor's scope can be acknowledged."""
    with closing(get_db()) as conn:
        cur = conn.execute(
            """UPDATE care_alerts SET status = 'acknowledged', acknowledged_by = :doc,
                      acknowledged_at = :now, ack_note = :note
                WHERE id = :id AND status = 'open'
                  AND id IN (SELECT a.id FROM care_alerts a WHERE """ + _ALERT_SCOPE + ")",
            _scope(doctor_id, now=now, note=note, id=alert_id),
        )
        conn.commit()
        return cur.rowcount == 1


def list_care_alerts_for_patient(patient_id: int, limit: int = 10):
    with closing(get_db()) as conn:
        return conn.execute(
            _ALERT_SELECT + " WHERE a.patient_id = ? ORDER BY a.id DESC LIMIT ?", (patient_id, limit)
        ).fetchall()


def list_care_doctors(patient_id: int):
    """Doctors who will see this patient's alerts (empty = every doctor will)."""
    with closing(get_db()) as conn:
        return conn.execute(
            """SELECT id, name, department FROM doctors WHERE id IN (
                   SELECT doctor_id FROM medications WHERE patient_id = :p
                   UNION SELECT doctor_id FROM appointments
                          WHERE patient_id = :p AND status IN ('pending', 'confirmed'))
               ORDER BY name COLLATE NOCASE""", {"p": patient_id},
        ).fetchall()
