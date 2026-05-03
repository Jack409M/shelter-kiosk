from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.shelter_capacity_service import load_capacity_rows, save_shelter_capacities
from routes.operations_settings_parts.access import _director_allowed

shelter_capacity = Blueprint(
    "shelter_capacity",
    __name__,
    url_prefix="/staff/admin/shelter-capacity",
)


@shelter_capacity.route("", methods=["GET", "POST"])
@require_login
@require_shelter
def index():
    if not _director_allowed(session):
        return redirect(url_for("attendance.staff_attendance"))

    if request.method == "POST":
        save_shelter_capacities(request.form)
        return redirect(url_for("shelter_capacity.index"))

    rows = load_capacity_rows()

    return render_template(
        "admin_shelter_capacity.html",
        rows=rows,
    )
