"""
scheduler.py
Background jobs for the medication feature (started/stopped from app.py's lifespan).

  every minute   -> send reminders for doses that just became due
  every 30 min   -> re-check adherence and raise low-adherence alerts
  every hour     -> make sure upcoming dose logs exist (and expire finished courses)
"""

from apscheduler.schedulers.background import BackgroundScheduler

import medication_service as svc

scheduler = BackgroundScheduler()


def _safe(fn):
    """A failing job must never take the web server down."""
    def wrapper():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"[SCHEDULER] {fn.__name__} failed: {exc}", flush=True)
    wrapper.__name__ = fn.__name__
    return wrapper


def start_scheduler() -> None:
    if scheduler.running:
        return
    svc.ensure_upcoming_doses()  # catch up immediately on startup
    scheduler.add_job(_safe(svc.send_due_reminders), "interval", minutes=1, id="send_due_reminders")
    scheduler.add_job(_safe(svc.check_all_adherence), "interval", minutes=30, id="check_all_adherence")
    scheduler.add_job(_safe(svc.ensure_upcoming_doses), "interval", hours=1, id="ensure_upcoming_doses")
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)