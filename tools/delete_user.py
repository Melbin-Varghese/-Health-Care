"""
tools/delete_user.py
Safely delete a doctor or a patient AND everything that belongs to them.

SQLite is not enforcing foreign keys in this project, so deleting only the
doctors/patients row would leave orphaned prescriptions, doses, appointments...
This script deletes in the right order, inside one transaction, after making a backup.

Run from the project root, with the app stopped:
    python tools/delete_user.py patient 3
    python tools/delete_user.py doctor 4
Add --yes to skip the confirmation prompt, --db PATH to use another database file.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "sukham.db"

# (label, table, WHERE clause using ?[, SET clause]) in the order they must run.
# Children first, the person last. A 4th item means "UPDATE ... SET" (keep the row, drop the link)
# instead of DELETE.
PLANS = {
    "patient": [
        ("dose logs",            "dose_logs",            "patient_id = ?"),
        ("medication schedules", "medication_schedules", "medication_id IN (SELECT id FROM medications WHERE patient_id = ?)"),
        ("medications",          "medications",          "patient_id = ?"),
        ("appointments",         "appointments",         "patient_id = ?"),
        ("health records",       "health_records",       "patient_id = ?"),
        ("symptom checks",       "symptom_checks",       "patient_id = ?"),
        ("adherence alerts",     "adherence_alerts",     "patient_id = ?"),
        ("help-signal alerts",   "care_alerts",          "patient_id = ?"),
        ("the patient",          "patients",             "id = ?"),
    ],
    "doctor": [
        ("dose logs",            "dose_logs",            "medication_id IN (SELECT id FROM medications WHERE doctor_id = ?)"),
        ("medication schedules", "medication_schedules", "medication_id IN (SELECT id FROM medications WHERE doctor_id = ?)"),
        ("medications",          "medications",          "doctor_id = ?"),
        ("appointments",         "appointments",         "doctor_id = ?"),
        ("health records",       "health_records",       "doctor_id = ?"),
        ("alerts they answered (kept, unlinked)", "care_alerts", "acknowledged_by = ?", "acknowledged_by = NULL"),
        ("the doctor",           "doctors",              "id = ?"),
    ],
}


def table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def main() -> int:
    ap = argparse.ArgumentParser(description="Delete a doctor or patient and all their data.")
    ap.add_argument("role", choices=["doctor", "patient"])
    ap.add_argument("user_id", type=int)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}")
        return 1

    conn = sqlite3.connect(args.db)
    table = "doctors" if args.role == "doctor" else "patients"
    person = conn.execute(f"SELECT id, name, email FROM {table} WHERE id = ?", (args.user_id,)).fetchone()
    if not person:
        print(f"No {args.role} with id {args.user_id}.")
        return 1

    plan = [step for step in PLANS[args.role] if table_exists(conn, step[1])]
    print(f"\n{args.role.capitalize()} #{person[0]}: {person[1]} <{person[2]}>\nThis will permanently delete:")
    for label, tbl, where, *_ in plan:
        n = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {where}", (args.user_id,)).fetchone()[0]
        print(f"  {n:>4}  {label}")

    if not args.yes and input("\nType DELETE to confirm: ").strip() != "DELETE":
        print("Cancelled. Nothing was changed.")
        return 0

    backup = args.db.with_name(f"{args.db.name}.bak-{datetime.now():%Y%m%d-%H%M%S-%f}")
    shutil.copy2(args.db, backup)
    try:
        with conn:                       # one transaction: all of it or none of it
            for _, tbl, where, *set_clause in plan:
                if set_clause:
                    conn.execute(f"UPDATE {tbl} SET {set_clause[0]} WHERE {where}", (args.user_id,))
                else:
                    conn.execute(f"DELETE FROM {tbl} WHERE {where}", (args.user_id,))
    finally:
        conn.close()
    print(f"\nDeleted. Backup saved as {backup.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
