from __future__ import annotations

from flask import flash, redirect, request, url_for

from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def inspection_log_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    return redirect(url_for("inspection_v2.inspection_sheet", resident_id=resident_id))


def add_inspection_log_view(resident_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    return redirect(url_for("inspection_v2.inspection_sheet", resident_id=resident_id))


def edit_inspection_log_view(resident_id: int, inspection_id: int):
    init_db()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _resident_case_redirect(resident_id)

    target_url = url_for("inspection_v2.inspection_sheet", resident_id=resident_id)

    if request.method == "GET":
        target_url = f"{target_url}#inspection-history"

    return redirect(target_url)
