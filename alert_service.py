"""
alert_service.py
Turns "help signals" into care alerts. No FastAPI and no SQL in here.

A signal comes from the camera: a held hand gesture, or sustained distress on
the face. Nothing is sent by hand. This file decides whether a signal
creates a NEW alert, or is just the same signal still being held:

  * one held gesture must not create an alert every frame;
  * a stronger signal (help -> emergency) always creates a new alert;
  * after a doctor acknowledges, the same held gesture doesn't re-alert; the
    patient has to stop for RESIGNAL_GAP seconds before a new alert can start.

Gesture strings match gesture_detector.py in services/monitor_service.
"""

from __future__ import annotations

from datetime import datetime

import crud
from medication_service import fmt, now, parse

LEVEL_CAUTION, LEVEL_HELP, LEVEL_EMERGENCY = "caution", "help", "emergency"
RANK = {LEVEL_CAUTION: 1, LEVEL_HELP: 2, LEVEL_EMERGENCY: 3}
URGENT = (LEVEL_HELP, LEVEL_EMERGENCY)
LEVEL_LABELS = {LEVEL_CAUTION: "Possible distress", LEVEL_HELP: "Needs help", LEVEL_EMERGENCY: "EMERGENCY"}
SOURCE_LABELS = {"gesture": "Hand gesture", "emotion": "Facial expression"}

RESIGNAL_GAP_SECONDS = 30      # silence needed before a new alert can start
TOUCH_EVERY_SECONDS = 5        # how often a held signal refreshes last_signal_at

GESTURE_EMERGENCY, GESTURE_HELP, GESTURE_OK = "EMERGENCY", "NEED HELP", "I'M OK"


def signal_from_monitor(gesture: str, distress: bool):
    """(level, source, detail) for what the camera sees, or None if nothing to report.
    A deliberate gesture always wins over the passive expression signal."""
    if gesture == GESTURE_EMERGENCY:
        return LEVEL_EMERGENCY, "gesture", "Emergency gesture (closed fist) held."
    if gesture == GESTURE_HELP:
        return LEVEL_HELP, "gesture", "Help gesture (one finger raised) held."
    if gesture == GESTURE_OK:
        return None                      # "I'm OK" is feedback on screen, never an alert
    if distress:
        return LEVEL_CAUTION, "emotion", "Sustained distress-associated facial expression (automatic, may be wrong)."
    return None


def live_status(gesture: str, distress: bool) -> dict:
    """What the Status card shows right now (like the original monitor): OK / CAUTION / HELP / EMERGENCY."""
    if gesture == GESTURE_EMERGENCY:
        return {"level": "emergency", "label": "EMERGENCY", "detail": "Emergency gesture (fist) held."}
    if gesture == GESTURE_HELP:
        return {"level": "help", "label": "HELP", "detail": "Help gesture (1 finger) held."}
    if gesture == GESTURE_OK:
        return {"level": "ok", "label": "OK", "detail": "Patient signaled OK (open palm)."}
    if distress:
        return {"level": "caution", "label": "CAUTION", "detail": "Sustained distress-associated expression."}
    return {"level": "ok", "label": "OK", "detail": "No concerning signal."}


def record_signal(patient_id: int, level: str, source: str, detail: str,
                  at: datetime | None = None) -> tuple[bool, int]:
    """Returns (created, alert_id)."""
    at = at or now()
    latest = crud.get_latest_care_alert(patient_id)
    if latest and RANK[latest["level"]] >= RANK[level]:
        gap = (at - parse(latest["last_signal_at"])).total_seconds()
        if latest["status"] == "open" or gap < RESIGNAL_GAP_SECONDS:
            if gap >= TOUCH_EVERY_SECONDS:
                crud.touch_care_alert(latest["id"], fmt(at))
            return False, latest["id"]
    return True, crud.create_care_alert(patient_id, level, source, detail, fmt(at))


def acknowledge(doctor_id: int, alert_id: int, note: str = "", at: datetime | None = None) -> tuple[bool, str]:
    at = at or now()
    ok = crud.acknowledge_care_alert(alert_id, doctor_id, (note or "").strip()[:200] or None, fmt(at))
    if ok:
        return True, "Alert acknowledged. The patient can see that you responded."
    return False, "This alert was already acknowledged, or isn't one of yours."


# ----------------------------- display helpers -----------------------------
def decorate(rows, at: datetime | None = None) -> list[dict]:
    at = at or now()
    out = []
    for r in rows:
        d = dict(r)
        created = parse(d["created_at"])
        last = parse(d["last_signal_at"])
        d.update(
            level_label=LEVEL_LABELS[d["level"]],
            source_label=SOURCE_LABELS.get(d["source"], d["source"]),
            is_urgent=d["level"] in URGENT,
            is_open=d["status"] == "open",
            created_label=created.strftime("%d %b, %I:%M:%S %p").lstrip("0"),
            time_label=created.strftime("%I:%M %p").lstrip("0"),
            last_signal_label=last.strftime("%I:%M:%S %p").lstrip("0"),
            still_signalling=(at - last).total_seconds() < 15 and d["status"] == "open",
            escalated=d["status"] == "open" and d["level"] in URGENT and (at - created).total_seconds() >= crud.ESCALATE_AFTER_SECONDS,
            responder=f"Dr. {d['acknowledged_by_name']}" if d.get("acknowledged_by_name") else "A doctor",
            ack_label=parse(d["acknowledged_at"]).strftime("%I:%M %p").lstrip("0") if d.get("acknowledged_at") else "",
        )
        out.append(d)
    return out


def feed_for_doctor(doctor_id: int) -> dict:
    """Small JSON summary the doctor pages poll to show badges and pop-ups."""
    rows = crud.list_care_alerts_for_doctor(doctor_id, limit=30)
    open_total, open_urgent = crud.count_open_care_alerts_for_doctor(doctor_id)
    items = decorate(rows)
    urgent_open = next((a for a in items if a["is_open"] and a["is_urgent"]), None)
    notice = next((a for a in items if a["is_open"] and not a["is_urgent"]), None)

    def brief(a):
        return None if not a else {"id": a["id"], "level": a["level"], "label": a["level_label"],
                                   "patient": a["patient_name"], "time": a["time_label"], "escalated": a["escalated"]}
    return {
        "open": open_total,
        "urgent": open_urgent,
        "latest_id": rows[0]["id"] if rows else 0,
        "latest_urgent": brief(urgent_open),     # pop-up + sound
        "latest_notice": brief(notice),          # quiet pop-up (automatic distress guess)
    }


def open_count_for_doctor(doctor_id: int) -> int:        # Jinja global (sidebar badge)
    return crud.count_open_care_alerts_for_doctor(doctor_id)[0]


def urgent_count_for_doctor(doctor_id: int) -> int:      # Jinja global (dashboard banner)
    return crud.count_open_care_alerts_for_doctor(doctor_id)[1]
