from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from routes.admin_parts.duplicate_merge_review import _resident_summary_rows
from routes.admin_parts.helpers import require_admin_role


def duplicate_name_group_review_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    first_name_key = (request.args.get("first_name_key") or "").strip().lower()
    last_name_key = (request.args.get("last_name_key") or "").strip().lower()

    if not first_name_key or not last_name_key:
        flash("Invalid duplicate review request.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    residents = _resident_summary_rows(first_name_key, last_name_key)

    if len(residents) < 2:
        flash("Duplicate group no longer has multiple active matching residents.", "warning")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    return render_template(
        "duplicate_name_group_review.html",
        title="Duplicate Name Review",
        first_name_key=first_name_key,
        last_name_key=last_name_key,
        residents=residents,
    )
