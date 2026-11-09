"""
routes/monitor.py
Patient Monitor: the camera watches the patient's hand and face, and alerts the
care team AUTOMATICALLY. There are no manual buttons: a held hand gesture
(fist = emergency, one finger = help) or sustained distress on the face is
enough. Their care team sees it straight away.

Patient browser --frame--> this file --> monitor service (AI, port 8002)
                                     --> alert_service --> care_alerts table
Doctor pages poll /doctor/alerts/feed and show a badge, a pop-up and a sound.

The rules for creating alerts live in alert_service.py.
"""

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

import alert_service as alerts
import config
import crud
from dependencies import require_doctor, require_patient
from extensions import templates

router = APIRouter()

MAX_FRAME_BYTES = 2 * 1024 * 1024
_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=1.5))
    return _http


def _flash(request: Request, kind: str, text: str) -> None:
    request.session["flash"] = {"kind": kind, "text": text}


def _pop_flash(request: Request):
    return request.session.pop("flash", None)


# ----------------------------- talking to the monitor service -----------------------------
async def _start_session() -> str:
    resp = await _client().post(f"{config.MONITOR_SERVICE_URL}/session/start",
                                params={"hold_frames": 6, "emotion_every_n": 2})
    resp.raise_for_status()
    return resp.json()["session_id"]


async def _analyze(request: Request, frame: bytes):
    """Send one frame; starts (or restarts) the patient's monitor session as needed."""
    sid = request.session.get("monitor_sid")
    for attempt in (1, 2):
        if not sid:
            sid = await _start_session()
            request.session["monitor_sid"] = sid
        resp = await _client().post(f"{config.MONITOR_SERVICE_URL}/session/{sid}/analyze",
                                    content=frame, headers={"Content-Type": "application/octet-stream"})
        if resp.status_code == 404 and attempt == 1:     # session expired on the service side
            sid = None
            continue
        return resp
    return resp


def _service_online() -> bool:
    try:
        r = httpx.get(f"{config.MONITOR_SERVICE_URL}/health", timeout=1.0)
        return r.status_code == 200 and r.json().get("model_loaded", False)
    except (httpx.HTTPError, ValueError):
        return False


# ----------------------------- patient -----------------------------
@router.get("/patient/monitor")
def patient_monitor(request: Request, patient=Depends(require_patient)):
    return templates.TemplateResponse(request, "patient_monitor.html", {
        "patient": patient,
        "care_doctors": [dict(d) for d in crud.list_care_doctors(patient["id"])],
        "recent": alerts.decorate(crud.list_care_alerts_for_patient(patient["id"], limit=10)),
        "monitor_online": _service_online(),
        "escalate_after": crud.ESCALATE_AFTER_SECONDS,
    })


@router.post("/patient/monitor/frame")
async def monitor_frame(request: Request, patient=Depends(require_patient)):
    frame = await request.body()
    if not frame or len(frame) > MAX_FRAME_BYTES:
        return JSONResponse({"ok": False, "error": "bad_frame"}, status_code=400)
    try:
        resp = await _analyze(request, frame)
    except httpx.HTTPError:
        return JSONResponse({"ok": False, "error": "monitor_offline"}, status_code=503)
    if resp.status_code != 200:
        return JSONResponse({"ok": False, "error": "monitor_error"}, status_code=502)

    data = resp.json()
    if data.get("skipped"):
        return {"ok": True, "skipped": True}

    alert = None
    signal = alerts.signal_from_monitor(data.get("gesture", ""), bool(data.get("distress")))
    if signal:
        created, alert_id = alerts.record_signal(patient["id"], *signal)
        alert = {"created": created, "id": alert_id, "level": signal[0]}

    emotion = data.get("emotion")
    return {
        "ok": True,
        "gesture": data.get("gesture"),
        "raw_gesture": data.get("raw_gesture"),
        "landmarks": data.get("landmarks"),
        "emotion": None if not emotion else {
            "label": emotion["label"], "confidence": emotion["confidence"],
            "probs": emotion["probs"], "box": emotion["box"]},
        "status": alerts.live_status(data.get("gesture", ""), bool(data.get("distress"))),
        "alert": alert,
    }


@router.post("/patient/monitor/stop")
async def monitor_stop(request: Request, patient=Depends(require_patient)):
    sid = request.session.pop("monitor_sid", None)
    if sid:
        try:
            await _client().post(f"{config.MONITOR_SERVICE_URL}/session/{sid}/stop")
        except httpx.HTTPError:
            pass          # the service cleans up idle sessions by itself
    return {"ok": True}


@router.get("/patient/monitor/status")
def monitor_status(patient=Depends(require_patient)):
    rows = alerts.decorate(crud.list_care_alerts_for_patient(patient["id"], limit=10))
    history = [{
        "id": a["id"], "when": a["created_label"], "level": a["level"], "level_label": a["level_label"],
        "source": a["source_label"], "detail": a["detail"], "status": a["status"],
        "response": (a["responder"] + " at " + a["ack_label"] + (" \u2014 \u201c" + a["ack_note"] + "\u201d" if a["ack_note"] else ""))
                    if a["status"] == "acknowledged" else "Waiting",
    } for a in rows]
    if not rows:
        return {"alert": None, "history": []}
    a = rows[0]
    return {"alert": {
        "id": a["id"], "level": a["level"], "level_label": a["level_label"], "status": a["status"],
        "created_label": a["created_label"], "still_signalling": a["still_signalling"], "escalated": a["escalated"],
        "acknowledged_by": a["responder"], "ack_label": a["ack_label"], "ack_note": a["ack_note"],
    }, "history": history}


# ----------------------------- doctor -----------------------------
@router.get("/doctor/alerts")
def doctor_alerts(request: Request, doctor=Depends(require_doctor)):
    rows = alerts.decorate(crud.list_care_alerts_for_doctor(doctor["id"], limit=100))
    return templates.TemplateResponse(request, "doctor_alerts.html", {
        "doctor": doctor, "flash": _pop_flash(request),
        "open_alerts": sorted((a for a in rows if a["is_open"]),
                              key=lambda a: (-alerts.RANK[a["level"]], a["id"])),
        "history": [a for a in rows if not a["is_open"]][:50],
        "latest_id": rows[0]["id"] if rows else 0,
    })


@router.post("/doctor/alerts/{alert_id}/acknowledge")
def doctor_acknowledge(request: Request, alert_id: int, note: str = Form(""),
                       doctor=Depends(require_doctor)):
    ok, message = alerts.acknowledge(doctor["id"], alert_id, note)
    _flash(request, "success" if ok else "error", message)
    return RedirectResponse("/doctor/alerts", status_code=303)


@router.get("/doctor/alerts/feed")
def doctor_alert_feed(doctor=Depends(require_doctor)):
    return alerts.feed_for_doctor(doctor["id"])
