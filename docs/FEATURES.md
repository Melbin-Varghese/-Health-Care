# Feature map

Status: **Live** = backed by the database/logic · **Placeholder** = hard-coded demo content · **Not reviewed** = code was not available when this was written.

## Public
| Feature | URL | Template | Status |
|---------|-----|----------|--------|
| Landing page | `/` | `main.html` | Live (marketing copy mentions appointments and an admin role that don't exist yet) |

## Doctor
| Feature | URLs | Template | Logic | Status |
|---------|------|----------|-------|--------|
| Register / login / logout | `/doctor/register`, `/doctor/login`, `/doctor/logout` | `doctor_register.html`, `doctor_login.html` | `crud`, `security`, `validators` | Live |
| Dashboard | `/doctor/dashboard` | `doctor_dashboard.html` | `crud.list_medications_for_doctor` | Prescribed-medications table, today's appointment count and the pending-requests banner are live. Patients count, messages, notifications and "My patients" are **placeholders** |
| Prescriptions | `/doctor/prescriptions`, `POST /doctor/prescriptions/add` | `doctor_prescriptions.html` | `crud.create_medication`, `medication_service.generate_doses` | Live |
| Adherence alerts | `/doctor/prescriptions/adherence` | `doctor_adherence.html` | `medication_service.compute_adherence`, `crud.list_alerts_for_doctor` | Live |
| Appointments | `/doctor/appointments`, `POST /doctor/appointments/{id}/confirm\|decline\|cancel` | `doctor_appointments.html` | `appointment_service.doctor_respond` | Live |
| Patient alerts | `/doctor/alerts`, `GET /doctor/alerts/feed`, `POST /doctor/alerts/{id}/acknowledge` | `doctor_alerts.html`, `static/js/doctor_alert_poll.js` (every doctor page) | `alert_service` | Live |
| Risk scoring | `/doctor/risk` | `risk_scoring.html` | `risk.calculate_risk`, `crud.create_health_record` | Live |
| Scan review hub | `/doctor/scans` | `scan_review.html` | n/a | Live. Eye scan and Bone scan are "coming soon" |
| Pneumonia X-ray | `/doctor/xray` | `pneumonia.html` | `services/pneumonia_service.py` over HTTP | Live (needs the AI service running) |

## Patient
| Feature | URLs | Template | Logic | Status |
|---------|------|----------|-------|--------|
| Register / login / logout | `/patient/register`, `/patient/login`, `/patient/logout` | `patient_register.html`, `patient_login.html` | `crud`, `security`, `validators` | Live |
| Dashboard | `/patient/dashboard` | `patient_dashboard.html` | `medication_service`, `crud` | Prescriptions, today's doses and adherence are live. Next appointment is live. Vitals, reports, messages, notifications and settings are **placeholders**. "Nearby care" embeds Google Maps in an iframe |
| Appointments | `/patient/appointments`, `POST /patient/appointments/book`, `POST /patient/appointments/{id}/cancel` | `patient_appointments.html` | `appointment_service.book`, `.patient_cancel` | Live |
| Patient Monitor (automatic alerts) | `/patient/monitor`, `POST /patient/monitor/frame`, `POST /patient/monitor/stop`, `GET /patient/monitor/status` | `patient_monitor.html` | `alert_service`, `services/monitor_service` over HTTP | Live (needs the monitor service on port 8002 and a camera) |
| Confirm a dose | `POST /patient/doses/{id}/respond` | (form on dashboard) | `crud.update_dose_status` | Live |
| My adherence | `/patient/prescriptions/adherence` | `patient_adherence.html` | `medication_service.adherence_by_medication` | Live |
| Symptom checker | `/patient/symptom-checker` | `symptom_checker.html` | `crud.create_symptom_check`, `SYMPTOM_SERVICE_URL` | Not reviewed |
| Profile | `/patient/profile`, `POST /patient/profile/update` | `patient_profile.html` | `crud.update_patient` | Live |

## Background jobs (`scheduler.py`)
| Interval | Job | What it does |
|----------|-----|--------------|
| 1 min | `send_due_reminders` | Prints a reminder for each dose that has come due (swap `print` for SMS/email/push) |
| 30 min | `check_all_adherence` | Raises a low-adherence alert (below 70% over 7 days), at most once per patient per day |
| 1 hour | `ensure_upcoming_doses` | Creates dose logs for today and tomorrow, expires finished courses |

## Database tables
`doctors`, `patients`, `health_records`, `medications`, `medication_schedules`, `dose_logs`, `adherence_alerts`, `symptom_checks`, `appointments`, `care_alerts`.

## Not built yet (shown in the UI or copy)
Messaging, notifications, doctor-defined working hours, appointment reminders, vitals trends, reports/documents, admin role, eye scan, bone scan, real SMS/email reminders.

## Appointment rules (`appointment_service.py`)
Patient requests a slot (**pending**) -> doctor **confirms** or **declines** -> either side can **cancel** a future appointment (the doctor only after confirming).
30-minute slots, 09:00-17:00, Monday-Friday, up to 30 days ahead, at least 30 minutes from now. A doctor, and a patient, can hold only one live appointment per slot; the database enforces this. A declined or cancelled slot becomes free again. Change the constants at the top of the file to change the rules.

## Patient Monitor (automatic non-verbal alerts)
The layout follows the original Streamlit monitor: camera with overlays on the left; a coloured **Status** card, **Facial expression** and an emotion bar chart on the right; **Alert history** below. **Nothing is sent by hand.** There are no help or emergency buttons; every alert comes from the face and hand models.

Open `/patient/monitor` and monitoring **starts by itself** (the browser asks once to allow the camera):

- **Hand signal:** open palm = I'm OK (nothing sent), one finger = need help, closed fist = emergency. Needs about 1-2 seconds of steady holding.
- **Face:** if the expression model reads distress (angry/disgust/fear/sad at 45%+ confidence) in 60% of the last 30 readings, a low-priority CAUTION alert is raised. This is an automatic guess and can be wrong.
- **Status card colours:** grey = camera not active, green = OK, amber = CAUTION, orange = HELP, red = EMERGENCY.
- **Camera problems are explained:** permission blocked, no camera, or "another program is using the camera" (OBS, Zoom, Teams, another tab). When the default camera is busy it tries the other cameras by itself, retries every 4 seconds, and a "Camera" list lets the patient pick one.
- **Keeps itself running:** the screen is kept awake, a lost camera reconnects after 3 seconds, and a deliberate "Pause monitoring" is remembered across reloads.

How an alert travels (`alert_service.py`, `routes/monitor.py`):
- The browser sends about 5 small JPEG frames a second to the main app, which forwards them to the monitor service (port 8002). Frames are analysed in memory and never saved.
- A held gesture makes ONE alert, not one per frame. A stronger signal (help -> emergency) makes a new alert. After a doctor responds, the patient must stop for 30 seconds before a new alert can start.
- **Who is alerted:** doctors who prescribed the patient something or have a pending/confirmed appointment with them. A patient with no doctor yet alerts every doctor.
- **Automatic escalation:** a help/emergency alert nobody answers within 90 seconds becomes visible to **every** doctor and is marked "Escalated". Change `ESCALATE_AFTER_SECONDS` in `crud.py`.
- **Doctors** see a badge on every page, a pop-up (with sound for help/emergency, silent for the CAUTION guess), and answer with "I'm responding" plus an optional note. The patient sees who responded. Doctors keep seeing the alerts they answered.

Limits: automatic only means no clicking. The patient's page must stay open on screen with the camera allowed, and a doctor must have Sukham open to see pop-ups. A camera can only be used by one program at a time. This supports, and does not replace, a nurse-call system.
