"""
extensions.py
Shared objects created ONCE and imported by every router
(same idea as extensions.py in the Flask project: db, login_manager).
"""

from fastapi.templating import Jinja2Templates

import alert_service
import appointment_service as appts
import config

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))



def _times12(value):
    """'08:00, 20:00' -> '8:00 AM, 8:00 PM' (template filter)."""
    if not value:
        return ""
    out = []
    for t in value.split(","):
        h, m = (int(x) for x in t.strip().split(":"))
        out.append(f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}")
    return ", ".join(out)


templates.env.filters["times12"] = _times12

# Small helpers the dashboards call directly, so their routes need no changes.
templates.env.globals["next_appointment"] = appts.next_for_patient
templates.env.globals["appointments_today"] = appts.today_count_for_doctor
templates.env.globals["pending_appointments"] = appts.pending_count_for_doctor
templates.env.globals["open_alert_count"] = alert_service.open_count_for_doctor
templates.env.globals["urgent_alert_count"] = alert_service.urgent_count_for_doctor
