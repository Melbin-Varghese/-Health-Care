"""
extensions.py
Shared objects created ONCE and imported by every router
(same idea as extensions.py in the Flask project: db, login_manager).
"""

from fastapi.templating import Jinja2Templates

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