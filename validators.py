"""
validators.py
Form validation rules shared by the doctor and patient routers.
"""

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s]{7,15}$")


def parse_age(age_raw: str):
    """Return (age_int_or_None, error_message_or_None)."""
    if not age_raw.isdigit():
        return None, "Enter a valid age."
    age = int(age_raw)
    if age < 0 or age > 120:
        return None, "Enter a realistic age."
    return age, None
