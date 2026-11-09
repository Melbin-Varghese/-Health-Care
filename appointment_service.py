"""
appointment_service.py
Appointment booking rules. No FastAPI and no SQL in here -- routes call these
functions and they call crud.py (same layout as medication_service.py).

Flow:  patient requests a slot (pending)  ->  doctor confirms or declines.
Either side can cancel a future appointment (the doctor only after confirming).

All times are the server's LOCAL time, like medication_service.
Change the constants below to change the booking rules.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

import crud
from medication_service import fmt, now, parse

SLOT_MINUTES = 30
DAY_START = time(9, 0)             # first slot starts here
DAY_END = time(17, 0)              # last slot ends here (so the last start is 16:30)
WORKDAYS = (0, 1, 2, 3, 4)         # Monday..Friday
BOOKING_HORIZON_DAYS = 30          # how far ahead a patient can book
MIN_LEAD = timedelta(minutes=30)   # can't book a slot that starts sooner than this
MAX_REASON_LEN = 300
MAX_NOTE_LEN = 200
LIVE = ("pending", "confirmed")

STATE_LABELS = {
    "pending": "Awaiting confirmation",
    "confirmed": "Confirmed",
    "declined": "Declined",
    "cancelled": "Cancelled",
    "completed": "Completed",
    "expired": "Not answered",
}


# ----------------------------- slots -----------------------------
def all_slots() -> list[str]:
    """['09:00', '09:30', ... '16:30']"""
    out, cur = [], datetime.combine(date.today(), DAY_START)
    end = datetime.combine(date.today(), DAY_END)
    while cur < end:
        out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=SLOT_MINUTES)
    return out


def bookable_range(at: datetime | None = None) -> tuple[date, date]:
    at = at or now()
    return at.date(), at.date() + timedelta(days=BOOKING_HORIZON_DAYS)


def parse_day(value) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def day_error(day: date | None, at: datetime | None = None) -> str | None:
    at = at or now()
    if day is None:
        return "Choose a valid date."
    first, last = bookable_range(at)
    if day < first or day > last:
        return f"Choose a date within the next {BOOKING_HORIZON_DAYS} days."
    if day.weekday() not in WORKDAYS:
        return "Appointments are available Monday to Friday."
    return None


def available_slots(doctor_id: int, day: date | None, at: datetime | None = None) -> list[str]:
    """Free, still-bookable start times ('HH:MM') for one doctor on one day."""
    at = at or now()
    if day_error(day, at):
        return []
    start = fmt(datetime.combine(day, time.min))
    end = fmt(datetime.combine(day + timedelta(days=1), time.min))
    taken = {parse(t).strftime("%H:%M") for t in crud.list_taken_slots(doctor_id, start, end)}
    earliest = at + MIN_LEAD
    return [s for s in all_slots()
            if s not in taken and datetime.combine(day, time.fromisoformat(s)) > earliest]


# ----------------------------- booking -----------------------------
def book(patient_id: int, doctor_id: int | None, day_str: str, slot: str, reason: str,
         at: datetime | None = None) -> tuple[int | None, str | None]:
    """Returns (appointment_id, None) on success or (None, error_message)."""
    at = at or now()
    if not doctor_id or not crud.get_doctor_by_id(doctor_id):
        return None, "Please choose a doctor."
    day = parse_day(day_str)
    err = day_error(day, at)
    if err:
        return None, err
    if slot not in all_slots():
        return None, "Please choose a time slot."
    when = datetime.combine(day, time.fromisoformat(slot))
    if when <= at + MIN_LEAD:
        return None, "That time is too soon or already past. Please choose a later slot."
    reason = (reason or "").strip()
    if not reason:
        return None, "Please tell the doctor the reason for the visit."
    if len(reason) > MAX_REASON_LEN:
        return None, f"Keep the reason under {MAX_REASON_LEN} characters."
    try:
        appt_id = crud.create_appointment(patient_id, doctor_id, fmt(when), reason, fmt(at))
    except sqlite3.IntegrityError:
        return None, ("That time is no longer available (the doctor, or you, already have an "
                      "appointment then). Please pick another slot.")
    return appt_id, None


def patient_cancel(patient_id: int, appt_id: int, at: datetime | None = None) -> tuple[bool, str]:
    at = at or now()
    appt = crud.get_appointment(appt_id)
    if not appt or appt["patient_id"] != patient_id:
        return False, "Appointment not found."
    if parse(appt["start_time"]) <= at:
        return False, "This appointment has already started or passed."
    ok = crud.update_appointment_status(appt_id, "cancelled", LIVE, fmt(at), patient_id=patient_id)
    return ok, "Appointment cancelled." if ok else "This appointment can no longer be cancelled."


_DOCTOR_ACTIONS = {            # action -> (new status, statuses it may start from, message)
    "confirm": ("confirmed", ("pending",), "Appointment confirmed."),
    "decline": ("declined", ("pending",), "Appointment declined."),
    "cancel":  ("cancelled", ("confirmed",), "Appointment cancelled."),
}


def doctor_respond(doctor_id: int, appt_id: int, action: str, note: str = "",
                   at: datetime | None = None) -> tuple[bool, str]:
    at = at or now()
    if action not in _DOCTOR_ACTIONS:
        return False, "Unknown action."
    appt = crud.get_appointment(appt_id)
    if not appt or appt["doctor_id"] != doctor_id:
        return False, "Appointment not found."
    if parse(appt["start_time"]) <= at:
        return False, "This appointment has already started or passed."
    new_status, allowed, done_msg = _DOCTOR_ACTIONS[action]
    note = (note or "").strip()[:MAX_NOTE_LEN] or None
    ok = crud.update_appointment_status(appt_id, new_status, allowed, fmt(at),
                                        doctor_id=doctor_id, doctor_note=note)
    return ok, done_msg if ok else "This appointment can't be changed any more."


# ----------------------------- display helpers -----------------------------
def decorate(rows, at: datetime | None = None) -> list[dict]:
    """Rows -> dicts with state, labels and which buttons to show."""
    at = at or now()
    out = []
    for r in rows:
        d = dict(r)
        when = parse(d["start_time"])
        future = when > at
        status = d["status"]
        if status == "confirmed" and not future:
            state = "completed"
        elif status == "pending" and not future:
            state = "expired"
        else:
            state = status
        time_label = when.strftime("%I:%M %p").lstrip("0")
        d.update(
            state=state,
            state_label=STATE_LABELS[state],
            date_label=when.strftime("%a, %d %b %Y"),
            time_label=time_label,
            short_label=f"{when.strftime('%a %d %b')}, {time_label}",
            is_future=future,
            can_cancel=status in LIVE and future,
            can_respond=status == "pending" and future,
        )
        out.append(d)
    return out


def split_for_patient(rows, at: datetime | None = None) -> dict:
    items = decorate(rows, at)
    upcoming = sorted((a for a in items if a["status"] in LIVE and a["is_future"]), key=lambda a: a["start_time"])
    history = sorted((a for a in items if a not in upcoming), key=lambda a: a["start_time"], reverse=True)
    return {"upcoming": upcoming, "history": history[:50]}


def split_for_doctor(rows, at: datetime | None = None) -> dict:
    items = decorate(rows, at)
    needs_action = sorted((a for a in items if a["can_respond"]), key=lambda a: a["start_time"])
    upcoming = sorted((a for a in items if a["status"] == "confirmed" and a["is_future"]), key=lambda a: a["start_time"])
    shown = {a["id"] for a in needs_action + upcoming}
    history = sorted((a for a in items if a["id"] not in shown), key=lambda a: a["start_time"], reverse=True)
    return {"needs_action": needs_action, "upcoming": upcoming, "history": history[:50]}


# ----------------------------- dashboard helpers (used as Jinja globals) -----------------------------
def next_for_patient(patient_id: int) -> dict | None:
    at = now()
    row = crud.get_next_appointment_for_patient(patient_id, fmt(at))
    return decorate([row], at)[0] if row else None


def today_count_for_doctor(doctor_id: int) -> int:
    day = now().date()
    return crud.count_confirmed_between(
        doctor_id, fmt(datetime.combine(day, time.min)), fmt(datetime.combine(day + timedelta(days=1), time.min)))


def pending_count_for_doctor(doctor_id: int) -> int:
    return crud.count_pending_after(doctor_id, fmt(now()))
