"""
medication_service.py
Medication reminder + adherence logic (ported from the standalone
medication_reminder project). No FastAPI and no SQL in here -- routes call
these functions and they call crud.py.

All times are the server's LOCAL time (the original used UTC, which would
fire reminders 5.5 hours off for users in India).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

import crud

DT_FMT = "%Y-%m-%d %H:%M:%S"

LOW_ADHERENCE_THRESHOLD = 70.0   # % -- below this a doctor alert is raised
ALERT_WINDOW_DAYS = 7            # look-back used when deciding to raise an alert
MISSED_GRACE = timedelta(hours=2)  # a pending dose this far past its time counts as missed
HORIZON_DAYS = 2                 # dose logs are created for today + tomorrow


# ----------------------------- small helpers -----------------------------
def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def fmt(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def parse(value: str) -> datetime:
    return datetime.strptime(value, DT_FMT)


def dose_state(status: str, scheduled_for: str, at: datetime) -> str:
    """
    What the UI should show for a dose:
      taken / skipped / delayed  -> as recorded
      upcoming                   -> pending, not due yet
      due                        -> pending, time has come (patient can verify)
      missed                     -> pending and more than MISSED_GRACE overdue
    """
    if status != "pending":
        return status
    when = parse(scheduled_for)
    if when > at:
        return "upcoming"
    if when < at - MISSED_GRACE:
        return "missed"
    return "due"


def decorate_doses(rows, at: datetime | None = None):
    """Turn dose rows into dicts with .state, .time and .can_respond for templates."""
    at = at or now()
    out = []
    for r in rows:
        d = dict(r)
        d["state"] = dose_state(d["status"], d["scheduled_for"], at)
        d["time"] = parse(d["scheduled_for"]).strftime("%I:%M %p").lstrip("0")
        d["date"] = parse(d["scheduled_for"]).strftime("%d %b")
        d["can_respond"] = d["state"] in ("due", "missed")
        out.append(d)
    return out


# ----------------------------- dose generation -----------------------------
def generate_doses(med_id: int, at: datetime | None = None) -> None:
    """Create dose logs for today + tomorrow for one medication (idempotent)."""
    at = at or now()
    med = crud.get_medication(med_id)
    if not med or not med["is_active"]:
        return

    created = parse(med["created_at"])
    start = date.fromisoformat(med["start_date"])
    end = date.fromisoformat(med["end_date"]) if med["end_date"] else None

    for sched in crud.list_schedules(med_id):
        t = time.fromisoformat(sched["scheduled_time"])
        for offset in range(HORIZON_DAYS):
            day = at.date() + timedelta(days=offset)
            if day < start or (end and day > end):
                continue
            when = datetime.combine(day, t)
            # Don't back-fill doses that were already in the past when the
            # doctor wrote the prescription -- they'd instantly count as "missed".
            if when <= created:
                continue
            crud.add_dose_log_if_missing(sched["id"], med_id, med["patient_id"], fmt(when))


def ensure_upcoming_doses() -> None:
    """Scheduler job: keep every active prescription stocked with upcoming doses."""
    at = now()
    crud.deactivate_expired_medications(at.date().isoformat())
    for med in crud.list_active_medications():
        generate_doses(med["id"], at)


# ----------------------------- adherence -----------------------------
def compute_adherence(doses, at: datetime | None = None) -> dict:
    """
    adherence % = taken / (taken + skipped + delayed + missed)
    Doses that are not due yet (or still inside the grace window) are left out.
    """
    at = at or now()
    counts = {"taken": 0, "skipped": 0, "delayed": 0, "missed": 0, "due": 0, "upcoming": 0}
    for d in doses:
        counts[dose_state(d["status"], d["scheduled_for"], at)] += 1

    considered = counts["taken"] + counts["skipped"] + counts["delayed"] + counts["missed"]
    pct = round(counts["taken"] / considered * 100, 1) if considered else None
    return {
        **counts,
        "pending": counts["due"] + counts["upcoming"],
        "total": sum(counts.values()),
        "considered": considered,
        "pct": pct,
        "low": pct is not None and pct < LOW_ADHERENCE_THRESHOLD,
    }


def _window_doses(patient_id: int, days: int, at: datetime):
    since = fmt(at - timedelta(days=days))
    until = fmt(at + timedelta(days=HORIZON_DAYS + 1))
    return crud.list_doses_between(patient_id, since, until)


def adherence_for_patient(patient_id: int, days: int = 14, at: datetime | None = None) -> dict:
    at = at or now()
    return compute_adherence(_window_doses(patient_id, days, at), at)


def adherence_by_medication(patient_id: int, days: int = 14, at: datetime | None = None) -> list[dict]:
    at = at or now()
    grouped = defaultdict(list)
    for d in _window_doses(patient_id, days, at):
        grouped[(d["medication_id"], d["drug_name"], d["dosage"])].append(d)
    result = []
    for (_, name, dosage), doses in grouped.items():
        result.append({"drug_name": name, "dosage": dosage, **compute_adherence(doses, at)})
    return sorted(result, key=lambda r: r["drug_name"].lower())


# ----------------------------- notifications -----------------------------
# Console stand-ins, same as the original project. Swap the print() calls
# for SMS / email / push when you're ready.
def send_reminder(dose) -> None:
    print(f"[REMINDER] patient_id={dose['patient_id']}: {dose['patient_name']}, "
          f"it's time to take {dose['drug_name']} ({dose['dosage']}).", flush=True)


def send_low_adherence_alert(patient_id: int, pct: float) -> None:
    print(f"[DOCTOR ALERT] patient {patient_id} at {pct}% adherence over the last "
          f"{ALERT_WINDOW_DAYS} days.", flush=True)


def send_due_reminders() -> None:
    """Scheduler job (every minute): remind about doses whose time has come."""
    at = now()
    for dose in crud.list_unreminded_due_doses(fmt(at)):
        # After downtime, don't spam reminders for doses that are long gone.
        if parse(dose["scheduled_for"]) >= at - MISSED_GRACE:
            send_reminder(dose)
        crud.mark_reminder_sent(dose["id"])


# ----------------------------- alerts -----------------------------
def check_adherence_and_alert(patient_id: int, at: datetime | None = None) -> bool:
    """Raise (at most one per day) low-adherence alert for a patient. True if raised."""
    at = at or now()
    stats = adherence_for_patient(patient_id, ALERT_WINDOW_DAYS, at)
    if not stats["low"]:
        return False
    day = at.date().isoformat()
    if crud.alert_exists_on(patient_id, day):
        return False
    crud.create_adherence_alert(patient_id, stats["pct"], ALERT_WINDOW_DAYS, fmt(at))
    send_low_adherence_alert(patient_id, stats["pct"])
    return True


def check_all_adherence() -> None:
    """Scheduler job: catches patients who ignore reminders and never respond."""
    at = now()
    for patient_id in crud.list_patient_ids_with_active_medications():
        check_adherence_and_alert(patient_id, at)