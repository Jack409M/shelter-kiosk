from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, session, url_for

from core.auth import require_login, require_shelter


case_management = Blueprint(
    "case_management",
    __name__,
    url_prefix="/staff/case-management",
)


def _case_manager_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


@case_management.get("")
@require_login
@require_shelter
def index():

    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    return render_template("case_management/index.html")
