# What changed in this reorganization

## Moved
- Both sidebars → `templates/partials/` (includes updated).
- `pneumonia_service.py` → `services/`, model → `services/models/`.
- All Python modules the `routes/` package imports (`crud`, `database`, `risk`, `medication_service`, ...) **stay at the root with the same names**, so nothing in `routes/` breaks.
- Line endings normalized to LF (`.gitattributes` added).

## Fixed
- `pneumonia_service.py`: model path no longer depends on the working directory; inference no longer blocks the event loop; 10 MB upload limit; 503 if the model isn't loaded; `lifespan` instead of deprecated `on_event`; removed open CORS (the main server calls it server-side). Response format is unchanged.
- Ports: docs and `config.py` now agree (main 9000, pneumonia 8000, symptom 8001).
- `config.py`: optional `.env` loading and a warning when the default `SECRET_KEY` is used.
- Risk, Pneumonia, Scan Review and Profile pages now use the shared sidebars (they had their own copies with different menus; Profile's Settings link pointed to a tab that doesn't exist). Highlighting is driven by `nav_active` on every page; the patient sidebar no longer always highlights Prescriptions.
- Login pages: restored the (blanked) error display; field now accepts email **or phone**, matching `crud.get_*_by_login`.
- Doctor register: restored error display, sticky values and `required` (blanked).
- Prescribe form: selected patient is kept after a validation error.
- Doctor adherence page: formula text now includes delayed doses, as the code does.
- Landing page: duplicate `id="patients"` removed.
- Patient dashboard: literal "patient name" replaced with the real name, empty avatar filled, duplicate Messages tab removed.

## Not changed (needs `routes/` or a decision)
- CSRF protection on all POST forms.
- Patient dashboard's "Missed" button posts `status=missed`, but `dose_logs.status` is documented as `pending | taken | skipped | delayed`. Check that the route maps it.
- SQLite foreign keys aren't enforced (`PRAGMA foreign_keys = ON` not set).
- `end_date >= start_date` isn't validated.
- Login/register error variables: the restored blocks accept `error` (string) or `errors` (list) and `form`; adjust to whatever your routes pass.
- Placeholder dashboard content (see docs/FEATURES.md).
- Three similar stylesheets (`style.css`, `stylee.css`, `styleee.css`): couldn't see `static/css/`.

# Appointments (new)
- New: `appointment_service.py`, `routes/appointments.py`, `templates/patient_appointments.html`, `templates/doctor_appointments.html`, `static/css/appointments.css`.
- `database.py`: new `appointments` table with partial unique indexes (no double booking). Created automatically on startup; existing data is untouched.
- `crud.py`: appointment queries appended. `app.py`: router registered. `extensions.py`: three small template helpers so the dashboards show real data without changing their routes.
- Both sidebars gained an Appointments link. On both dashboards the demo Appointments tab was replaced by a link to the real page, the "Next appointment" / "Today's appointments" cards are real, and doctors get a banner when requests are waiting.
- Not included yet: reminders before an appointment, doctor-defined working hours, rescheduling (cancel and rebook instead).

# Help Signal (new)
- New: `alert_service.py`, `routes/monitor.py`, `templates/patient_monitor.html`, `templates/doctor_alerts.html`, `static/css/monitor.css`, `static/js/doctor_alert_poll.js`, `services/monitor_service/`.
- `database.py`: `care_alerts` table (created automatically). `crud.py`: alert queries. `config.py` / `.env.example`: `MONITOR_SERVICE_URL`. `app.py`: router registered. `extensions.py`: two template helpers for the badge and banner.
- The old Streamlit frontend is replaced by the Sukham page. The old FastAPI backend became `services/monitor_service/`; `emotion_detector.py` and `gesture_detector.py` are unchanged, `main.py` was rewritten:
  - it no longer decides alerts or writes `alerts_log.csv` (one shared alert log mixed up patients); Sukham stores alerts per patient in the database;
  - inference runs in a worker thread, with a per-session lock (a busy session drops frames instead of queueing);
  - no CORS and no alert endpoints, since only the main app talks to it.
- Sidebars: Help Signal (patient) and Patient Alerts with a live badge (doctor). Doctor dashboard shows a red banner when patients are asking for help.
- `tools/delete_user.py` now also removes a deleted patient's alerts and unlinks a deleted doctor from the alerts they answered.
- Not included yet: SMS/phone notification of doctors who aren't logged in, per-ward routing, voice or switch-based signals.

# Help Signal: automatic mode
- **Starts by itself:** the patient page starts monitoring on load (no button). Pause is remembered across reloads. Screen stays awake; a lost camera reconnects.
- **Alerts reach doctors on their own:** the automatic "possible distress" alert now shows a quiet pop-up to the doctor (no sound); help/emergency keep the loud pop-up.
- **Automatic escalation:** an unanswered help/emergency alert is shown to every doctor after 90 seconds.
- Doctors keep seeing alerts they answered, even if the patient isn't in their care.
- Your three model files are included in `services/monitor_service/models/`.
- Tested with your real models: the service loads them, reads faces, runs the hand model (about 120 ms/frame on a small server), and the full chain browser -> Sukham -> service -> database -> doctor works. Not tested here: real hands (no hand photos were available), so please try a fist and a pointing finger yourself.
- `requirements.txt` for the monitor service pins `opencv-python-headless<5`.

# Patient Monitor: no manual alerts
- **Removed the manual "I need help" / "EMERGENCY" buttons** and their `/patient/alerts/manual` endpoint. Alerts now come only from the hand and face models.
- **Patient page rebuilt like the original monitor** (the one in your recording): camera with landmarks, face box and gesture text drawn on the video; a coloured Status card (OK / CAUTION / HELP / EMERGENCY / camera not active); Facial expression with a 7-bar emotion chart; Alert history table that updates by itself; the same "not a certified medical device" warning. Renamed "Help Signal" to "Patient Monitor" in the sidebars.
- **Camera errors are now explained.** Your recording ended with `NotReadableError: Could not start video source`, which means another program (often OBS, Zoom, Teams or another tab) is holding the camera. The page now says so, retries every 4 seconds, falls back to your other cameras automatically, and has a camera picker. Permission-denied and no-camera cases have their own messages.
- The live status (`alert_service.live_status`) matches the original `alert_manager` texts.
