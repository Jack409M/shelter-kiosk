from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, session

from core.auth import require_login, require_shelter
from core.rent_idle_time_service import build_resident_slot_idle_time_report

bed_turnover = Blueprint("bed_turnover", __name__, url_prefix="/staff/bed-turnover")
CHICAGO_TZ = ZoneInfo("America/Chicago")
_ALLOWED_ROLES = {"case_manager", "shelter_director", "admin"}


def _current_year() -> int:
    return datetime.now(CHICAGO_TZ).year


@bed_turnover.route("")
@require_login
@require_shelter
def index():
    role = str(session.get("role") or "").strip().lower()
    if role not in _ALLOWED_ROLES:
        return render_template("errors/403.html"), 403

    shelter = str(session.get("shelter") or "").strip().lower()
    report = build_resident_slot_idle_time_report(_current_year())
    rows = report["rows"]

    if role == "case_manager" and shelter:
        rows = [row for row in rows if row.shelter == shelter]

    return render_template(
        "bed_turnover/index.html",
        title="Bed Turnover",
        report=report,
        rows=rows,
        role=role,
        shelter=shelter,
    )
