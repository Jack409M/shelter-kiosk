from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for

from core.access import require_resident
from core.resident_portal_service import chi_today_str, complete_chore, get_today_chores
from routes.resident_portal import resident_portal
from routes.resident_portal_parts.helpers import (
    _clean_text,
    _clear_resident_session,
    _prepare_resident_request_context,
    _resident_signin_redirect,
)


@resident_portal.route("/resident/chores", methods=["GET", "POST"])
@require_resident
def resident_chores():
    resident_id = None
    shelter = ""

    try:
        resident_id, shelter, _resident_identifier = _prepare_resident_request_context()

        if resident_id is None:
            return _resident_signin_redirect()

        if request.method == "POST":
            assignment_id = _clean_text(request.form.get("assignment_id"))
            result = complete_chore(resident_id, assignment_id)

            if not result.found:
                flash("Chore assignment not found.", "error")
            elif result.already_completed:
                flash("That chore was already completed.", "ok")
            elif result.completed:
                flash("Chore marked completed.", "success")
            else:
                flash("Unable to complete that chore.", "error")

            return redirect(url_for("resident_portal.resident_chores"))

        chores = get_today_chores(resident_id)

        return render_template(
            "resident/chores.html",
            chores=chores,
            today=chi_today_str(),
        )
    except Exception as exc:
        current_app.logger.exception(
            "resident_portal_chores_failed resident_id=%s shelter=%s exception_type=%s",
            resident_id if resident_id is not None else "unknown",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()
